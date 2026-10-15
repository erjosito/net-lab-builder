"""Read-only, bounded B0 evidence collector; no routing configuration writes."""
import base64
import concurrent.futures as futures
import datetime as dt
import gzip
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import threading
import time

import control
import guest
import effective_routes

ROOT = pathlib.Path(__file__).resolve().parent
RUNTIME = ROOT / ".runtime-control"
LEASE = RUNTIME / "baseline-validation-lease.json"
OUT = ROOT.parent / "show-output" / "b0-unsecured-er" / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
LOCK = threading.Lock()
START = time.monotonic()
SUB = json.loads((RUNTIME / "account.json").read_text())["subscriptionId"]
BASE = f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{control.RG}/providers/Microsoft.Network"
TARGETS = ["10.110.0.10", "10.120.0.10", "10.130.0.10", "10.140.0.4"]
SPOKES = ["10.10.0.10", "10.20.0.10", "10.30.0.10"]
FAILURES = []


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sanitize(text):
    return text.replace(SUB, "<SUBSCRIPTION_ID>")


def save(name, value):
    (OUT / name).write_text(sanitize(json.dumps(value, indent=2)) + "\n", encoding="utf-8")


def guard():
    lease = json.loads(LEASE.read_text(encoding="utf-8-sig"))
    if (RUNTIME / "STOP").exists() or lease["state"] != "active":
        raise RuntimeError("STOP or inactive lease")
    expiry = dt.datetime.fromisoformat(lease["expiresAtUtc"].replace("Z", "+00:00"))
    if dt.datetime.now(dt.timezone.utc) >= expiry - dt.timedelta(minutes=6):
        raise RuntimeError("80% elapsed lease budget; closure only")
    if lease.get("toolCallsUsed", 0) >= 60:
        raise RuntimeError("80% call budget")
    return lease


def az(args, label):
    with LOCK:
        lease = guard()
        lease["toolCallsUsed"] = lease.get("toolCallsUsed", 0) + 1
        lease["mutationsUsed"] = 0
        lease["lastCheckpointUtc"] = utc()
        LEASE.write_text(json.dumps(lease, indent=2) + "\n")
    command = [shutil.which("az"), *args, "--subscription", SUB, "--only-show-errors", "-o", "json"]
    began = utc()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        output, error = process.communicate(timeout=540)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=30)
        output, error = process.communicate(timeout=30)
        raise RuntimeError(f"{label}: timeout")
    text = output.decode("utf-8", errors="replace")
    record = {"timestampUtc": began, "finishedUtc": utc(), "command": command,
              "exitCode": process.returncode, "stdout": text,
              "stderr": error.decode("utf-8", errors="replace"),
              "sha256": hashlib.sha256(output).hexdigest()}
    save(label + ".json", record)
    print(f"{label}: exit={process.returncode}", flush=True)
    if process.returncode:
        with LOCK:
            FAILURES.append(label)
        return None
    return json.loads(text) if text.strip() else None


def rest(path, label, body=None, query=None):
    args = ["rest", "--method", "post" if body else "get", "--url", path]
    params = OUT / f"{label}-query.json"
    params.write_text(json.dumps(query or {"api-version": "2026-01-01"}))
    args += ["--url-parameters", "@" + str(params)]
    if body:
        body_path = RUNTIME / f"b0-{label}-body.json"
        body_path.write_text(json.dumps(body))
        save(label + "-body.json", body)
        args += ["--body", "@" + str(body_path)]
    return az(args, label)


def routes(site, snap, connection=False):
    return effective_routes.collect(az, SUB, control.RG, site,
                                    f"hub-{site}-{'connection-' if connection else ''}{snap}", connection)


def shell_capture(name):
    site = name.rsplit("-", 1)[-1]
    router = name.startswith("router-")
    source = {"probe-dc-eu": TARGETS[0], "probe-dc-us": TARGETS[1],
              "probe-dc-jp": TARGETS[2], "router-cn": TARGETS[3],
              "probe-spoke-eu": SPOKES[0], "probe-spoke-us": SPOKES[1],
              "probe-spoke-jp": SPOKES[2]}.get(name)
    targets = TARGETS if "spoke" in name else SPOKES
    script = """#!/bin/bash
set -u
exec 2>&1
echo B0_BEGIN; date -u +%FT%TZ
ip -4 address show
ip rule show
ip route show table all
ss -lnt
systemctl is-enabled lab-http; systemctl is-active lab-http
"""
    if router:
        script += """
sha256sum /etc/bird/bird.conf /var/lib/threehub/activation-files.json
birdc show protocols all
birdc show route table lab4 all
birdc show route table underlay4 all
for p in azure_0 azure_1; do birdc show route export "$p" all; done
wg show all endpoints
wg show all latest-handshakes
wg show all transfer
ip -s link show
"""
        if site == "jp":
            script += "swanctl --list-sas\nip -s xfrm policy\n"
        script += """
echo CAPTURE_BEGIN
timeout --signal=INT 150 tcpdump -l -nn -i any -c 32 '((host 10.140.0.4 and host 10.10.0.10) or (host 10.110.0.10 and host 10.20.0.10)) and tcp port 5201' &
CAP=$!
sleep 8
"""
    else:
        script += "sleep 18\n"
    if source:
        for target in targets:
            script += f"""
echo PROBE_BEGIN source={source} target={target}
date -u +%FT%TZ
ip route get {target} from {source}
ping -I {source} -c 2 -W 2 {target}; echo ICMP_EXIT=$?
curl --interface {source} --noproxy '*' -sS --connect-timeout 3 --max-time 5 -w '\\nHTTP_CODE=%{{http_code}} LOCAL=%{{local_ip}} REMOTE=%{{remote_ip}}\\n' http://{target}:5201/; echo TCP_EXIT=$?
echo PROBE_END
"""
    if router:
        script += """
wait "$CAP"; echo CAPTURE_EXIT=$?
echo CAPTURE_END
wg show all transfer
ip -s link show
"""
        if site == "jp":
            script += "swanctl --list-sas\n"
        for ip in TARGETS + SPOKES + list(guest.IPS.values()):
            script += f"ip route get {ip}\nip route get {ip} mark 0x200\n"
        script += "sha256sum /etc/bird/bird.conf /var/lib/threehub/activation-files.json\n"
    script += "date -u +%FT%TZ; echo B0_END\n"
    encoded = base64.b64encode(script.encode()).decode()
    # Compression preserves complete diagnostics within managed instanceView's limit.
    return f"""#!/bin/bash
set -o pipefail
echo B0_GZIP_BEGIN
echo '{encoded}' | base64 -d | bash | gzip -9 | base64 -w0
echo
echo B0_GZIP_END
"""


