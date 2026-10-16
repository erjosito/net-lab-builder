"""Protected, two-phase guest deployment for the locked three-hub design."""
import argparse
import base64
import ipaddress
import json
import pathlib

import control
from infra import DC_PREFIXES, REGIONS, SPOKE_PREFIXES, VMS, template

SITES = ("eu", "us", "jp", "cn")
ASNS = dict(zip(SITES, (65011, 65012, 65013, 65014)))
DC = dict(zip(SITES, DC_PREFIXES))
IPS = dict(zip(SITES, ("10.210.0.4", "10.220.0.4", "10.130.0.4", "10.140.0.4")))
PAIRS = (("eu", "us"), ("eu", "jp"), ("eu", "cn"),
         ("us", "jp"), ("us", "cn"), ("jp", "cn"))
INSTALL = "/var/lib/threehub"


def links(site):
    result = []
    for index, pair in enumerate(PAIRS):
        if site not in pair:
            continue
        first = site == pair[0]
        network = ipaddress.ip_network(f"172.31.0.{index * 4}/30")
        peer = pair[1] if first else pair[0]
        result.append({"peer": peer, "interface": f"wg{pair[0]}{pair[1]}",
                       "local": str(network[1 if first else 2]),
                       "remote": str(network[2 if first else 1]),
                       "port": 51821 + index})
    return result


def bird(site, hubs, vpn):
    asn = ASNS[site]
    own = DC[site]
    data = ", ".join(DC_PREFIXES + SPOKE_PREFIXES)
    spokes = ", ".join(SPOKE_PREFIXES)
    pins = [ip for peer, ip in IPS.items() if peer != site]
    azure = hubs.get(site, []) if site in ("eu", "us") else (
        [slot["bgp"] for slot in vpn] if site == "jp" else [])
    pins += azure if site in ("eu", "us") else []
    underlay = "\n".join(f"  route {ip}/32 via __GATEWAY__;" for ip in pins)
    if site == "jp":
        underlay += "\n" + "\n".join(
            f'  route {slot["bgp"]}/32 via "xfrm{slot["id"]}";' for slot in vpn)
    own_hop = 'via "__NIC__"' if site in ("jp", "cn") else "via __GATEWAY__"
    text = f"""log syslog all;
router id {IPS[site]};
ipv4 table underlay4;
ipv4 table lab4;
protocol device devices {{ scan time 10; }}
protocol direct connected {{
  ipv4 {{ table underlay4; }};
  interface "__NIC__", "wg*";
}}
protocol static control_pins {{
  ipv4 {{ table underlay4; }};
{underlay}
}}
protocol static own_dc {{
  ipv4 {{ table lab4; }};
  route {own} {own_hop};
}}
function regional_preference(int ingress) {{
  if (net = 10.10.0.0/24 && ingress = 65011) ||
     (net = 10.20.0.0/24 && ingress = 65012) ||
     (net = 10.30.0.0/24 && ingress = 65013) then
    bgp_local_pref = 300;
  else bgp_local_pref = 100;
}}
filter azure_export {{
  if net ~ [{", ".join(DC_PREFIXES)}] &&
     (proto = "own_dc" || proto ~ "mesh_*") then accept;
  reject;
}}
filter mesh_export {{
  if net = {own} && proto = "own_dc" then accept;
  if net ~ [{spokes}] && proto ~ "azure_*" then {{
    bgp_community.add(({asn}, 1));
    accept;
  }}
  reject;
}}
protocol kernel kernel_lab {{
  kernel table 254;
  metric 80;
  ipv4 {{
    table lab4;
    import none;
    export filter {{
      if net = {own} && {1 if site in ("jp", "cn") else 0} = 1 then reject;
      if net ~ [{data}] then accept;
      reject;
    }};
  }};
}}
"""
    for link in links(site):
        peer = link["peer"]
        allowed_spokes = f"""if net ~ [{spokes}] then {{
        bgp_community = -empty-;
        bgp_community.add(({ASNS[peer]}, 1));
        regional_preference({ASNS[peer]});
        accept;
      }}""" if peer != "cn" else ""
        text += f"""
protocol bgp mesh_{peer} {{
  local {link["local"]} as {asn};
  neighbor {link["remote"]} as {ASNS[peer]};
  multihop 2;
  hold time 180;
  keepalive time 60;
  ipv4 {{
    table lab4;
    igp table underlay4;
    gateway recursive;
    next hop self;
    import filter {{
      bgp_next_hop = {link["remote"]};
      if net = {DC[peer]} then {{ bgp_community = -empty-; accept; }}
      {allowed_spokes}
      reject;
    }};
    export filter mesh_export;
  }};
}}
"""
    for index, peer in enumerate(azure):
        source = "169.254.21.1" if site == "jp" else IPS[site]
        hop = peer if site == "jp" else "__GATEWAY__"
        text += f"""
protocol bgp azure_{index} {{
  local {source} as {asn};
  neighbor {peer} as 65515;
  multihop 10;
  hold time 180;
  keepalive time 60;
  ipv4 {{
    table lab4;
    igp table underlay4;
    gateway recursive;
    import filter {{
      if net ~ [{spokes}] then {{
        bgp_next_hop = {hop};
        bgp_community = -empty-;
        bgp_community.add(({asn}, 1));
        regional_preference({asn});
        accept;
      }}
      reject;
    }};
    export filter azure_export;
  }};
}}
"""
    return text


