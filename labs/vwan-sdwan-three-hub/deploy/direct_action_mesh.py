"""Quota-free, lease-bounded direct WireGuard transport migration."""
import copy
import datetime as dt
import hashlib
import json
import time

import control
import guest
import infra

CORRELATION = "direct-action-mesh-20261015"
OUT = control.ROOT.parent / "show-output" / "direct-action-mesh"
WORK = control.RUNTIME / CORRELATION
BACKUP = "/var/lib/threehub/" + CORRELATION
PRIOR = control.ROOT.parent / "show-output" / "direct-mesh-ports" / "closure-proof.json"


def canonical_rules(rules):
    return {r["name"]: {k: v for k, v in r["properties"].items()
                       if k != "provisioningState" and v != []} for r in rules}


def guest_script(site, mode, expected):
    payload = {"site": site, "links": guest.links(site), "ips": guest.IPS,
               "backup": BACKUP, "mode": mode, "expected": expected}
    return "#!/bin/bash\nset -euo pipefail\npython3 - <<'PY'\n" + (
        "data = " + repr(payload) + "\n" + r'''
import hashlib,json,os,pathlib,re,shlex,shutil,stat,subprocess,time
P=pathlib.Path
def run(args, check=True):
    p=subprocess.run(args,capture_output=True,text=True,timeout=40)
    if check and p.returncode: raise RuntimeError('Command failed: '+args[0])
    return p.stdout
def sha(p): return hashlib.sha256(P(p).read_bytes()).hexdigest()
def identity(p):
    s=P(p).stat()
    return dict(sha256=sha(p),uid=s.st_uid,gid=s.st_gid,mode=stat.S_IMODE(s.st_mode),mtimeNs=s.st_mtime_ns)
def atomic(path,text):
    p=P(path);s=p.stat();n=p.with_name(p.name+'.direct-action-new')
    with n.open('x') as f: f.write(text)
    os.chown(n,s.st_uid,s.st_gid);os.chmod(n,stat.S_IMODE(s.st_mode));os.replace(n,p)
def runtime():
    result={}
    for link in data['links']:
        iface=link['interface']
        result[iface]=dict(endpoint=run(['wg','show',iface,'endpoints']).split()[1],
            listen=int(run(['wg','show',iface,'listen-port']).strip()),
            fwmark=run(['wg','show',iface,'fwmark']).strip(),
            allowedHash=hashlib.sha256(run(['wg','show',iface,'allowed-ips']).encode()).hexdigest())
    return result
bird='/etc/bird/bird.conf';network='/opt/threehub/network.sh';root=P(data['backup'])
before=identity(bird)
assert before['sha256']==data['expected']['sha256'],'Unexpected BIRD baseline'
assert {k:before[k] for k in ('uid','gid','mode','mtimeNs')}==data['expected']['stat'],'Unexpected BIRD identity'
paths=[network]+['/etc/wireguard/'+x['interface']+'.conf' for x in data['links']]
if data['mode']=='apply':
    assert os.geteuid()==0
    assert not root.exists(),'Backup already exists'
    net=P(network).read_text()
    start=net.index('for chain in TH_WG_IN TH_WG_OUT; do\n')
    end=net.index('iptables -t mangle -C FORWARD',start)
    removed=net[start:end]
    assert all(not line or line.startswith(('for chain','  ','done','iptables -t nat')) for line in removed.splitlines())
    assert '-j TH_WG_IN' in removed and '-j TH_WG_OUT' in removed
    configs={}
    for link in data['links']:
        p='/etc/wireguard/'+link['interface']+'.conf';text=P(p).read_text()
        old=data['ips'][link['peer']]+':51820'
        assert re.findall(r'^Endpoint\s*=\s*(.*)$',text,re.M)==[old]
        assert re.findall(r'^ListenPort\s*=\s*(.*)$',text,re.M)==[str(link['port'])]
        assert re.findall(r'^FwMark\s*=\s*(.*)$',text,re.M)==['0x200']
        configs[p]=re.sub(r'^Endpoint\s*=.*$', 'Endpoint = '+data['ips'][link['peer']]+':'+str(link['port']),text,flags=re.M)
    original=runtime()
    root.mkdir(mode=0o700)
    for p in paths:
        target=root/p.lstrip('/');target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        shutil.copy2(p,target)
        os.chown(target,P(p).stat().st_uid,P(p).stat().st_gid)
    (root/'nat.save').write_text(run(['iptables-save','-t','nat']))
    (root/'rules.save').write_text(run(['ip','rule','show']))
    (root/'routes100.save').write_text(run(['ip','route','show','table','100']))
    (root/'manifest.json').write_text(json.dumps(dict(bird=before,runtime=original,files={p:identity(p) for p in paths})))
    os.chmod(root/'manifest.json',0o600)
    atomic(network,net[:start]+net[end:])
    for p,text in configs.items(): atomic(p,text)
    for parent,chain in [('PREROUTING','TH_WG_IN'),('POSTROUTING','TH_WG_OUT')]:
        while subprocess.run(['iptables','-t','nat','-C',parent,'-j',chain],capture_output=True,timeout=10).returncode==0:
            run(['iptables','-t','nat','-D',parent,'-j',chain])
        exists=subprocess.run(['iptables','-t','nat','-S',chain],capture_output=True,timeout=10).returncode==0
        if exists:
            run(['iptables','-t','nat','-F',chain]);run(['iptables','-t','nat','-X',chain])
    for link in data['links']:
        iface=link['interface'];key=run(['wg','show',iface,'peers']).strip()
        assert len(key.split())==1
        run(['wg','set',iface,'peer',key,'endpoint',data['ips'][link['peer']]+':'+str(link['port'])])
    after=runtime()
    for iface,value in after.items():
        assert all(value[k]==original[iface][k] for k in ('listen','fwmark','allowedHash'))
    assert run(['ip','rule','show'])==(root/'rules.save').read_text()
    assert run(['ip','route','show','table','100'])==(root/'routes100.save').read_text()
    nat=run(['iptables-save','-t','nat'])
    keep=lambda t:[l for l in t.splitlines() if not l.startswith('#') and 'TH_WG_' not in l]
    assert keep(nat)==keep((root/'nat.save').read_text()),'Unrelated NAT changed'
elif data['mode']=='restore' and root.exists():
    manifest=json.loads((root/'manifest.json').read_text())
    for p in paths:
        shutil.copy2(root/p.lstrip('/'),p)
        os.chown(p,manifest['files'][p]['uid'],manifest['files'][p]['gid'])
    for chain in ('TH_WG_IN','TH_WG_OUT'):
        if subprocess.run(['iptables','-t','nat','-S',chain],capture_output=True,timeout=10).returncode:
            run(['iptables','-t','nat','-N',chain])
        run(['iptables','-t','nat','-F',chain])
    for line in (root/'nat.save').read_text().splitlines():
        if line.startswith('-A ') and 'TH_WG_' in line:
            args=shlex.split(line)
            if args[1] in ('PREROUTING','POSTROUTING'):
                args[0]='-C'
                if subprocess.run(['iptables','-t','nat',*args],capture_output=True,timeout=10).returncode==0: continue
                args[0]='-A'
            run(['iptables','-t','nat',*args])
    for iface,value in manifest['runtime'].items():
        key=run(['wg','show',iface,'peers']).strip()
        run(['wg','set',iface,'peer',key,'endpoint',value['endpoint']])
    assert runtime()==manifest['runtime']
    for p in paths: assert sha(p)==manifest['files'][p]['sha256']
assert identity(bird)==before,'BIRD identity changed'
protocols={}
for line in run(['birdc','show','protocols']).splitlines():
    if re.match(r'(mesh_|azure_)',line): protocols[line.split()[0]]=line.split()[-1]
units=['threehub-network.service']+['wg-quick@'+x['interface']+'.service' for x in data['links']]
unitstate={u:dict(enabled=run(['systemctl','is-enabled',u],False).strip(),active=run(['systemctl','is-active',u],False).strip()) for u in units}
handshakes={}
for link in data['links']:
    values=run(['wg','show',link['interface'],'latest-handshakes']).split()
    handshakes[link['interface']]=int(values[1])
result=dict(site=data['site'],mode=data['mode'],bird=before,protocols=protocols,
    runtime=runtime(),handshakes=handshakes,now=int(time.time()),units=unitstate,
    natTranslationPresent='TH_WG_' in run(['iptables-save','-t','nat']),
    networkHash=sha(network),backup=root.exists(),
    ikeEstablished=len(re.findall('ESTABLISHED',run(['swanctl','--list-sas']))) if data['site']=='jp' else None)
print('DIRECT_ACTION_COMPLETE '+json.dumps(result,separators=(',',':')))
''' + "\nPY\n")


