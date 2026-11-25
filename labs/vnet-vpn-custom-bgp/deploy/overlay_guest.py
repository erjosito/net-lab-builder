"""Persistent, dual-instance private and Internet StrongSwan/FRR configuration."""
import base64
import ipaddress
import re
import shlex


def tunnel_specs(inventory, stage="backup"):
    rows = inventory["gateway"]["bgpSettings"]["bgpPeeringAddresses"]
    specs = []
    for row in rows:
        outer = [ip for ip in row["tunnelIpAddresses"] if ipaddress.ip_address(ip).is_private]
        public = [ip for ip in row["tunnelIpAddresses"] if not ipaddress.ip_address(ip).is_private]
        if len(outer) != 1 or len(public) != 1 or len(row["defaultBgpIpAddresses"]) != 1:
            raise ValueError("Expected one private outer, public outer and default BGP IP per instance.")
        name = row["ipconfigurationId"].rsplit("/", 1)[-1]
        specs.append({
            "instance": name, "outer": outer[0], "public": public[0],
            "bgp": row["defaultBgpIpAddresses"][0],
            "apipa": row["customBgpIpAddresses"][0],
        })
    if len(specs) != 2:
        raise ValueError("Expected exactly two active-active instances.")
    specs.sort(key=lambda item: ipaddress.ip_address(item["bgp"]), reverse=True)
    # Match the customer-like Internet endpoint to the higher default BGP address.
    selected = specs[0]
    tunnels = [
        {"name": "internet", "id": 101, "outer": selected["public"], "bgp": selected["apipa"],
         "instance": selected["instance"], "source": "169.254.21.1", "transport": "internet"},
        *[{"name": f"private{index}", "id": 102 + index, "outer": item["outer"],
           "bgp": item["bgp"], "instance": item["instance"], "source": "10.245.254.6",
           "transport": "private"}
          for index, item in enumerate(specs)],
        {"name": "internet1", "id": 104, "outer": specs[1]["public"], "bgp": specs[1]["apipa"],
         "instance": specs[1]["instance"], "source": "169.254.21.1", "transport": "internet"},
    ]
    return tunnels[:{"internet": 1, "private-first": 2, "private": 3, "backup": 4}[stage]]