def unit(description, command, after="network-online.target", requires=""):
    return f"""[Unit]
Description={description}
Wants=network-online.target
After={after}
{f"Requires={requires}" if requires else ""}
[Service]
Type=oneshot
ExecStart={command}
RemainAfterExit=yes
TimeoutStartSec=180
[Install]
WantedBy=multi-user.target
"""


def swan(vpn, public_ip, psk):
    text = "connections {\n"
    for index, slot in enumerate(vpn):
        text += f"""  vng{index} {{
    version = 2
    local_addrs = 10.130.0.4
    remote_addrs = {slot["public"]}
    proposals = aes256-sha256-modp2048
    encap = yes
    dpd_delay = 30s
    local {{ auth = psk
      id = {public_ip}
    }}
    remote {{ auth = psk
      id = {slot["public"]}
    }}
    children {{
      s2s{index} {{
        local_ts = 0.0.0.0/0
        remote_ts = 0.0.0.0/0
        esp_proposals = aes256-sha256-modp2048
        if_id_in = {slot["id"]}
        if_id_out = {slot["id"]}
        set_mark_out = 0x200
        start_action = start
        close_action = start
        dpd_action = restart
        life_time = 1h
      }}
    }}
  }}
"""
    return text + f"""}}
secrets {{
  ike-japan {{
    id = {public_ip}
    secret = "{psk}"
  }}
}}
"""


def network(site, hubs, vpn):
    text = """#!/bin/bash
set -euo pipefail
NIC=$(ip -4 route show default | awk 'NR==1 {print $5}')
GATEWAY=$(ip -4 route show default | awk 'NR==1 {print $3}')
test -n "$NIC" && test -n "$GATEWAY"
sysctl -q -w net.ipv4.ip_forward=1 net.ipv4.conf.all.rp_filter=0 net.ipv4.conf.default.rp_filter=0
for f in /proc/sys/net/ipv4/conf/*/rp_filter; do echo 0 > "$f"; done
ip route replace table 100 default via "$GATEWAY" dev "$NIC" onlink
if ! ip rule show | grep -q 'fwmark 0x200 lookup 100'; then
  ip rule add pref 100 fwmark 0x200 lookup 100
fi
"""
    # A router .4 is also CN's workload address: pin outer transport, not data.
    for peer, ip in IPS.items():
        if peer != site:
            text += f'ip route replace table 100 {ip}/32 via "$GATEWAY" dev "$NIC" onlink\n'
    pins = hubs.get(site, []) if site in ("eu", "us") else []
    if site == "jp":
        pins += [slot["public"] for slot in vpn]
    for ip in pins:
        text += f'ip route replace {ip}/32 via "$GATEWAY" dev "$NIC"\n'
    text += """iptables -t mangle -C FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1340 2>/dev/null || iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1340
"""
    if site == "jp":
        text += "ip address replace 169.254.21.1/32 dev lo\n"
        for slot in vpn:
            iface = f"xfrm{slot['id']}"
            text += f"""if ! ip link show {iface} >/dev/null 2>&1; then ip link add {iface} type xfrm dev "$NIC" if_id {slot["id"]}; fi
ip link set {iface} mtu 1380 up
ip route replace {slot["bgp"]}/32 dev {iface} src 169.254.21.1
"""
    return text


