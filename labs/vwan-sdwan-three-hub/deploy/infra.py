"""Generate deterministic ARM templates for the approved unsecured topology."""
import base64
import copy
from control import ROOT, TAGS, save

API = "2024-05-01"
REGIONS = {"eu": "westeurope", "us": "northcentralus", "jp": "japaneast"}
SKUS = {"eu": "Standard_B2ts_v2", "us": "Standard_B2als_v2", "jp": "Standard_B2ts_v2"}
VNETS = [
    ("dc-eu", "eu", "10.110.0.0/24"), ("dc-us", "us", "10.120.0.0/24"),
    ("dc-jp", "jp", "10.130.0.0/24"), ("dc-cn", "jp", "10.140.0.0/24"),
    ("transit-eu", "eu", "10.210.0.0/24"), ("transit-us", "us", "10.220.0.0/24"),
    ("spoke-eu", "eu", "10.10.0.0/24"), ("spoke-us", "us", "10.20.0.0/24"),
    ("spoke-jp", "jp", "10.30.0.0/24"),
]
VMS = [
    ("router-eu", "transit-eu", "10.210.0.4", True),
    ("router-us", "transit-us", "10.220.0.4", True),
    ("router-jp", "dc-jp", "10.130.0.4", True),
    ("router-cn", "dc-cn", "10.140.0.4", True),
    ("probe-dc-eu", "dc-eu", "10.110.0.10", False),
    ("probe-dc-us", "dc-us", "10.120.0.10", False),
    ("probe-dc-jp", "dc-jp", "10.130.0.10", False),
    ("probe-spoke-eu", "spoke-eu", "10.10.0.10", False),
    ("probe-spoke-us", "spoke-us", "10.20.0.10", False),
    ("probe-spoke-jp", "spoke-jp", "10.30.0.10", False),
]
DC_PREFIXES = ["10.110.0.0/24", "10.120.0.0/24", "10.130.0.0/24", "10.140.0.0/24"]
SPOKE_PREFIXES = ["10.10.0.0/24", "10.20.0.0/24", "10.30.0.0/24"]
ROUTER_IPS = ["10.210.0.4", "10.220.0.4", "10.130.0.4", "10.140.0.4"]
WG_PAIRS = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
PEERS = [
    ("dc-eu", "dc-us"), ("dc-eu", "dc-jp"), ("dc-eu", "dc-cn"),
    ("dc-us", "dc-jp"), ("dc-us", "dc-cn"), ("dc-jp", "dc-cn"),
    ("dc-eu", "transit-eu"), ("dc-us", "transit-us"),
    ("transit-eu", "transit-us"), ("transit-eu", "dc-jp"), ("transit-eu", "dc-cn"),
    ("transit-us", "dc-jp"), ("transit-us", "dc-cn"),
]


def rid(kind, name):
    segments = ", ".join(f"'{segment}'" for segment in name.split("/"))
    return f"[resourceId('Microsoft.Network/{kind}', {segments})]"


def resource(kind, name, properties, region=None, depends=()):
    value = {"type": f"Microsoft.Network/{kind}", "apiVersion": API,
             "name": name, "properties": properties}
    if region:
        value.update(location=REGIONS[region], tags=TAGS)
    if depends:
        value["dependsOn"] = list(depends)
    return value


def template(resources, parameters=None):
    return {"$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
            "contentVersion": "1.0.0.0", "parameters": parameters or {}, "resources": resources}


def base():
    resources = [resource("virtualWans", "vwan-threehub", {
        "type": "Standard", "allowBranchToBranchTraffic": True,
        "disableVpnEncryption": False}, "jp")]
    for region, prefix in [("eu", "10.250.0.0/23"), ("us", "10.250.2.0/23"), ("jp", "10.250.4.0/23")]:
        resources.append(resource("virtualHubs", f"hub-{region}", {
            "virtualWan": {"id": rid("virtualWans", "vwan-threehub")},
            "addressPrefix": prefix, "sku": "Standard", "hubRoutingPreference": "ExpressRoute",
            "virtualRouterAutoScaleConfiguration": {"minCapacity": 2}},
            region, [rid("virtualWans", "vwan-threehub")]))
    resources.append(vpn_gateway_resource([rid("virtualHubs", "hub-jp")]))
    save(ROOT / "base.json", template(resources))