def files(inventory, psks, stage):
    if stage not in ["internet", "private-first", "private", "backup"]:
        raise ValueError("Unknown guest stage.")
    if any(not re.fullmatch(r"[a-f0-9]{64}", psks[key]) for key in ["internet", "private"]):
        raise ValueError("Expected generated 256-bit hex PSKs.")
    specs = tunnel_specs(inventory, stage)
    public = inventory["cpe"]["networkInterfaces"][0]["accessConfigs"][0]["natIP"]
    ipaddress.ip_address(public)
    swan = "connections {\n"
    network = """#!/usr/bin/env bash
set -euo pipefail
NIC=$(ip -4 route show default | awk 'NR==1 {print $5}')
GW=$(ip -4 route show default | awk 'NR==1 {print $3}')
test -n "$NIC" && test -n "$GW"
sysctl -qw net.ipv4.ip_forward=1 net.ipv4.conf.all.rp_filter=0 net.ipv4.conf.default.rp_filter=0
sysctl -qw "net.ipv4.conf.$NIC.rp_filter=0"
ip address replace 10.245.254.6/32 dev lo
ip address replace 10.246.1.1/32 dev lo
"""
    if stage == "backup":
        network += "ip address replace 169.254.21.1/32 dev lo\n"
    for spec in specs:
        name, ident = spec["name"], spec["id"]
        local_id = public if spec["transport"] == "internet" else "10.245.0.10"
        swan += f"""  {name} {{
    version = 2
    local_addrs = 10.245.0.10
    remote_addrs = {spec["outer"]}
    mobike = no
    encap = yes
    dpd_delay = 15s
    proposals = aes256-sha256-modp2048,aes256-sha256-modp1024
    local {{
      auth = psk
      id = {local_id}
    }}
    remote {{
      auth = psk
      id = {spec["outer"]}
    }}
    children {{
      {name} {{
        local_ts = 0.0.0.0/0
        remote_ts = 0.0.0.0/0
        if_id_in = {ident}
        if_id_out = {ident}
        esp_proposals = aes256-sha256
        rekey_time = 2700s
        life_time = 3600s
        start_action = start
        dpd_action = restart
      }}
    }}
  }}
"""
        network += f"""if ! ip link show xfrm-{name} >/dev/null 2>&1; then
  ip link add xfrm-{name} type xfrm dev "$NIC" if_id {ident}
fi
ip link set xfrm-{name} mtu 1400 up
ip route replace {spec["outer"]}/32 via "$GW" dev "$NIC" src 10.245.0.10
"""
        if spec["transport"] != "internet" or stage == "backup":
            network += f'ip route replace {spec["bgp"]}/32 dev xfrm-{name} src {spec["source"]}\n'
    if stage == "backup":
        network += """if ip -4 route show exact 10.244.0.0/16 | grep -q 'metric 250'; then
  ip route del 10.244.0.0/16 dev xfrm-internet metric 250
fi
"""
    else:
        network += "ip route replace 10.244.0.0/16 dev xfrm-internet src 10.246.1.1 metric 250\n"
    swan += "}\nsecrets {\n"
    for name in ["internet", "private"] if len(specs) > 1 else ["internet"]:
        swan += f"""  ike-{name} {{
    id = {public if name == "internet" else "10.245.0.10"}
    secret = {psks[name]}
  }}
"""
    swan += "}\n"
    frr = """frr defaults traditional
hostname vnbgp-cpe
log syslog informational
service integrated-vtysh-config
ip route 10.246.1.0/24 Null0
ip prefix-list LAB-EXPORT seq 10 permit 10.246.1.0/24
ip prefix-list AZURE-IMPORT seq 10 permit 10.244.0.0/16
route-map PRIVATE-IN permit 10
 match ip address prefix-list AZURE-IMPORT
 set local-preference 200
route-map INTERNET-IN permit 10
 match ip address prefix-list AZURE-IMPORT
 set local-preference 100
route-map PRIVATE-OUT permit 10
 match ip address prefix-list LAB-EXPORT
route-map INTERNET-OUT permit 10
 match ip address prefix-list LAB-EXPORT
 set as-path prepend 64513 64513
router bgp 64513
 bgp router-id 10.245.254.6
 no bgp default ipv4-unicast
"""
    peers = [s for s in specs if s["transport"] != "internet" or stage == "backup"]
    for spec in peers:
        frr += f""" neighbor {spec["bgp"]} remote-as 65515
 neighbor {spec["bgp"]} ebgp-multihop 5
 neighbor {spec["bgp"]} update-source {spec["source"]}
"""
    frr += " address-family ipv4 unicast\n  network 10.246.1.0/24\n  maximum-paths 2\n"
    for spec in peers:
        policy = "INTERNET" if spec["transport"] == "internet" else "PRIVATE"
        frr += f"""  neighbor {spec["bgp"]} activate
  neighbor {spec["bgp"]} route-map {policy}-IN in
  neighbor {spec["bgp"]} route-map {policy}-OUT out
"""
    frr += " exit-address-family\n!\n"
    return {
        "/etc/swanctl/conf.d/vnbgp.conf": swan,
        "/usr/local/sbin/vnbgp-network": network,
        "/etc/frr/frr.conf": frr,
        "/etc/strongswan.d/90-vnbgp.conf": "charon {\n  install_routes = no\n}\n",
        "/etc/sysctl.d/91-vnbgp.conf": (
            "net.ipv4.ip_forward=1\nnet.ipv4.conf.all.rp_filter=0\n"
            "net.ipv4.conf.default.rp_filter=0\n"
        ),
        "/etc/systemd/system/vnbgp-network.service": """[Unit]
Description=VNet VPN lab persistent interfaces and endpoint routes
Wants=network-online.target
After=network-online.target
Before=strongswan.service frr.service
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/vnbgp-network
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
""",
        "/etc/systemd/system/vnbgp-ipsec.service": """[Unit]
Description=Load persistent VNet VPN lab configuration
Requires=vnbgp-network.service strongswan.service
After=vnbgp-network.service strongswan.service
Before=frr.service
[Service]
Type=oneshot
ExecStart=/usr/sbin/swanctl --load-all
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
""",
    }