def router_files(site, hubs, vpn, keys, psk, jp_public):
    files = {
        "/etc/bird/bird.conf": bird(site, hubs, vpn),
        "/opt/threehub/network.sh": network(site, hubs, vpn),
        "/etc/systemd/system/threehub-network.service": unit(
            "Threehub underlay pins and forwarding", "/opt/threehub/network.sh"),
        "/etc/sysctl.d/91-threehub.conf": (
            "net.ipv4.ip_forward=1\nnet.ipv4.conf.all.rp_filter=0\n"
            "net.ipv4.conf.default.rp_filter=0\n"),
    }
    wg_units = []
    for link in links(site):
        name = link["interface"]
        peer = link["peer"]
        files[f"/etc/wireguard/{name}.conf"] = f"""[Interface]
Address = {link["local"]}/30
PrivateKey = {keys[site]["private"]}
ListenPort = {link["port"]}
FwMark = 0x200
MTU = 1380
Table = off
[Peer]
PublicKey = {keys[peer]["public"]}
Endpoint = {IPS[peer]}:{link["port"]}
AllowedIPs = {link["remote"]}/32, {DC[peer]}, {", ".join(SPOKE_PREFIXES)}
PersistentKeepalive = 25
"""
        wg_units.append(f"wg-quick@{name}.service")
        files[f"/etc/systemd/system/wg-quick@{name}.service.d/threehub.conf"] = (
            "[Unit]\nRequires=threehub-network.service\nAfter=threehub-network.service\n")
    before_bird = ["threehub-network.service", *wg_units]
    if site == "jp":
        files["/etc/swanctl/swanctl.conf"] = swan(vpn, jp_public, psk)
        files["/etc/strongswan.d/threehub.conf"] = """charon {
  plugins {
    kernel-netlink {
      install_routes = no
      install_routes_xfrmi = no
    }
    socket-default { fwmark = 0x200 }
  }
}
"""
        files["/opt/threehub/ipsec.sh"] = """#!/bin/bash
set -euo pipefail
swanctl --load-all
swanctl --initiate --ike vng0 --child s2s0 --timeout 45
swanctl --initiate --ike vng1 --child s2s1 --timeout 45
"""
        files["/etc/systemd/system/threehub-ipsec.service"] = unit(
            "Threehub persistent Japan VPN", "/opt/threehub/ipsec.sh",
            "threehub-network.service strongswan.service",
            "threehub-network.service strongswan.service")
        before_bird.append("threehub-ipsec.service")
    files["/etc/systemd/system/bird.service.d/threehub.conf"] = (
        "[Unit]\nRequires=" + " ".join(before_bird) + "\nAfter=" + " ".join(before_bird) +
        "\n[Service]\nExecStartPre=/usr/sbin/bird -p -c /etc/bird/bird.conf\n")
    return files


def listener_files():
    return {
        "/etc/systemd/system/lab-http.service": """[Unit]
Description=Lab private TCP probe listener
After=network-online.target
[Service]
User=nobody
ExecStart=/usr/bin/python3 -m http.server 5201 --directory /var/lib/lab-http
Restart=on-failure
[Install]
WantedBy=multi-user.target
""",
        "/var/lib/lab-http/index.html": "threehub-guest-ready\n",
    }