def nsg_document(actual):
    resources = []
    diffs = {}
    for site in guest.SITES:
        nsg = next(n for n in actual if n["name"] == f"nsg-router-{site}")
        if any(nsg.get("tags", {}).get(k) != v for k, v in control.TAGS.items()):
            raise RuntimeError(f"Refusing unowned NSG: {site}")
        old = nsg["properties"]["securityRules"]
        rules = [{"name": r["name"], "properties": {
            k: copy.deepcopy(v) for k, v in r["properties"].items()
            if k not in ("provisioningState",)}} for r in old]
        added = []
        for link in guest.links(site):
            for direction in ("Inbound", "Outbound"):
                used = {r["properties"]["priority"] for r in rules
                        if r["properties"]["direction"] == direction}
                priority = next(p for p in range(1000, 4000) if p not in used)
                peer, own = guest.IPS[link["peer"]] + "/32", guest.IPS[site] + "/32"
                name = f"direct-link-{link['peer']}-{direction.lower()}"
                if any(r["name"] == name for r in rules):
                    raise RuntimeError("Migration NSG rule already present")
                added.append(infra.rule(name, priority, "Udp",
                    [peer if direction == "Inbound" else own],
                    [own if direction == "Inbound" else peer],
                    [str(link["port"])], direction))
                rules.append(added[-1])
        resources.append({"type": "Microsoft.Network/networkSecurityGroups",
            "apiVersion": infra.API, "name": nsg["name"], "location": nsg["location"],
            "tags": nsg["tags"], "properties": {"securityRules": rules}})
        diffs[site] = {"preservedRuleNames": [r["name"] for r in old], "added": added}
    return infra.template(resources), diffs


