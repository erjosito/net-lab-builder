"""Bounded, one-shot, bidirectional mTLS streaming. Python standard library only."""
import argparse
import concurrent.futures
import contextlib
import hashlib
import http.client
import http.server
import json
import os
from pathlib import Path
import re
import socket
import ssl
import threading
import time
from datetime import datetime, timezone

GIB = 1024 ** 3
MAX_BYTES = 5 * GIB
RATE = 2_500_000
MAX_RATE = 16 * 1024 ** 2
CHUNK = 65536


def utc():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    target = Path(path)
    target.write_text(json.dumps(value, separators=(",", ":")) + "\n", encoding="utf-8")
    os.chmod(target, 0o600)


def blocks(size):
    for offset in range(0, size, CHUNK):
        yield hashlib.shake_256(b"bwb-transfer-v1:" + str(offset).encode()).digest(
            min(CHUNK, size - offset))


def digest(size):
    result = hashlib.sha256()
    for block in blocks(size):
        result.update(block)
    return result.hexdigest()


def nic(interface):
    if interface in (".", "..") or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,32}", interface):
        raise ValueError("invalid_interface")
    root = Path("/sys/class/net") / interface / "statistics"
    return {k: int((root / (k + "_bytes")).read_text()) for k in ("rx", "tx")}


def delta(before, after):
    change = {k: after[k] - before[k] for k in ("rx", "tx")}
    if min(change.values()) < 0:
        raise RuntimeError("nic_counter_reset")
    change["wire_once"] = change["rx"] + change["tx"]
    return change


class Guard:
    def __init__(self, config, counter=nic):
        self.config = config
        self.counter = counter
        self.before = counter(config["interface"])
        self.started = time.monotonic()
        self.cancel = threading.Event()
        self.sockets = []
        self.lock = threading.Lock()
        self.last_check = 0

    def stop(self):
        self.cancel.set()
        with self.lock:
            for connection in self.sockets:
                try:
                    socket.socket.shutdown(connection, socket.SHUT_RDWR)
                except OSError:
                    pass

    def track(self, connection):
        with self.lock:
            self.sockets.append(connection)
            if self.cancel.is_set():
                with contextlib.suppress(OSError):
                    socket.socket.shutdown(connection, socket.SHUT_RDWR)

    def check(self):
        if self.cancel.is_set():
            raise RuntimeError("peer_cancelled")
        if time.monotonic() - self.started >= self.config.get("deadline", 2700):
            self.stop()
            raise TimeoutError("total_deadline")
        with self.lock:
            if time.monotonic() - self.last_check > .25:
                self.last_check = time.monotonic()
                used = delta(self.before, self.counter(self.config["interface"]))["wire_once"]
                if used >= self.config["wire_cap"]:
                    self.cancel.set()
                    raise RuntimeError("nic_wire_cap")

    def pace(self, count, started):
        delay = count / self.config.get("rate", RATE) - (time.monotonic() - started)
        while delay > 0:
            self.check()
            self.cancel.wait(min(delay, .25))
            delay = count / self.config.get("rate", RATE) - (time.monotonic() - started)

    def evidence(self):
        after = self.counter(self.config["interface"])
        return {"before": self.before, "after": after, "delta": delta(self.before, after)}


def context(config, server=False):
    ctx = ssl.create_default_context(
        ssl.Purpose.CLIENT_AUTH if server else ssl.Purpose.SERVER_AUTH,
        cafile=config["ca"])
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.set_alpn_protocols(["http/1.1"])
    ctx.load_cert_chain(config["cert"], config["key"])
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def legs(config):
    value = config.get("legs", ["up", "down"])
    if not isinstance(value, list) or value not in (["up"], ["down"], ["up", "down"]):
        raise ValueError("invalid_declared_legs")
    return value


def aliases(config):
    value = config.get("aliases", {"client": "A", "server": "T"})
    if (not isinstance(value, dict) or set(value) != {"client", "server"}
            or any(not isinstance(v, str) or not re.fullmatch(r"[A-Z]", v)
                   for v in value.values()) or value["client"] == value["server"]):
        raise ValueError("invalid_endpoint_aliases")
    return value