def vpn_gateway_resource(depends=()):
    return resource("vpnGateways", "vpngw-jp", {
        "virtualHub": {"id": rid("virtualHubs", "hub-jp")},
        "vpnGatewayScaleUnit": 1,
        "bgpSettings": {"asn": 65515, "peerWeight": 0}},
        "jp", depends)


def vpn_gateway():
    return template([vpn_gateway_resource()])


def gateway_public_ips(gateway):
    properties = gateway["properties"]
    peers = properties.get("bgpSettings", {}).get("bgpPeeringAddresses", [])
    ids = [peer.get("ipconfigurationId") for peer in peers]
    if len(peers) != 2 or any(not value for value in ids) or len(set(ids)) != 2:
        raise ValueError("Two actual gateway instance IDs required")
    configurations = properties.get("ipConfigurations", [])
    if configurations:
        endpoints = {configuration["id"]: configuration.get("publicIpAddress")
                     for configuration in configurations}
        if len(configurations) != 2 or set(endpoints) != set(ids):
            raise ValueError("Gateway IP configuration IDs must match actual BGP instances")
        if any(endpoints[peer["ipconfigurationId"]] not in peer.get("tunnelIpAddresses", [])
               for peer in peers):
            raise ValueError("Gateway public IP must belong to its actual BGP instance")
    else:
        if any(len(peer.get("tunnelIpAddresses", [])) != 1 for peer in peers):
            raise ValueError("Gateway IP configurations required to select public tunnel endpoints")
        endpoints = {peer["ipconfigurationId"]: peer["tunnelIpAddresses"][0] for peer in peers}
    if any(not value for value in endpoints.values()) or len(set(endpoints.values())) != 2:
        raise ValueError("Two actual gateway instance IDs and distinct tunnel PIPs required")
    return endpoints


def vpn_gateway_update(gateway):
    properties = gateway["properties"]
    if properties.get("provisioningState") != "Succeeded":
        raise ValueError("JP VPN gateway must succeed before custom address update")
    gateway_public_ips(gateway)
    body = {key: copy.deepcopy(gateway[key]) for key in ("location", "tags", "properties")
            if key in gateway}
    for peer, custom in zip(
            sorted(body["properties"]["bgpSettings"]["bgpPeeringAddresses"],
                   key=lambda value: value["ipconfigurationId"]),
            ("169.254.21.2", "169.254.21.6")):
        peer["customBgpIpAddresses"] = [custom]
    return body


def rule(name, priority, protocol, sources, destinations, ports, direction="Inbound", access="Allow"):
    properties = {"priority": priority, "protocol": protocol, "access": access, "direction": direction,
                  "sourcePortRange": "*"}
    for field, values in [("sourceAddressPrefix", sources), ("destinationAddressPrefix", destinations),
                          ("destinationPortRange", ports)]:
        properties[field if len(values) == 1 else field + "es" if "Address" in field else field + "s"] = (
            values[0] if len(values) == 1 else values)
    return {"name": name, "properties": properties}