def decode(name, response):
    instance = (response or {}).get("properties", {}).get("instanceView", {})
    output = instance.get("output", "")
    save(f"guest-{name}-state.json", {key: instance.get(key) for key in ("executionState", "exitCode", "error")})
    try:
        packed = output.split("B0_GZIP_BEGIN", 1)[1].split("B0_GZIP_END", 1)[0].strip()
        raw = gzip.decompress(base64.b64decode(packed)).decode()
        (OUT / f"guest-{name}.txt").write_text(sanitize(raw), encoding="utf-8")
        if "B0_END" not in raw:
            FAILURES.append(f"{name}: incomplete output")
        return raw
    except Exception as exc:
        FAILURES.append(f"{name}: output unavailable or truncated ({type(exc).__name__})")
        return ""


def main():
    OUT.mkdir(parents=True)
    activation = json.loads((RUNTIME / "guest-activation-proof.json").read_text())
    lease = guard()
    save("context.json", {"lease": lease, "correlation": OUT.name, "scenario": "B0", "HRP": "ExpressRoute",
                         "routingIntent": False, "additionalPrepends": 0, "activationProof": activation,
                         "diagnosticExecution": "Managed read batch only; zero configuration mutations"})
    hubs, snapshots, guests = {}, {}, {}
    for site in ("eu", "us", "jp"):
        hubs[site] = rest(f"{BASE}/virtualHubs/hub-{site}", f"hub-{site}-config-before")
    first = time.monotonic()
    for site in ("eu", "us", "jp"):
        snapshots[site] = routes(site, "snapshot1")
        routes(site, "snapshot1", True)
    first = time.monotonic()
    names = ["router-eu", "router-us", "router-jp", "router-cn",
             "probe-dc-eu", "probe-dc-us", "probe-dc-jp",
             "probe-spoke-eu", "probe-spoke-us", "probe-spoke-jp"]
    sources = {name: shell_capture(name) for name in names}
    document, parameters = guest.managed_template(sources, "b0-" + OUT.name.lower())
    for resource in document["resources"]:
        resource["properties"]["timeoutInSeconds"] = 240
    template = RUNTIME / "b0-read-batch.json"
    params = RUNTIME / "b0-read-batch.parameters.json"
    template.write_text(json.dumps(document))
    params.write_text(json.dumps(parameters))
    save("guest-exact-scripts.json", sources)
    deployment = az(["deployment", "group", "create", "-g", control.RG,
                     "--name", "b0-read-" + OUT.name.lower(), "--template-file", str(template),
                     "--parameters", "@" + str(params)], "managed-read-batch")
    # No persistent service/files/routes are changed by the batch source scripts.
    for name in names:
        value = rest(f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{control.RG}"
                     f"/providers/Microsoft.Compute/virtualMachines/{name}/runCommands/guest-b0-{OUT.name.lower()}",
                     f"guest-{name}-actual-get", query={"api-version": "2024-03-01", "$expand": "instanceView"})
        guests[name] = decode(name, value)
    if time.monotonic() - first < 120:
        time.sleep(120 - (time.monotonic() - first))
    for site in ("eu", "us", "jp"):
        routes(site, "snapshot2")
        routes(site, "snapshot2", True)
        rest(f"{BASE}/virtualHubs/hub-{site}", f"hub-{site}-config-after")
    with futures.ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(lambda name: az(["network", "nic", "show-effective-route-table",
                                     "-g", control.RG, "-n", "nic-" + name], f"nic-{name}-routes"), names))
    save("collection-status.json", {"timestampUtc": utc(), "failures": FAILURES,
                                   "elapsedSeconds": time.monotonic() - START,
                                   "configurationMutations": 0, "children": []})
    print(str(OUT), flush=True)


if __name__ == "__main__":
    main()