def validate(config):
    legs(config)
    aliases(config)
    if type(config["bytes"]) is not int or not 0 < config["bytes"] <= MAX_BYTES:
        raise ValueError("invalid_byte_cap")
    ceiling = config.get("rate_ceiling", RATE)
    if (type(ceiling) is not int or not 0 < ceiling <= MAX_RATE
            or not 0 < config.get("rate", RATE) <= ceiling):
        raise ValueError("invalid_rate")
    if not 0 < config.get("deadline", 2700) <= 2700:
        raise ValueError("invalid_deadline")
    if not 0 < config.get("idle", 60) <= 120:
        raise ValueError("invalid_idle_timeout")
    if not 0 < config.get("first_request_timeout", 180) <= 180:
        raise ValueError("invalid_first_request_timeout")
    if not 0 < config["wire_cap"] <= 12 * GIB:
        raise ValueError("invalid_wire_cap")
    if not re.fullmatch(r"[a-f0-9]{32}", config["id"]):
        raise ValueError("invalid_transfer_id")
    if type(config.get("readiness_attempts", 1)) is not int or not (
            1 <= config.get("readiness_attempts", 1) <= 12):
        raise ValueError("invalid_readiness_probe_limit")


def record(config, leg, peer):
    names = aliases(config)
    return {"id": config["id"] + "-" + leg,
            "producer": names["client" if leg == "up" else "server"],
            "consumer": names["server" if leg == "up" else "client"],
            "started": utc(), "peer": peer,
            "bytes": 0, "sha256": "", "status": "started", "http_status": 0, "retries": 0}


class TransferServer(http.server.ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True
    request_queue_size = 2

    def __init__(self, config, counter=nic):
        validate(config)
        self.config = config
        self.guard = Guard(config, counter)
        self.expected = digest(config["bytes"])
        self.tls = context(config, True)
        self.slots = threading.BoundedSemaphore(2)
        self.state_lock = threading.Lock()
        self.claimed = set()
        self.records = {}
        self.completed = set()
        self.attempts = 0
        self.probes = 0
        self.failed = False
        self.failure = None
        self.done = threading.Event()
        super().__init__((config.get("bind", "0.0.0.0"), config.get("port", 443)), Handler)
        self.timeout = .2
        self.first_request_deadline = time.monotonic() + config.get("first_request_timeout", 180)

    def process_request(self, request, address):
        self.guard.track(request)
        self.attempts += 1
        if self.attempts > 32 or not self.slots.acquire(False):
            request.close()
            self.failed = True
            self.guard.stop()
            self.done.set()
            return
        super().process_request(request, address)

    def process_request_thread(self, request, address):
        try:
            request.settimeout(self.config.get("idle", 60))
            connection = self.tls.wrap_socket(request, server_side=True,
                                              do_handshake_on_connect=False)
            self.guard.track(connection)
            with connection:
                connection.do_handshake()
                super().process_request_thread(connection, address)
        except (OSError, ssl.SSLError):
            self.probes += 1
            request.close()
        finally:
            self.slots.release()

    def handle_error(self, request, address):
        self.failed = True
        self.guard.stop()
        self.done.set()

    def run(self):
        started = utc()
        try:
            while not self.done.is_set():
                self.guard.check()
                with self.state_lock:
                    if not self.claimed and time.monotonic() >= self.first_request_deadline:
                        raise TimeoutError("first_request_timeout")
                self.handle_request()
        except Exception as error:
            self.failed = True
            self.failure = str(error)
            self.guard.stop()
        finally:
            self.guard.stop()
            self.server_close()
        report = {"role": "server_" + aliases(self.config)["server"],
                  "declared_legs": legs(self.config), "aliases": aliases(self.config),
                  "started": started, "ended": utc(),
                  "legs": self.records, "nic": self.guard.evidence(),
                  "failure": self.failure,
                  "handshake_or_empty_probes": self.probes, "requests": len(self.claimed)}
        report["success"] = (not self.failed and set(self.records) == set(legs(self.config)) and
                             all(x["status"] == "ok" for x in self.records.values()) and
                             report["nic"]["delta"]["wire_once"] < self.config["wire_cap"])
        save(self.config["report"], report)
        return report


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "bounded"
    sys_version = ""

    def log_message(self, *args):
        pass

    def log_error(self, *args):
        self.server.failed = True
        self.server.done.set()

    def send_error(self, code, message=None, explain=None):
        self.server.failed = True
        self.server.done.set()
        super().send_error(code, message, explain)

    def handle_expect_100(self):
        self.send_error(417)
        return False

    def handle_one_request(self):
        super().handle_one_request()
        if not getattr(self, "raw_requestline", b""):
            self.server.probes += 1
        self.close_connection = True

    def do_POST(self):
        self.transfer("up")

    def do_GET(self):
        self.transfer("down")

    def transfer(self, leg):
        server = self.server
        cfg = server.config
        rec = record(cfg, leg, self.client_address[0])
        try:
            if leg not in legs(cfg):
                raise ValueError("undeclared_leg")
            if self.client_address[0] != cfg["expected_peer"]:
                raise ValueError("unexpected_peer")
            if self.path != "/" + cfg["id"] + "/" + leg:
                raise ValueError("invalid_path")
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Encoding"):
                raise ValueError("encoding_forbidden")
            if leg == "up" and (len(lengths) != 1 or lengths[0] != str(cfg["bytes"])):
                raise ValueError("invalid_content_length")
            if leg == "down" and lengths:
                raise ValueError("download_body_forbidden")
            with server.state_lock:
                if not server.claimed and time.monotonic() >= server.first_request_deadline:
                    raise TimeoutError("first_request_timeout")
                if leg in server.claimed:
                    raise ValueError("one_shot_already_claimed")
                server.claimed.add(leg)
            hasher = hashlib.sha256()
            start = time.monotonic()
            if leg == "down":
                self.send_response(200)
                self.send_header("Content-Length", str(cfg["bytes"]))
                self.send_header("X-Payload-SHA256", server.expected)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Encoding", "identity")
                self.send_header("Connection", "close")
                self.end_headers()
                for block in blocks(cfg["bytes"]):
                    server.guard.check()
                    server.guard.pace(rec["bytes"] + len(block), start)
                    self.wfile.write(block)
                    hasher.update(block)
                    rec["bytes"] += len(block)
                self.wfile.flush()
            else:
                while rec["bytes"] < cfg["bytes"]:
                    server.guard.check()
                    block = self.rfile.read(min(CHUNK, cfg["bytes"] - rec["bytes"]))
                    if not block:
                        raise ValueError("truncated_upload")
                    hasher.update(block)
                    rec["bytes"] += len(block)
                    server.guard.pace(rec["bytes"], start)
            rec.update(sha256=hasher.hexdigest(), ended=utc(), http_status=200)
            if rec["sha256"] != server.expected or rec["bytes"] != cfg["bytes"]:
                raise ValueError("hash_or_count_mismatch")
            rec["status"] = "ok"
            with server.state_lock:
                server.records[leg] = rec
                save(cfg["report"], {"role": "server_" + aliases(cfg)["server"],
                                    "legs": server.records})
            if leg == "up":
                body = json.dumps(rec, separators=(",", ":")).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)
                self.wfile.flush()
        except Exception as error:
            server.failed = True
            rec.update(status=type(error).__name__ + ":" + str(error), ended=utc())
            with server.state_lock:
                server.records.setdefault(leg, rec)
            try:
                self.send_error(400)
            except OSError:
                pass
            server.guard.stop()
            server.done.set()
        finally:
            with server.state_lock:
                server.completed.add(leg)
                if server.completed == set(legs(cfg)):
                    server.done.set()