def stage_script(files, site=None):
    payload = base64.b64encode(json.dumps(files).encode()).decode()
    packages = "bird2 wireguard-tools" if site else ""
    if site == "jp":
        packages += " strongswan-swanctl charon-systemd libstrongswan-extra-plugins"
    return f"""#!/bin/bash
set -euo pipefail
umask 077
mkdir -p {INSTALL}
exec > >(tee {INSTALL}/stage.log) 2>&1
trap 'echo STAGE_FAILED_LINE_$LINENO' ERR
timeout 240 cloud-init status --wait --long
echo CLOUD_INIT_READY
if ! dpkg-query -W -f='${{Status}}\\n' {packages or "python3"} 2>/dev/null | grep -v '^install ok installed$' | grep -q . && dpkg-query -W {packages or "python3"} >/dev/null 2>&1; then
  echo PACKAGES_READY
else
  export DEBIAN_FRONTEND=noninteractive
  timeout 240 apt-get -qq update
  timeout 360 apt-get -qq -o DPkg::Lock::Timeout=120 install -y {packages or "python3"}
fi
python3 - <<'PY'
import base64,json,pathlib,subprocess,tarfile,re
files=json.loads(base64.b64decode('{payload}'))
root=pathlib.Path('{INSTALL}')
if not (root/'backup.json').exists():
    existing=[p for p in files if pathlib.Path(p).exists()]
    with tarfile.open(root/'backup.tar', 'w') as archive:
        for p in existing: archive.add(p,arcname=p.lstrip('/'),recursive=False)
    services=['bird','lab-http','strongswan']
    states={{s:subprocess.run(['systemctl','is-enabled',s],capture_output=True,text=True).stdout.strip() for s in services}}
    (root/'backup.json').write_text(json.dumps({{'files':list(files),'existing':existing,'services':states}}))
    (root/'iptables.save').write_bytes(subprocess.check_output(['iptables-save']))
    (root/'routes.save').write_bytes(subprocess.check_output(['ip','route','save']))
    pins=[]
    for content in files.values():
        pins.extend(re.findall(r'ip route replace ([0-9./]+)',content))
    (root/'pins.json').write_text(json.dumps(sorted(set(pins))))
    (root/'original-links.json').write_text(subprocess.check_output(['ip','-j','link'],text=True))
    (root/'sysctl.json').write_text(json.dumps({{k:pathlib.Path('/proc/sys/'+k.replace('.','/')).read_text().strip() for k in ['net.ipv4.ip_forward','net.ipv4.conf.all.rp_filter','net.ipv4.conf.default.rp_filter']}}))
route=subprocess.check_output(['ip','-j','-4','route','show','default'],text=True)
default=json.loads(route)[0]
for path,content in files.items():
    content=content.replace('__NIC__',default['dev']).replace('__GATEWAY__',default['gateway'])
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
    p.chmod(0o644 if path.startswith('/var/lib/lab-http/') else (0o700 if path.endswith('.sh') else 0o600))
(root/'files.json').write_text(json.dumps(list(files)))
PY
{"bird -p -c /etc/bird/bird.conf" if site else "python3 --version"}
for f in /opt/threehub/*.sh; do if test -f "$f"; then bash -n "$f"; fi; done
systemctl daemon-reload
echo STAGE_OK
"""


def activate_script(site=None):
    commands = ["systemctl enable --now lab-http.service"]
    if site:
        commands += ["systemctl enable --now threehub-network.service"]
        commands += [f"systemctl enable --now wg-quick@{link['interface']}.service"
                     for link in links(site)]
        if site == "jp":
            commands += ["if systemctl list-unit-files strongswan-starter.service --no-legend | grep -q '^strongswan-starter.service'; then\n"
                         "  systemctl disable --now strongswan-starter.service\nfi",
                         "systemctl enable --now strongswan.service",
                         "systemctl enable --now threehub-ipsec.service"]
        commands += ["bird -p -c /etc/bird/bird.conf", "systemctl enable bird",
                     "systemctl restart bird"]
    if site == "jp-probe":
        raise ValueError("Probe routes belong in files, not router activation")
    return """#!/bin/bash
set -euo pipefail
exec > >(tee /var/lib/threehub/activate.log) 2>&1
trap 'echo ACTIVATE_FAILED_LINE_$LINENO' ERR
""" + "\n".join(commands) + """
echo SERVICES_PERSISTENT
curl -fsS --max-time 5 --retry 3 --retry-connrefused --retry-delay 1 --retry-max-time 15 http://127.0.0.1:5201/
echo ACTIVATE_OK
"""


def write_final_files(files):
    payload = base64.b64encode(json.dumps(files).encode()).decode()
    return f"""python3 - <<'PY'
import base64,hashlib,json,pathlib,subprocess,tarfile
files=json.loads(base64.b64decode('{payload}'))
root=pathlib.Path('{INSTALL}')
backup_names=['backup.json','backup.tar','routes.save','iptables.save','pins.json','original-links.json','sysctl.json']
backup_hashes={{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in backup_names}}
default=json.loads(subprocess.check_output(['ip','-j','-4','route','show','default'],text=True))[0]
final_hashes={{}}
for path,content in files.items():
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    if path.startswith('/var/lib/lab-http/'): p.parent.chmod(0o755)
    p.write_text(content.replace('__NIC__',default['dev']).replace('__GATEWAY__',default['gateway']))
    p.chmod(0o644 if path.startswith('/var/lib/lab-http/') else (0o700 if path.endswith('.sh') else 0o600))
    final_hashes[path]=hashlib.sha256(p.read_bytes()).hexdigest()
assert backup_hashes=={{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in backup_names}}
(root/'activation-files.json').write_text(json.dumps({{'files':final_hashes,'originalBackups':backup_hashes}}))
(root/'activation-files.json').chmod(0o600)
with tarfile.open(root/'activation-files.tar','w') as archive:
    for path in files: archive.add(path,arcname=path.lstrip('/'),recursive=False)
(root/'activation-files.tar').chmod(0o600)
PY
for f in /opt/threehub/*.sh; do if test -f "$f"; then bash -n "$f"; fi; done
systemctl daemon-reload
"""


