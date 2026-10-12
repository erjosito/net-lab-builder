"""Read-only Niobe collector; one bounded guest command/chunk per invocation.

Each guest response is limited to 2,800 bytes plus status. Full command output
is paged in memory (rerun for another --chunk; separate samples, NOT an atomic
snapshot); probe truncation is an explicit error, never a false success.
Packet capture is synchronous and capped at 12
packets/20 seconds: use multiple independently labelled windows, NOT as proof
of zero packets unless Niobe independently established capture rendezvous.
No installs, routes, NAT, persistent guest files, or detached processes.
Invocations sharing a lease are serialized by an exclusive runtime lock.
This is not the full concurrent four-stream packet-proof orchestrator; Niobe
must provide that separate rendezvous/transport before claiming design PASS.
"""
import argparse
import json
import shlex
from runtime import RG, Runtime, arguments

VMS = ["vm-hub-test", "vm-hub-nva", "vm-spoke-nva", "vm-workload-probe"]
DESTINATIONS = ["10.40.2.4", "10.40.1.4", "10.60.0.4", "10.60.1.4"]
READS = {
    "addresses": ["ip", "-j", "addr"],
    "rules": ["ip", "-j", "rule"],
    "routes": ["ip", "-j", "route", "show", "table", "all"],
    "nat": ["iptables-save", "-c", "-t", "nat"],
    "filter": ["iptables-save", "-c", "-t", "filter"],
    "listeners": ["ss", "-lnt"],
    "neighbors": ["ip", "-s", "neigh", "show"],
    "sysctl": ["sysctl", "net.ipv4.ip_forward", "net.ipv4.conf.all.rp_filter",
               "net.ipv4.conf.eth0.rp_filter"],
    "bird-protocols": ["birdc", "show", "protocols"],
    "bird-routes": ["birdc", "show", "route"],
    "bird-hash": ["sha256sum", "/etc/bird/bird.conf"],
}


def command_for(kind, destination, direction, source=None):
    if kind == "comparison":
        return ["bash", "-c", (
            "date -u; ip route get " + destination + "; "
            "echo '=== ICMP connectivity ==='; "
            "timeout 12 ping -n -c 5 -W 1 " + destination + "; echo PING_STATUS=$?; "
            "echo '=== ICMP mtr ==='; "
            "timeout 20 mtr -n -r -c 5 --max-ttl 8 " + destination + "; echo MTR_STATUS=$?; "
            "echo '=== ICMP traceroute ==='; "
            "if command -v traceroute >/dev/null; then "
            "timeout 12 traceroute -n -I -m 8 -q 1 -w 1 " + destination + "; echo TRACE_STATUS=$?; "
            "else echo 'NOT_CAPTURED: traceroute unavailable; ICMP mtr captured above'; fi"
        )], 55
    if kind in READS:
        return READS[kind], 15
    if kind == "lookup":
        return ["ip", "route", "get", destination], 10
    if kind == "forwarded-lookup":
        if not source:
            raise ValueError("forwarded-lookup requires --source")
        return ["ip", "route", "get", destination, "from", source, "iif", "eth0"], 10
    if kind == "ping":
        return ["ping", "-n", "-c", "5", "-W", "1", destination], 12
    if kind == "tcp":
        return ["bash", "-c", f"exec 3<>/dev/tcp/{destination}/22; head -c 100 <&3"], 4
    if kind.startswith("mtr-"):
        return ["mtr", "-n", "-r", "-c", "5", "--max-ttl", "8",
                *([] if kind == "mtr-icmp" else ["--tcp", "--port", "22"]),
                destination], 20
    if kind.startswith("trace-"):
        return ["traceroute", "-n", "-m", "8", "-q", "1", "-w", "1",
                *(["-I"] if kind == "trace-icmp" else ["-T", "-p", "22"]), destination], 20
    if kind == "packets":
        return ["tcpdump", "-nn", "-tttt", "-l", "-i", "eth0", "-Q", direction, "-c", "12",
                "(host 10.40.2.4 and host 10.60.1.4) and (icmp or tcp port 22)"], 20
    raise ValueError("Unsupported collector")


def guest_script(command, seconds, chunk):
    # Python is only used as an in-memory bounded output transport, not installed.
    code = f"""
import json, os, signal, shutil, subprocess, sys
cmd = {command!r}
if not shutil.which(cmd[0]):
    print('ERROR missing binary: ' + cmd[0]); print('COMMAND_STATUS=127'); sys.exit(127)
p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
try:
    data, _ = p.communicate(timeout={seconds})
    status = p.returncode
except subprocess.TimeoutExpired:
    os.killpg(p.pid, signal.SIGKILL)
    data, _ = p.communicate(timeout=3)
    status = 124
offset = {chunk} * 2800
print(json.dumps({{'command': cmd, 'status': status, 'bytes': len(data),
                  'chunk': {chunk}, 'chunks': max(1, (len(data)+2799)//2800)}}))
print(data[offset:offset+2800].decode('utf-8', errors='replace'))
if len(data) > 2800:
    print('ERROR OUTPUT_PAGED: not a complete atomic snapshot; never treat as full packet proof')
print('COMMAND_STATUS=' + str(status))
print('UDR_STATUS=0')
"""
    return ("command -v python3 >/dev/null 2>&1 || { echo 'ERROR missing binary: python3'; exit 127; }\n"
            + "python3 -c " + shlex.quote(code))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", choices=["S0", "S1", "A", "B", "A2"], required=True)
    p.add_argument("--vm", choices=VMS, required=True)
    p.add_argument("--kind", choices=[*READS, "effective-routes", "effective-nsg", "lookup",
                   "forwarded-lookup", "ping", "tcp", "mtr-icmp", "mtr-tcp",
                   "trace-icmp", "trace-tcp", "packets", "comparison"], required=True)
    p.add_argument("--destination", choices=DESTINATIONS)
    p.add_argument("--source", choices=DESTINATIONS)
    p.add_argument("--direction", choices=["in", "out"], default="in")
    p.add_argument("--chunk", type=int, default=0)
    p.add_argument("--sample", type=int, default=1, help="Distinct evidence label, e.g. TCP samples 1/2/3")
    arguments(p)
    a = p.parse_args()
    if a.chunk < 0 or a.sample < 1:
        p.error("chunk >= 0 and sample >= 1 required")
    r = Runtime(a, "Niobe")
    label = f"{a.phase}-{a.vm}-{a.kind}-{a.direction}-{a.sample}-{a.chunk}"
    if a.kind.startswith("effective-"):
        nic = a.vm.replace("vm-", "nic-", 1)
        verb = "show-effective-route-table" if a.kind == "effective-routes" else "list-effective-nsg"
        result = r.command(label, ["network", "nic", verb, "-g", RG, "-n", nic])
        print(json.dumps(result))
        return
    if a.kind not in READS and a.kind != "packets" and not a.destination:
        p.error("Probe/lookup requires --destination")
    command, seconds = command_for(a.kind, a.destination, a.direction, a.source)
    text = r.guest(label, a.vm, guest_script(command, seconds, a.chunk))
    print(text)


if __name__ == "__main__":
    main()