def client(config, counter=nic):
    validate(config)
    guard = Guard(config, counter)
    expected = digest(config["bytes"])
    tls = context(config)
    results = {}
    started = utc()
    probes = []
    prepared_connection = None
    for attempt in range(config.get("readiness_attempts", 1)):
        guard.check()
        probe = {"at": utc(), "attempt": attempt + 1, "payload_bytes": 0,
                 "reused_for": legs(config)[0]}
        candidate = http.client.HTTPSConnection(
            config["host"], config.get("port", 443), context=tls, timeout=5)
        try:
            candidate.connect()
            candidate.sock.settimeout(config.get("idle", 60))
            prepared_connection = candidate
            probe["status"] = "ready"
            probes.append(probe)
            break
        except (OSError, ssl.SSLError) as error:
            candidate.close()
            probe["status"] = type(error).__name__
            probes.append(probe)
            if isinstance(error, ssl.SSLError):
                break
            if attempt + 1 < config.get("readiness_attempts", 1):
                guard.cancel.wait(5)
    if prepared_connection is None:
        report = {"role": "client_" + aliases(config)["client"],
                  "declared_legs": legs(config), "aliases": aliases(config),
                  "started": started, "ended": utc(), "legs": {},
                  "nic": guard.evidence(), "requests": 0, "readiness_probes": probes,
                  "success": False}
        save(config["report"], report)
        return report

    def leg_run(leg):
        rec = record(config, leg, config["host"])
        connection = prepared_connection if leg == legs(config)[0] else http.client.HTTPSConnection(
            config["host"], config.get("port", 443), context=tls,
            timeout=config.get("idle", 60))
        try:
            guard.check()
            if leg != legs(config)[0]:
                connection.connect()
            guard.track(connection.sock)
            rec["peer"] = connection.sock.getpeername()[0]
            if rec["peer"] != config.get("expected_peer", config["host"]):
                raise ValueError("unexpected_server_peer")
            path = "/" + config["id"] + "/" + leg
            hasher = hashlib.sha256()
            start = time.monotonic()
            if leg == "up":
                connection.putrequest("POST", path, skip_accept_encoding=True)
                connection.putheader("Content-Length", str(config["bytes"]))
                connection.putheader("Connection", "close")
                connection.endheaders()
                for block in blocks(config["bytes"]):
                    guard.check()
                    guard.pace(rec["bytes"] + len(block), start)
                    connection.send(block)
                    hasher.update(block)
                    rec["bytes"] += len(block)
                response = connection.getresponse()
                if response.status != 200:
                    raise ValueError("upload_status")
                if not response.getheader("Content-Length", "").isdigit() or int(
                        response.getheader("Content-Length")) > 4096:
                    raise ValueError("unbounded_ack")
                ack = json.loads(response.read(4097))
                if (ack["bytes"] != config["bytes"] or ack["sha256"] != expected
                        or ack["status"] != "ok" or ack["id"] != config["id"] + "-up"):
                    raise ValueError("upload_ack_mismatch")
            else:
                connection.request("GET", path, headers={"Accept-Encoding": "identity",
                                                        "Connection": "close"})
                response = connection.getresponse()
                if (response.status != 200 or response.getheader("Content-Length") !=
                        str(config["bytes"]) or response.getheader("X-Payload-SHA256") != expected
                        or response.getheader("Content-Encoding") != "identity"
                        or response.getheader("Transfer-Encoding")):
                    raise ValueError("download_headers")
                while rec["bytes"] < config["bytes"]:
                    guard.check()
                    block = response.read(min(CHUNK, config["bytes"] - rec["bytes"]))
                    if not block:
                        raise ValueError("truncated_download")
                    hasher.update(block)
                    rec["bytes"] += len(block)
            rec.update(sha256=hasher.hexdigest(), http_status=response.status)
            if rec["bytes"] != config["bytes"] or rec["sha256"] != expected:
                raise ValueError("hash_or_count_mismatch")
            rec["status"] = "ok"
        except Exception as error:
            rec["status"] = type(error).__name__ + ":" + str(error)
            guard.stop()
        finally:
            rec["ended"] = utc()
            connection.close()
            results[leg] = rec

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(leg_run, leg) for leg in legs(config)]
        while not all(f.done() for f in futures):
            try:
                guard.check()
            except Exception:
                guard.stop()
            time.sleep(.05)
        for future in futures:
            future.result()
    report = {"role": "client_" + aliases(config)["client"],
              "declared_legs": legs(config), "aliases": aliases(config),
              "started": started, "ended": utc(), "legs": results,
              "nic": guard.evidence(), "requests": len(legs(config)), "readiness_probes": probes}
    report["success"] = (all(r["status"] == "ok" for r in results.values()) and
                         report["nic"]["delta"]["wire_once"] < config["wire_cap"])
    save(config["report"], report)
    return report