def activation_proof(site=None, jp_probe=False):
    units = ["lab-http"]
    if site:
        units += ["bird", "threehub-network"]
        units += [f"wg-quick@{link['interface']}" for link in links(site)]
        if site == "jp":
            units += ["strongswan", "threehub-ipsec"]
    if jp_probe:
        units += ["threehub-probe"]
    return f"""python3 - <<'PY'
import hashlib,json,pathlib,subprocess,time
root=pathlib.Path('{INSTALL}')
manifest=json.loads((root/'activation-files.json').read_text())
for path,expected in manifest['files'].items():
    assert hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()==expected,path
for name,expected in manifest['originalBackups'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected,name
services={{}}
for name in {units!r}:
    enabled=subprocess.check_output(['systemctl','is-enabled',name],text=True).strip()
    active=subprocess.check_output(['systemctl','is-active',name],text=True).strip()
    assert enabled=='enabled' and active=='active',name
    services[name]={{'enabled':enabled,'active':active}}
proof={{'activation':'PASS','filesChecksumVerified':True,'originalBackupsPreserved':True,
        'filesManifestSha256':hashlib.sha256((root/'activation-files.json').read_bytes()).hexdigest(),
        'services':services,'protocols':{{}},'routes':{{}}}}
if {bool(site)!r}:
    deadline=time.monotonic()+120
    while True:
        protocols=subprocess.check_output(['birdc','show','protocols'],text=True)
        peers={{}}
        for line in protocols.splitlines():
            fields=line.split()
            if len(fields)>=6 and fields[1]=='BGP': peers[fields[0]]=' '.join(fields[5:])
        if sum(v=='Established' for v in peers.values())=={3 if site == "cn" else 5} or time.monotonic()>=deadline:
            break
        time.sleep(5)
    proof['protocols']=peers
    proof['established']=sum(v=='Established' for v in peers.values())
    proof['expectedPeers']={3 if site == "cn" else 5}
    (root/'activation-bird-protocols.txt').write_text(protocols)
    (root/'activation-bird-routes.txt').write_text(subprocess.check_output(['birdc','show','route','table','lab4'],text=True))
    for target in ['10.110.0.10','10.120.0.10','10.130.0.10','10.140.0.4']:
        proof['routes'][target]=subprocess.check_output(['ip','route','get',target],text=True).splitlines()[0]
    (root/'activation-routes.json').write_text(subprocess.check_output(['ip','-j','route','show','table','all'],text=True))
    if {site == "jp"!r}:
        (root/'activation-ipsec.txt').write_text(subprocess.check_output(['swanctl','--list-sas'],text=True))
(root/'activation-proof.json').write_text(json.dumps(proof))
(root/'activation-proof.json').chmod(0o600)
(root/'activation-routes.save').write_bytes(subprocess.check_output(['ip','route','save']))
(root/'activation-routes.save').chmod(0o600)
print(json.dumps(proof))
PY
"""


def smoke_script(site=None):
    text = """#!/bin/bash
set -euo pipefail
systemctl is-enabled lab-http
systemctl is-active lab-http
curl -fsS --max-time 5 http://127.0.0.1:5201/
"""
    if site:
        count = 3 if site == "cn" else 5
        text += f"""bird -p -c /etc/bird/bird.conf
systemctl is-enabled bird threehub-network
systemctl is-active bird threehub-network
birdc show protocols
birdc show route table lab4
test "$(birdc show protocols | grep -c Established)" -eq {count}
"""
        for link in links(site):
            target = str(ipaddress.ip_network(DC[link["peer"]])[
                4 if link["peer"] == "cn" else 10])
            text += f"""systemctl is-enabled wg-quick@{link["interface"]}
systemctl is-active wg-quick@{link["interface"]}
ip route get {IPS[link["peer"]]}
ip route get {IPS[link["peer"]]} mark 0x200
ip route get {target}
"""
        for index in range(2 if site != "cn" else 0):
            text += f"birdc show route export azure_{index}\n"
        if site == "jp":
            text += "swanctl --list-sas\nip -d link show xfrm41\nip -d link show xfrm42\n"
    return text + "echo SMOKE_OK\n"


