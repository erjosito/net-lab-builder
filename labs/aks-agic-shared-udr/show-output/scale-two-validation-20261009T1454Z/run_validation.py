"""Read-only validation runner. Every command is captured with start/end, stdout, stderr, exit code, timeout."""
import argparse, json, os, re, subprocess, datetime as dt

OUT = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(OUT, "..", ".."))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", help="new output directory; it must not already exist")
args = parser.parse_args()
RUN_OUT = os.path.abspath(args.out) if args.out else os.path.join(
    OUT, "run-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
if os.path.exists(RUN_OUT):
    parser.error("output directory already exists; refusing to overwrite captures")
os.makedirs(RUN_OUT)
KC = os.path.join(LAB, "deploy", ".runtime-control", "kubeconfig")
RG = "rg-aks-agic-shared-udr"
POOL = "pool-default-web-80-bp-80"
TIMEOUT = 180
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
LOCAL_PATH = re.compile(r'(?i)[A-Z]:(?:\\\\|\\)Users(?:\\\\|\\)[^\s",;)}]+')
seq = 0

def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

def san(s):
    return LOCAL_PATH.sub("[LOCAL_PATH_REDACTED]", UUID.sub("<uuid>", s or ""))

def run(name, argv, shell_cmd=False):
    global seq
    seq += 1
    if shell_cmd:
        argv = [os.environ.get("ComSpec", "cmd.exe"), "/c"] + argv
    rec = {"seq": seq, "name": name, "mutating": False, "command": san(" ".join(argv)), "startUtc": now()}
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    try:
        o, e = p.communicate(timeout=TIMEOUT)
        rec["timedOut"] = False
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
        o, e = p.communicate()
        rec["timedOut"] = True
    rec.update(endUtc=now(), exitCode=p.returncode, stdout=san(o), stderr=san(e))
    with open(os.path.join(RUN_OUT, "%02d-%s.json" % (seq, name)), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2)
    return rec, o

def az(name, *args):
    return run(name, ["az", *args, "-o", "json", "--only-show-errors"], shell_cmd=True)

def kc(name, *args):
    return run(name, ["kubectl", "--kubeconfig", KC, "--request-timeout=60s", *args])

def jl(o):
    try:
        return json.loads(o)
    except Exception:
        return None

res = {"startUtc": now(), "checks": {}}
c = res["checks"]

r, o = kc("deploy", "get", "deploy", "web", "-n", "default", "-o", "json")
d = jl(o)
if d:
    s, st = d["spec"], d["status"]
    c["deployment"] = {"desired": s.get("replicas"), "ready": st.get("readyReplicas"),
                       "available": st.get("availableReplicas"), "updated": st.get("updatedReplicas")}

r, o = kc("pods", "get", "pods", "-n", "default", "-l", "app=web", "-o", "json")
p = jl(o)
pods = {}
if p:
    for i in p["items"]:
        ready = all(x.get("ready") for x in i["status"].get("containerStatuses", []))
        pods[i["metadata"]["name"]] = {"ip": i["status"].get("podIP"), "phase": i["status"]["phase"],
                                      "ready": ready, "node": i["spec"].get("nodeName")}
c["pods"] = pods

r, o = kc("endpointslices", "get", "endpointslices", "-n", "default",
          "-l", "kubernetes.io/service-name=web", "-o", "json")
e = jl(o)
epips = []
if e:
    for sl in e["items"]:
        for ep in sl.get("endpoints", []):
            if ep.get("conditions", {}).get("ready", True):
                epips += ep["addresses"]
c["endpointSliceIPs"] = sorted(epips)

r, o = az("agw-state", "network", "application-gateway", "show", "-g", RG, "-n", "agw1",
          "--query", "{name:name,provisioningState:provisioningState,operationalState:operationalState}")
c["agw"] = jl(o)

r, o = az("agw-pool", "network", "application-gateway", "address-pool", "show", "-g", RG,
          "--gateway-name", "agw1", "-n", POOL, "--query", "{name:name,backendAddresses:backendAddresses,state:provisioningState}")
pl = jl(o)
c["poolIPs"] = sorted(x.get("ipAddress") for x in pl["backendAddresses"]) if pl else None

r, o = az("agw-backend-health", "network", "application-gateway", "show-backend-health", "-g", RG, "-n", "agw1")
bh = jl(o)
health = []
if bh:
    for bp in bh.get("backendAddressPools", []):
        if not bp["backendAddressPool"]["id"].endswith("/" + POOL):
            continue
        for coll in bp.get("backendHttpSettingsCollection", []):
            sname = coll["backendHttpSettings"]["id"].rsplit("/", 1)[-1]
            for srv in coll.get("servers", []):
                health.append({"settings": sname, "address": srv["address"], "health": srv["health"]})
c["backendHealth"] = health

r, o = kc("agic-pods", "get", "pods", "-n", "kube-system", "-l", "app=ingress-appgw", "-o", "wide")
c["agicPods"] = r["stdout"].strip().splitlines()
r, o = kc("agic-logs", "logs", "-n", "kube-system", "-l", "app=ingress-appgw", "--tail=400", "--timestamps")
c["agicLogLinesMatching"] = [l[:300] for l in san(o).splitlines()
                              if re.search(r"10\.244\.0\.18|Applied|Updating|BEGIN|END|Reconcil", l)][:40]

r, o = az("routes", "network", "route-table", "route", "list", "-g", RG, "--route-table-name", "rt-shared",
          "--query", "sort_by([].{n:name,p:addressPrefix,t:nextHopType,ip:nextHopIpAddress,s:provisioningState},&n)")
c["routes"] = jl(o)
r, o = az("rt-assoc", "network", "route-table", "show", "-g", RG, "-n", "rt-shared", "--query", "{subnets:subnets[].id}")
c["rtSubnets"] = [x.rsplit("/", 1)[-1] for x in (jl(o) or {}).get("subnets", [])]

egress = {}
for name in pods:
    r, o = kc("egress-" + name, "exec", "-n", "default", name, "--", "python", "-c",
              "import urllib.request;print(urllib.request.urlopen('https://api.ipify.org',timeout=20).read().decode())")
    egress[name] = {"exit": r["exitCode"], "ip": o.strip(), "stderr": r["stderr"][-200:]}
c["egress"] = egress

res["endUtc"] = now()
with open(os.path.join(RUN_OUT, "summary.json"), "w", encoding="utf-8") as f:
    json.dump(res, f, indent=2)
print(json.dumps(res, indent=2))