def security_rules(name, ip, router, hubs=None, gateway_ips=None):
    rules = [
        rule("private-icmp", 130, "Icmp", DC_PREFIXES + SPOKE_PREFIXES, [ip], ["*"]),
        rule("private-http", 131, "Tcp", DC_PREFIXES + SPOKE_PREFIXES, [ip], ["5201"]),
        rule("out-private-icmp", 130, "Icmp", [ip], DC_PREFIXES + SPOKE_PREFIXES, ["*"], "Outbound"),
        rule("out-private-http", 131, "Tcp", [ip], DC_PREFIXES + SPOKE_PREFIXES, ["5201"], "Outbound"),
        rule("bootstrap-web", 200, "Tcp", [ip], ["Internet"], ["80", "443"], "Outbound"),
        rule("platform-agent", 202, "Tcp", [ip], ["168.63.129.16", "169.254.169.254"],
             ["80", "32526"], "Outbound"),
    ]
    if router:
        rules.extend([
            rule("forward-private", 140, "*", DC_PREFIXES + SPOKE_PREFIXES,
                 DC_PREFIXES + SPOKE_PREFIXES, ["*"]),
            rule("out-forward-private", 140, "*", DC_PREFIXES + SPOKE_PREFIXES,
                 DC_PREFIXES + SPOKE_PREFIXES, ["*"], "Outbound"),
        ])
        for index, pair in enumerate(WG_PAIRS):
            if ROUTER_IPS.index(ip) not in pair:
                continue
            remote = ROUTER_IPS[pair[1] if ROUTER_IPS[pair[0]] == ip else pair[0]]
            rules.extend([
                rule(f"wireguard-link-{index}", 1000 + index, "Udp",
                     [f"{remote}/32"], [f"{ip}/32"], [str(51821 + index)]),
                rule(f"out-wireguard-link-{index}", 1000 + index, "Udp",
                     [f"{ip}/32"], [f"{remote}/32"], [str(51821 + index)], "Outbound"),
            ])
        if name in ("router-eu", "router-us"):
            region = name.split("-")[-1]
            peers = [f"{x}/32" for x in hubs[region]] if hubs else [
                "10.250.0.0/23" if region == "eu" else "10.250.2.0/23"]
            rules.extend([rule("hub-bgp", 110, "Tcp", peers, [ip], ["179"]),
                          rule("out-hub-bgp", 110, "Tcp", [ip], peers, ["179"], "Outbound")])
        if name == "router-jp" and gateway_ips:
            endpoints = [f"{x}/32" for x in gateway_ips]
            rules.extend([rule("jp-ike", 120, "Udp", endpoints, [ip], ["500", "4500"]),
                          rule("out-jp-ike", 120, "Udp", [ip], endpoints, ["500", "4500"], "Outbound")])
    rules.extend([rule("deny-other-inbound", 4000, "*", ["*"], ["*"], ["*"], access="Deny"),
                  rule("deny-other-outbound", 4000, "*", ["*"], ["*"], ["*"], "Outbound", "Deny")])
    return rules


def bootstrap(router):
    packages = ["python3", "curl", "tcpdump"]
    if router:
        packages += ["bird2", "strongswan", "strongswan-swanctl", "charon-systemd", "wireguard"]
    config = """#cloud-config
package_update: true
packages:
""" + "".join(f"  - {x}\n" for x in packages) + """write_files:
  - path: /etc/systemd/system/lab-http.service
    permissions: '0644'
    content: |
      [Unit]
      Description=Private lab HTTP probe
      After=network-online.target
      Wants=network-online.target
      [Service]
      User=nobody
      ExecStart=/usr/bin/python3 -m http.server 5201 --directory /var/lib/lab-http
      Restart=on-failure
      [Install]
      WantedBy=multi-user.target
"""
    if router:
        config += """  - path: /etc/sysctl.d/90-lab-forwarding.conf
    permissions: '0644'
    content: |
      net.ipv4.ip_forward=1
      net.ipv4.conf.all.rp_filter=0
      net.ipv4.conf.default.rp_filter=0
"""
    config += """runcmd:
  - mkdir -p /var/lib/lab-http
  - sh -c 'echo lab-bootstrap-ready > /var/lib/lab-http/index.html'
  - systemctl daemon-reload
  - systemctl enable --now lab-http.service
"""
    if router:
        config += "  - sysctl --system\n  - systemctl disable --now bird\n"
    return base64.b64encode(config.encode()).decode()