def invoke(site, mode, expected, mutation=False):
    path = WORK / f"{mode}-{site}.sh"
    path.write_text(guest_script(site, mode, expected), encoding="utf-8", newline="\n")
    response = control.az(["vm", "run-command", "invoke", "-g", control.RG,
        "-n", f"router-{site}", "--command-id", "RunShellScript",
        "--scripts", "@" + str(path)], f"action-{mode}-{site}",
        mutation=mutation, timeout=600, closure=mode != "apply")
    control.save(OUT / f"{mode}-{site}.json", response)
    messages = "\n".join(v.get("message", "") for v in response.get("value", []))
    marker = "DIRECT_ACTION_COMPLETE "
    if marker not in messages:
        raise RuntimeError(f"{site}: action did not emit COMPLETE")
    result = json.loads(messages.split(marker, 1)[1].splitlines()[0])
    control.save(OUT / f"{mode}-{site}-proof.json", result)
    return result


def main():
    control.LEASE = control.RUNTIME / "direct-action-mesh-20261015.json"
    lease = json.loads(control.LEASE.read_text(encoding="utf-8-sig"))
    if lease.get("toolCallsUsed", 0) or lease.get("mutationsUsed", 0):
        raise RuntimeError("Refusing to replay a started migration")
    lease.setdefault("startedAtUtc", dt.datetime.now(dt.timezone.utc).isoformat())
    control.save(control.LEASE, lease)
    control.guard()
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    prior = json.loads(PRIOR.read_text())
    try:
        nics = control.az(["network", "nic", "list", "-g", control.RG], "action-nics-before")
        for site in guest.SITES:
            nic = next(n for n in nics if n["name"] == f"nic-router-{site}")
            assert any(c["privateIPAddress"] == guest.IPS[site] for c in nic["ipConfigurations"])
            assert nic["networkSecurityGroup"]["id"].endswith(f"/nsg-router-{site}")
        control.save(OUT / "source-hashes.json", {
            name: hashlib.sha256((control.ROOT / name).read_bytes()).hexdigest()
            for name in ("direct_action_mesh.py", "guest.py", "infra.py",
                         "test_guest.py", "test_infra.py", "test_direct_action_mesh.py")})
        actual = control.az(["rest", "--method", "get", "--url",
            f"https://management.azure.com/subscriptions/{control.account_id()}"
            f"/resourceGroups/{control.RG}/providers/Microsoft.Network/networkSecurityGroups"
            f"?api-version={infra.API}"], "action-nsg-before")["value"]
        selected = [n for n in actual if n["name"] in {f"nsg-router-{s}" for s in guest.SITES}]
        control.save(WORK / "nsg-before.json", selected)
        document, diffs = nsg_document(selected)
        control.save(OUT / "nsg-diff.json", diffs)
        path = WORK / "nsg.json"
        control.save(path, document)
        args = ["-g", control.RG, "--template-file", str(path)]
        control.az(["deployment", "group", "validate", *args], "action-nsg-validate", timeout=180)
        control.az(["deployment", "group", "create", *args, "--name", CORRELATION],
                   "action-nsg-apply", mutation=True, timeout=600)
        for site in guest.SITES:
            try:
                invoke(site, "apply", prior[site], mutation=True)
            except Exception:
                # Only one transport restoration is authorized, never a retry.
                invoke(site, "restore", prior[site], mutation=True)
                raise
        print("LIVE threehub-quota-free-direct-mesh | closure | mutations 5/6 | state running | next 180s convergence", flush=True)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            control.guard(False)
            time.sleep(min(5, max(0, deadline - time.monotonic())))
        proofs = {s: invoke(s, "health", prior[s]) for s in guest.SITES}
        final_nsgs = control.az(["rest", "--method", "get", "--url",
            f"https://management.azure.com/subscriptions/{control.account_id()}"
            f"/resourceGroups/{control.RG}/providers/Microsoft.Network/networkSecurityGroups"
            f"?api-version={infra.API}"], "action-nsg-after", closure=True)["value"]
        nsg_checks = {}
        for intended in document["resources"]:
            found = next(n for n in final_nsgs if n["name"] == intended["name"])
            nsg_checks[intended["name"]] = (
                canonical_rules(found["properties"]["securityRules"]) ==
                canonical_rules(intended["properties"]["securityRules"]) and found["tags"] == intended["tags"])
        control.save(OUT / "nsg-verification.json", nsg_checks)
        mesh = sum(v == "Established" for p in proofs.values()
                   for k, v in p["protocols"].items() if k.startswith("mesh_"))
        azure = sum(v == "Established" for p in proofs.values()
                    for k, v in p["protocols"].items() if k.startswith("azure_"))
        checks = {
            "meshEstablished": mesh == 12, "azureEstablished": azure == 6,
            "japanIke": proofs["jp"]["ikeEstablished"] == 2,
            "noTranslation": all(not p["natTranslationPresent"] for p in proofs.values()),
            "recentHandshakes": all(0 <= p["now"] - t <= 180 for p in proofs.values()
                                    for t in p["handshakes"].values()),
            "persistenceReady": all(u["enabled"] == "enabled" and u["active"] == "active"
                                    for p in proofs.values() for u in p["units"].values()),
            "birdUnchanged": all(p["bird"]["sha256"] == prior[s]["sha256"] for s, p in proofs.items()),
            "nsgExactPreservation": all(nsg_checks.values()),
        }
        verdict = {"verdict": "PASS" if all(checks.values()) else "FAIL",
                   "checks": checks, "meshEntriesEstablished": mesh,
                   "azureEntriesEstablished": azure, "transportRetained": True}
        if verdict["verdict"] != "PASS":
            verdict["reason"] = "Acceptance failed: " + ", ".join(k for k, v in checks.items() if not v)
        lease = control.guard(False)
        lease.update(state="completed", verdict=verdict["verdict"], queuedWork=False)
    except Exception as exc:
        lease = json.loads(control.LEASE.read_text())
        verdict = {"verdict": "BLOCKED", "reason": str(exc)}
        lease.update(state="blocked", failure=str(exc), queuedWork=False)
    verdict.update(mutations=lease.get("mutationsUsed", 0), calls=lease.get("toolCallsUsed", 0),
                   children="none", closedAtUtc=dt.datetime.now(dt.timezone.utc).isoformat())
    lease["lastCheckpointUtc"] = verdict["closedAtUtc"]
    control.save(OUT / "verdict.json", verdict)
    control.save(control.LEASE, lease)
    print(json.dumps(verdict), flush=True)


if __name__ == "__main__":
    main()