def restore_script(site=None, jp_probe=False):
    units = ["lab-http"]
    if site:
        units += ["bird", "threehub-network"]
        units += [f"wg-quick@{link['interface']}" for link in links(site)]
        if site == "jp":
            units += ["threehub-ipsec", "strongswan"]
    if jp_probe:
        units += ["threehub-probe"]
    return """#!/bin/bash
set -euo pipefail
test -f /var/lib/threehub/backup.json
""" + "\n".join(
        f"if systemctl cat {name} >/dev/null 2>&1; then systemctl disable --now {name}; fi"
        for name in units) + """
python3 - <<'PY'
import hashlib,json,pathlib,subprocess,tarfile
root=pathlib.Path('/var/lib/threehub'); backup=json.loads((root/'backup.json').read_text())
for prefix in json.loads((root/'pins.json').read_text()):
    route=subprocess.check_output(['ip','route','show',prefix],text=True)
    if route: subprocess.run(['ip','route','del',prefix],check=True)
links={x['ifname'] for x in json.loads((root/'original-links.json').read_text())}
for name in ['xfrm41','xfrm42']:
    present=subprocess.run(['ip','link','show',name],capture_output=True).returncode==0
    if present and name not in links: subprocess.run(['ip','link','del',name],check=True)
marked=subprocess.check_output(['ip','rule','show'],text=True)
if 'fwmark 0x200 lookup 100' in marked:
    subprocess.run(['ip','rule','del','pref','100','fwmark','0x200','lookup','100'],check=True)
    subprocess.run(['ip','route','flush','table','100'],check=True)
addresses=subprocess.check_output(['ip','-4','address','show','dev','lo'],text=True)
if '169.254.21.1/32' in addresses:
    subprocess.run(['ip','address','del','169.254.21.1/32','dev','lo'],check=True)
for path in backup['files']:
    p=pathlib.Path(path)
    if p.exists(): p.unlink()
with tarfile.open(root/'backup.tar') as archive:
    archive.extractall('/')
    for member in archive.getmembers():
        expected=archive.extractfile(member).read()
        actual=pathlib.Path('/'+member.name).read_bytes()
        if hashlib.sha256(expected).digest()!=hashlib.sha256(actual).digest():
            raise RuntimeError('Restore checksum mismatch: '+member.name)
subprocess.run(['iptables-restore'],input=(root/'iptables.save').read_bytes(),check=True)
for k,v in json.loads((root/'sysctl.json').read_text()).items():
    subprocess.run(['sysctl','-q','-w',k+'='+v],check=True)
with (root/'routes.save').open('rb') as saved_routes:
    subprocess.run(['ip','route','restore'],stdin=saved_routes,check=True)
subprocess.run(['systemctl','daemon-reload'],check=True)
for s,state in backup['services'].items():
    if state=='enabled': subprocess.run(['systemctl','enable','--now',s],check=True)
services={}
for s,state in backup['services'].items():
    enabled=subprocess.run(['systemctl','is-enabled',s],capture_output=True,text=True)
    active=subprocess.run(['systemctl','is-active',s],capture_output=True,text=True)
    if enabled.returncode not in (0,1,4) or active.returncode not in (0,3,4):
        raise RuntimeError('Service state query failed: '+s)
    if enabled.stdout.strip()!=state:
        raise RuntimeError('Restored service enablement mismatch: '+s)
    if state=='enabled' and active.stdout.strip()!='active':
        raise RuntimeError('Restored enabled service is not active: '+s)
    services[s]={'enabled':enabled.stdout.strip(),'active':active.stdout.strip(),
                 'activeStateRecorded':False}
with (root/'routes.save').open('rb') as saved_routes:
    expected_routes=subprocess.check_output(['ip','route','showdump'],stdin=saved_routes,text=True)
restored_routes=root/'routes-restored.save'
restored_routes.write_bytes(subprocess.check_output(['ip','route','save']))
restored_routes.chmod(0o600)
with restored_routes.open('rb') as current_routes:
    actual_routes=subprocess.check_output(['ip','route','showdump'],stdin=current_routes,text=True)
if sorted(expected_routes.splitlines())!=sorted(actual_routes.splitlines()):
    raise RuntimeError('Restored route snapshot mismatch')
print(json.dumps({'restore':'PASS','filesChecksumVerified':True,
                  'routesSnapshotVerified':True,'services':services}))
PY
echo RESTORE_FILES_OK
"""