def compute():
    resources = []
    lookup = {name: (region, prefix) for name, region, prefix in VNETS}
    for region, own in [("eu", "10.110.0.0/24"), ("us", "10.120.0.0/24")]:
        next_hop = "10.210.0.4" if region == "eu" else "10.220.0.4"
        routes = [{"name": f"data-{i}", "properties": {"addressPrefix": prefix,
                   "nextHopType": "VirtualAppliance", "nextHopIpAddress": next_hop}}
                  for i, prefix in enumerate(DC_PREFIXES + SPOKE_PREFIXES) if prefix != own]
        resources.append(resource("routeTables", f"rt-dc-{region}", {
            "disableBgpRoutePropagation": False, "routes": routes}, region))
    for name, region, prefix in VNETS:
        subnet = {"addressPrefix": prefix, "defaultOutboundAccess": False}
        depends = []
        if name in ("dc-eu", "dc-us"):
            subnet["routeTable"] = {"id": rid("routeTables", f"rt-{name}")}
            depends.append(rid("routeTables", f"rt-{name}"))
        resources.append(resource("virtualNetworks", f"vnet-{name}", {
            "addressSpace": {"addressPrefixes": [prefix]},
            "subnets": [{"name": "workload", "properties": subnet}]}, region, depends))
    previous_peer = None
    for first, second in PEERS:
        for local, remote in [(first, second), (second, first)]:
            name = f"vnet-{local}/to-{remote}"
            dependencies = [rid("virtualNetworks", f"vnet-{local}"), rid("virtualNetworks", f"vnet-{remote}")]
            if previous_peer:
                dependencies.append(previous_peer)
            resources.append(resource("virtualNetworks/virtualNetworkPeerings", name, {
                "remoteVirtualNetwork": {"id": rid("virtualNetworks", f"vnet-{remote}")},
                "allowVirtualNetworkAccess": True, "allowForwardedTraffic": True,
                "allowGatewayTransit": False, "useRemoteGateways": False}, depends=dependencies))
            previous_peer = rid("virtualNetworks/virtualNetworkPeerings", name)
    for name, vnet, ip, router in VMS:
        region = lookup[vnet][0]
        resources.append(resource("networkSecurityGroups", f"nsg-{name}", {
            "securityRules": security_rules(name, ip, router)}, region))
        pip = resource("publicIPAddresses", f"pip-{name}", {
            "publicIPAllocationMethod": "Static", "publicIPAddressVersion": "IPv4"}, region)
        pip["sku"] = {"name": "Standard"}
        resources.append(pip)
        resources.append(resource("networkInterfaces", f"nic-{name}", {
            "enableIPForwarding": router,
            "networkSecurityGroup": {"id": rid("networkSecurityGroups", f"nsg-{name}")},
            "ipConfigurations": [{"name": "ipconfig1", "properties": {
                "privateIPAllocationMethod": "Static", "privateIPAddress": ip,
                "publicIPAddress": {"id": rid("publicIPAddresses", f"pip-{name}")},
                "subnet": {"id": f"[resourceId('Microsoft.Network/virtualNetworks/subnets', 'vnet-{vnet}', 'workload')]"}}}]},
            region, [rid("virtualNetworks", f"vnet-{vnet}"), rid("publicIPAddresses", f"pip-{name}"),
                     rid("networkSecurityGroups", f"nsg-{name}")]))
        resources.append({
            "type": "Microsoft.Compute/virtualMachines", "apiVersion": "2024-07-01", "name": name,
            "location": REGIONS[region], "tags": TAGS,
            "dependsOn": [rid("networkInterfaces", f"nic-{name}")],
            "properties": {
                "hardwareProfile": {"vmSize": SKUS[region]}, "priority": "Regular",
                "storageProfile": {
                    "imageReference": {"publisher": "Canonical", "offer": "0001-com-ubuntu-server-jammy",
                                       "sku": "22_04-lts-gen2", "version": "latest"},
                    "osDisk": {"name": f"osdisk-{name}", "createOption": "FromImage", "diskSizeGB": 30,
                               "managedDisk": {"storageAccountType": "StandardSSD_LRS"}}},
                "osProfile": {"computerName": name, "adminUsername": "azurelabuser",
                    "customData": bootstrap(router),
                    "linuxConfiguration": {"disablePasswordAuthentication": True,
                        "ssh": {"publicKeys": [{"path": "/home/azurelabuser/.ssh/authorized_keys",
                                               "keyData": "[parameters('sshPublicKey')]"}]}}},
                "networkProfile": {"networkInterfaces": [{"id": rid("networkInterfaces", f"nic-{name}")}]}}})
    save(ROOT / "compute.json", template(resources, {"sshPublicKey": {"type": "secureString"}}))


def routing(region):
    table = {"id": rid("virtualHubs/hubRouteTables", f"hub-{region}/defaultRouteTable")}
    return {"associatedRouteTable": table,
            "propagatedRouteTables": {"ids": [table], "labels": ["Default"]}}


def hub_connections():
    resources = []
    for region in REGIONS:
        previous = None
        for kind in (["transit", "spoke"] if region != "jp" else ["spoke"]):
            name = f"hub-{region}/conn-{kind}-{region}"
            resources.append(resource("virtualHubs/hubVirtualNetworkConnections", name, {
                "remoteVirtualNetwork": {"id": rid("virtualNetworks", f"vnet-{kind}-{region}")},
                "enableInternetSecurity": False, "routingConfiguration": routing(region)},
                depends=[previous] if previous else []))
            previous = rid("virtualHubs/hubVirtualNetworkConnections", name)
    return template(resources)