def verify(a, t, expected=None):
    if not a["success"] or not t["success"]:
        raise ValueError("endpoint_failure")
    declared = a.get("declared_legs", ["up", "down"])
    names = aliases(a)
    if expected is not None:
        if (declared != expected.get("legs", ["up", "down"])
                or names != aliases(expected)):
            raise ValueError("declared_plan_mismatch")
    if (declared != t.get("declared_legs", ["up", "down"]) or names != aliases(t)
            or set(a["legs"]) != set(legs({"legs": declared}))
            or set(t["legs"]) != set(declared)):
        raise ValueError("declared_evidence_mismatch")
    for leg in declared:
        x, y = a["legs"][leg], t["legs"][leg]
        for key in ("id", "producer", "consumer", "bytes", "sha256", "status", "retries"):
            if x[key] != y[key]:
                raise ValueError("endpoint_evidence_mismatch")
        if x["status"] != "ok" or x["retries"] != 0:
            raise ValueError("incomplete_leg")
        if expected is not None and (
                x["bytes"] != expected["bytes"] or x["sha256"] != expected["payload_sha256"]
                or x["id"] != expected["id"] + "-" + leg
                or any(report["nic"]["delta"]["wire_once"] >= expected["wire_cap"]
                       for report in (a, t))):
            raise ValueError("declared_payload_mismatch")
        if (x["producer"] != names["client" if leg == "up" else "server"]
                or x["consumer"] != names["server" if leg == "up" else "client"]):
            raise ValueError("endpoint_role_mismatch")
    return {"transport": "PASS", "wire_once_" + names["client"]: a["nic"]["delta"]["wire_once"],
            "billing": "INCONCLUSIVE"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("server", "client", "verify"))
    parser.add_argument("config")
    parser.add_argument("--server-report")
    args = parser.parse_args()
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8-sig"))
    if args.role == "verify":
        print(json.dumps(verify(cfg, json.loads(Path(args.server_report).read_text()))))
        return
    report = TransferServer(cfg).run() if args.role == "server" else client(cfg)
    print(json.dumps(report, separators=(",", ":")), flush=True)
    raise SystemExit(0 if report["success"] else 1)


if __name__ == "__main__":
    main()