def install_script(inventory, psks, stage, *, add_only=False):
    if add_only and stage != "backup":
        raise ValueError("Adding the second Internet instance requires the backup stage.")
    rendered = files(inventory, psks, stage)
    if add_only:
        rendered = {path: rendered[path] for path in [
            "/etc/swanctl/conf.d/vnbgp.conf", "/usr/local/sbin/vnbgp-network", "/etc/frr/frr.conf",
        ]}
    script = """set -euo pipefail
umask 077
install -d -m 0700 /etc/swanctl/conf.d
"""
    if add_only:
        script += """systemctl is-active strongswan frr
NIC=$(ip -4 route show default | awk 'NR==1 {print $5}')
GW=$(ip -4 route show default | awk 'NR==1 {print $3}')
test -n "$NIC" && test -n "$GW"
ip -4 address show dev lo | grep -q '169\\.254\\.21\\.1/32'
"""
    for path, content in rendered.items():
        encoded = base64.b64encode(content.encode()).decode()
        script += f"printf %s {shlex.quote(encoded)} | base64 -d >{shlex.quote(path)}\n"
    script += """chmod 0700 /usr/local/sbin/vnbgp-network
chown frr:frr /etc/frr/frr.conf
chmod 0640 /etc/frr/frr.conf
"""
    if add_only:
        spec = next(s for s in tunnel_specs(inventory, stage) if s["name"] == "internet1")
        script += f"""if ! ip link show xfrm-internet1 >/dev/null 2>&1; then
  ip link add xfrm-internet1 type xfrm dev "$NIC" if_id {spec["id"]}
fi
ip link set xfrm-internet1 mtu 1400 up
ip route replace {spec["outer"]}/32 via "$GW" dev "$NIC" src 10.245.0.10
ip route replace {spec["bgp"]}/32 dev xfrm-internet1 src {spec["source"]}
swanctl --load-conns
"""
        names = "internet1"
    else:
        script += """\
sed -i 's/^bgpd=no$/bgpd=yes/;s/^staticd=no$/staticd=yes/' /etc/frr/daemons
systemctl daemon-reload
systemctl enable vnbgp-network.service vnbgp-ipsec.service
/usr/local/sbin/vnbgp-network
swanctl --reload-settings
swanctl --load-all
"""
        names = " ".join(spec["name"] for spec in tunnel_specs(inventory, stage))
    script += f"""for child in {names}; do
  current=$(swanctl --list-sas --ike "$child")
  if [ -z "$current" ]; then swanctl --initiate --child "$child" --timeout 30; fi
done
"""
    if add_only:
        commands = [
            "configure terminal", "router bgp 64513",
            f'neighbor {spec["bgp"]} remote-as 65515',
            f'neighbor {spec["bgp"]} ebgp-multihop 5',
            f'neighbor {spec["bgp"]} update-source {spec["source"]}',
            "address-family ipv4 unicast",
            f'neighbor {spec["bgp"]} route-map INTERNET-IN in',
            f'neighbor {spec["bgp"]} route-map INTERNET-OUT out',
            f'neighbor {spec["bgp"]} activate', "end",
        ]
        script += "vtysh " + shlex.join([arg for command in commands for arg in ["-c", command]]) + "\n"
    else:
        script += "systemctl restart frr\n" if stage == "internet" else "systemctl reload frr\n"
    script += "systemctl is-active strongswan frr\nswanctl --list-sas\nip -4 route show\n"
    return script