def bindings():
    snapshot = json.loads((control.ROOT.parent / "infrastructure-handoff.json").read_text())
    hubs = {site: value["properties"]["virtualRouterIps"] for site, value in json.loads(
        (control.RUNTIME / "hub-bindings-discovered.json").read_text()).items()}
    gateway = json.loads((control.RUNTIME / "gateway-final-resource.stdout.json").read_text())
    settings = gateway["properties"]["bgpSettings"]["bgpPeeringAddresses"]
    slots = []
    for index, item in enumerate(settings):
        custom = item["customBgpIpAddresses"]
        if len(custom) != 1 or custom[0] not in ("169.254.21.2", "169.254.21.6"):
            raise ValueError("Unexpected live custom BGP binding")
        public = [ip for ip in item["tunnelIpAddresses"]
                  if not ipaddress.ip_address(ip).is_private]
        if len(public) != 1:
            raise ValueError("Expected exactly one public IKE address per live instance")
        slots.append({"bgp": custom[0], "public": public[0],
                      "id": 41 if custom[0] == "169.254.21.2" else 42,
                      "instance": item["ipconfigurationId"]})
    if len(slots) != 2:
        raise ValueError("Two actual VPN instances required")
    return snapshot, hubs, sorted(slots, key=lambda slot: slot["id"])


def keys():
    path = control.RUNTIME / "guest.keys.json"
    if path.exists():
        return json.loads(path.read_text())
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    result = {}
    for site in SITES:
        key = X25519PrivateKey.generate()
        result[site] = {"private": base64.b64encode(key.private_bytes_raw()).decode(),
                        "public": base64.b64encode(key.public_key().public_bytes_raw()).decode()}
    control.save(path, result)
    return result


def scripts(phase):
    snapshot, hubs, vpn = bindings()
    psk = json.loads((control.RUNTIME / "vpn.parameters.json").read_text())[
        "parameters"]["vpnSharedKey"]["value"]
    keymap = keys()
    result = {}
    for name, _, _, router in VMS:
        site = name.removeprefix("router-") if router else None
        if phase == "stage":
            files = listener_files()
            if router:
                files.update(router_files(site, hubs, vpn, keymap, psk,
                             snapshot["runtimeEndpoints"]["router-jp"]["publicIp"]))
            if name == "probe-dc-jp":
                routes = "\n".join(f"ip route replace {p} via 10.130.0.4"
                                   for p in DC_PREFIXES + SPOKE_PREFIXES if p != DC["jp"])
                files["/opt/threehub/probe-routes.sh"] = "#!/bin/bash\nset -euo pipefail\n" + routes + "\n"
                files["/etc/systemd/system/threehub-probe.service"] = unit(
                    "Japan probe anti-bypass routes", "/opt/threehub/probe-routes.sh")
            result[name] = stage_script(files, site)
        elif phase == "activate":
            result[name] = activate_script(site)
            files = listener_files()
            if router:
                files.update(router_files(site, hubs, vpn, keymap, psk,
                             snapshot["runtimeEndpoints"]["router-jp"]["publicIp"]))
            if name == "probe-dc-jp":
                routes = "\n".join(f"ip route replace {p} via 10.130.0.4"
                                   for p in DC_PREFIXES + SPOKE_PREFIXES if p != DC["jp"])
                files["/opt/threehub/probe-routes.sh"] = "#!/bin/bash\nset -euo pipefail\n" + routes + "\n"
                files["/etc/systemd/system/threehub-probe.service"] = unit(
                    "Japan probe anti-bypass routes", "/opt/threehub/probe-routes.sh")
                result[name] = result[name].replace(
                    "echo SERVICES_PERSISTENT",
                    "systemctl enable --now threehub-probe.service\necho SERVICES_PERSISTENT")
            result[name] = result[name].replace(
                "systemctl enable --now lab-http.service",
                write_final_files(files) + "\nsystemctl enable --now lab-http.service\n"
                "systemctl restart lab-http.service", 1)
            result[name] = result[name].replace(
                "echo ACTIVATE_OK", activation_proof(site, name == "probe-dc-jp") + "echo ACTIVATE_OK")
        elif phase == "smoke":
            result[name] = smoke_script(site)
        elif phase == "restore":
            result[name] = restore_script(site, name == "probe-dc-jp")
        else:
            raise ValueError(phase)
    return result