def hub_bindings(hubs):
    resources = []
    for region in ("eu", "us"):
        hub = hubs[region].get("properties", hubs[region])
        if hub["virtualRouterAsn"] != 65515 or len(hub["virtualRouterIps"]) != 2:
            raise ValueError(f"Hub {region} router endpoints are not ready")
        if region != "jp":
            resources.append(resource("virtualHubs/bgpConnections", f"hub-{region}/bgp-router-{region}", {
                "peerAsn": 65011 if region == "eu" else 65012,
                "peerIp": "10.210.0.4" if region == "eu" else "10.220.0.4",
                "hubVirtualNetworkConnection": {"id": rid(
                    "virtualHubs/hubVirtualNetworkConnections", f"hub-{region}/conn-transit-{region}")}},
                ))
            name, _, ip, router = next(vm for vm in VMS if vm[0] == f"router-{region}")
            resources.append(resource("networkSecurityGroups", f"nsg-{name}", {
                "securityRules": security_rules(name, ip, router,
                                                {region: hub["virtualRouterIps"]})}, region))
    return template(resources)


def vpn_bindings(gateway, public_ip):
    properties = gateway["properties"]
    if properties["provisioningState"] != "Succeeded":
        raise ValueError("JP VPN gateway is not ready")
    peers = properties["bgpSettings"]["bgpPeeringAddresses"]
    public_endpoints = gateway_public_ips(gateway)
    selections, endpoints = [], []
    for custom in ["169.254.21.2", "169.254.21.6"]:
        matches = [peer for peer in peers if custom in peer.get("customBgpIpAddresses", [])]
        if len(matches) != 1:
            raise ValueError(f"Missing unique gateway mapping for {custom}")
        peer = matches[0]
        selections.append({"ipConfigurationId": peer["ipconfigurationId"],
                           "customBgpIpAddress": custom})
        endpoints.append(public_endpoints[peer["ipconfigurationId"]])
    if len(set(endpoints)) != 2 or not public_ip:
        raise ValueError("Two live gateway PIPs and JP router PIP required")
    site = resource("vpnSites", "site-dc-jp", {
        "virtualWan": {"id": rid("virtualWans", "vwan-threehub")},
        "vpnSiteLinks": [{"name": "link-jp", "properties": {
            "ipAddress": public_ip, "linkProperties": {"linkSpeedInMbps": 10},
            "bgpProperties": {"asn": 65013, "bgpPeeringAddress": "169.254.21.1"}}}]}, "jp")
    policy = {"dhGroup": "DHGroup14", "ikeEncryption": "AES256", "ikeIntegrity": "SHA256",
              "ipsecEncryption": "AES256", "ipsecIntegrity": "SHA256", "pfsGroup": "PFS14",
              "saDataSizeKilobytes": 102400000, "saLifeTimeSeconds": 3600}
    connection = resource("vpnGateways/vpnConnections", "vpngw-jp/conn-dc-jp", {
        "remoteVpnSite": {"id": rid("vpnSites", "site-dc-jp")},
        "enableInternetSecurity": False, "routingConfiguration": routing("jp"),
        "vpnLinkConnections": [{"name": "link-jp", "properties": {
            "vpnSiteLink": {"id": rid("vpnSites/vpnSiteLinks", "site-dc-jp/link-jp")},
            "enableBgp": True, "sharedKey": "[parameters('vpnSharedKey')]",
            "vpnConnectionProtocolType": "IKEv2", "usePolicyBasedTrafficSelectors": False,
            "vpnGatewayCustomBgpAddresses": selections, "ipsecPolicies": [policy],
            "connectionBandwidth": 10}}]}, depends=[rid("vpnSites", "site-dc-jp")])
    nsg = resource("networkSecurityGroups", "nsg-router-jp", {
        "securityRules": security_rules("router-jp", "10.130.0.4", True,
                                        gateway_ips=sorted(set(endpoints)))}, "jp")
    return template([site, connection, nsg], {"vpnSharedKey": {"type": "secureString"}})


if __name__ == "__main__":
    base()