def managed_template(sources, phase):
    resources = []
    params = {}
    for name, script in sources.items():
        param = name.replace("-", "_")
        params[param] = {"type": "secureString"}
        region = "us" if name.endswith("-us") else ("eu" if name.endswith("-eu") else "jp")
        resources.append({
            "type": "Microsoft.Compute/virtualMachines/runCommands",
            "apiVersion": "2024-07-01", "name": f"{name}/guest-{phase}",
            "location": REGIONS[region],
            "properties": {"source": {"script": f"[parameters('{param}')]"},
                           "timeoutInSeconds": 900, "asyncExecution": False,
                           "treatFailureAsDeploymentFailure": True}})
    values = {name.replace("-", "_"): {"value": script} for name, script in sources.items()}
    return template(resources, params), {"parameters": values}


def generate(phase):
    document, parameters = managed_template(scripts(phase), phase)
    path = control.RUNTIME / f"guest-{phase}.json"
    param_path = control.RUNTIME / f"guest-{phase}.parameters.json"
    control.save(path, document)
    control.save(param_path, parameters)
    return path, param_path


def submit(phase):
    closure = phase == "restore"
    control.guard(not closure)
    path, params = generate(phase)
    args = ["-g", control.RG, "--template-file", str(path), "--parameters", "@" + str(params)]
    control.az(["deployment", "group", "what-if", *args, "--no-pretty-print"],
               f"guest-{phase}-whatif", timeout=180, closure=closure)
    control.az(["deployment", "group", "validate", *args], f"guest-{phase}-validate",
               timeout=180, closure=closure)
    control.az(["deployment", "group", "create", *args, "--name", f"threehub-guest-{phase}",
                "--no-wait"], f"guest-{phase}-submit", mutation=True, closure=closure)
    control.record_operation(f"threehub-guest-{phase}")
    if closure:
        lease = control.guard(False)
        deadline = control.dt.datetime.now(control.dt.timezone.utc) + control.dt.timedelta(
            minutes=lease["restoreTimeoutMinutes"])
        lease["operations"][f"threehub-guest-{phase}"]["deadlineUtc"] = deadline.isoformat()
        lease["restoreDeadlineUtc"] = deadline.isoformat()
        control.save(control.LEASE, lease)


def outputs(phase, names=None):
    results = {}
    query_path = control.RUNTIME / "guest-instanceview-query.json"
    control.save(query_path, {"api-version": "2024-03-01", "$expand": "instanceView"})
    for name, _, _, _ in VMS:
        if names and name not in names:
            continue
        value = control.az(["rest", "--method", "get", "--url",
            f"https://management.azure.com/subscriptions/{control.account_id()}/resourceGroups/{control.RG}"
            f"/providers/Microsoft.Compute/virtualMachines/{name}/runCommands/guest-{phase}",
            "--url-parameters", "@" + str(query_path)],
            f"guest-{phase}-{name}", closure=True)
        instance = value["properties"].get("instanceView", {})
        results[name] = {key: instance.get(key) for key in
                         ("executionState", "exitCode", "output", "error")}
        print(name, json.dumps(results[name]), flush=True)
    control.save(control.RUNTIME / f"guest-{phase}-results.json", results)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["stage", "activate", "smoke", "restore"])
    parser.add_argument("--lease-file", type=pathlib.Path, required=True)
    parser.add_argument("--generate-only", action="store_true")
    parser.add_argument("--outputs", action="store_true")
    parser.add_argument("--names", nargs="+")
    options = parser.parse_args()
    control.LEASE = options.lease_file.resolve()
    if control.LEASE.parent != control.RUNTIME:
        raise ValueError("Lease must be in this lab runtime directory")
    if options.generate_only:
        generate(options.phase)
    elif options.outputs:
        outputs(options.phase, options.names)
    else:
        submit(options.phase)
