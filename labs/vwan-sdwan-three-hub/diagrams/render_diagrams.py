"""Render the same offline scene as SVG and editable native Excalidraw shapes."""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BLUE, PURPLE, ORANGE, GRAY = "#1864ab", "#862e9c", "#e67700", "#495057"


class Scene:
    def __init__(self, name, width, height):
        self.name, self.width, self.height = name, width, height
        self.elements, self.svg = [], []

    def element(self, kind, x, y, width, height, **properties):
        item = dict(id=f"{self.name}-{len(self.elements) + 1}", type=kind,
                    x=x, y=y, width=width, height=height, angle=0,
                    strokeColor=GRAY, backgroundColor="transparent",
                    fillStyle="solid", strokeWidth=2, strokeStyle="solid",
                    roughness=0, opacity=100, groupIds=[], frameId=None,
                    roundness=None, seed=1, version=1, versionNonce=1,
                    isDeleted=False, boundElements=None, updated=1,
                    link=None, locked=False)
        item.update(properties)
        self.elements.append(item)
        return item

    def text(self, x, y, text, size=18, width=1000, container=None):
        lines = text.split("\n")
        height = size * 2.5 * len(lines)
        item = self.element(
            "text", x, y, width, height, text=text, originalText=text,
            fontSize=size, fontFamily=2, strokeColor="#000000",
            textAlign="left", verticalAlign="top", lineHeight=1.25,
            autoResize=False, containerId=container["id"] if container else None)
        if container:
            container["boundElements"] = [{"type": "text", "id": item["id"]}]
        spans = "".join(
            f'<tspan x="{x}" dy="{0 if n == 0 else size * 1.5}">'
            f'{html.escape(line)}</tspan>' for n, line in enumerate(lines))
        self.svg.append(f'<text x="{x}" y="{y + size}" font-size="{size}" '
                        f'fill="#000000">{spans}</text>')
        return item

    def box(self, x, y, width, height, text="", color=BLUE, fill=None, size=18):
        item = self.element("rectangle", x, y, width, height,
                            strokeColor=color,
                            backgroundColor=fill or "transparent",
                            roundness={"type": 3})
        self.svg.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" '
                        f'rx="12" stroke="{color}" stroke-width="2" '
                        f'fill="{fill or "none"}"/>')
        if text:
            assert size * 2.5 * len(text.split("\n")) + 30 <= height
            self.text(x + 20, y + 15, text, size, width - 40, item)
        return item

    def line(self, points, color=BLUE, dashed=False):
        x = min(px for px, _ in points)
        y = min(py for _, py in points)
        local = [[px - x, py - y] for px, py in points]
        self.element(
            "line", x, y,
            max(p[0] for p in points) - min(p[0] for p in points),
            max(p[1] for p in points) - min(p[1] for p in points),
            points=local, strokeColor=color,
            strokeStyle="dashed" if dashed else "solid",
            startBinding=None, endBinding=None,
            startArrowhead=None, endArrowhead=None)
        coords = " ".join(f"{px},{py}" for px, py in points)
        dash = ' stroke-dasharray="10 7"' if dashed else ""
        self.svg.append(f'<polyline points="{coords}" fill="none" '
                        f'stroke="{color}" stroke-width="3"{dash}/>')

    def save(self):
        data = dict(type="excalidraw", version=2, source="net-lab-builder",
                    elements=self.elements,
                    appState={"viewBackgroundColor": "#ffffff", "gridSize": None},
                    files={})
        (ROOT / f"{self.name}.excalidraw").write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8")
        (ROOT / f"{self.name}.svg").write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" '
            f'height="{self.height}" viewBox="0 0 {self.width} {self.height}" '
            f'role="img" aria-labelledby="title desc">'
            f'<title id="title">{html.escape(self.name)}</title>'
            '<desc id="desc">Three secured hubs with Standard Azure Firewall '
            'and PrivateTraffic routing intent. Static-VPN reproduction is pending.</desc>'
            f'<rect width="{self.width}" height="{self.height}" fill="white"/>'
            '<g font-family="Arial, Helvetica, sans-serif">'
            + "".join(self.svg) + "</g></svg>\n", encoding="utf-8")


def topology():
    s = Scene("topology", 1800, 1980)
    s.text(40, 20, "Three-hub Virtual WAN / private SD-WAN model", 30, 1700)
    s.text(40, 90, "CURRENT: three Standard firewalls + PrivateTraffic RI. Static-VPN reproduction remains in progress.", 21, 1700)
    s.box(30, 180, 1740, 450, color=BLUE)
    s.text(50, 190, "AZURE VIRTUAL WAN  |  vwan-threehub (Standard)  |  hub ASN 65515", 20, 1700)
    columns = [70, 680, 1290]
    for x, site, prefix, region, hub_prefix in zip(
            columns, ["EU", "US", "JP"], ["10.10", "10.20", "10.30"],
            ["West Europe", "North Central US", "Japan East"],
            ["10.250.0.0/23", "10.250.2.0/23", "10.250.4.0/23"]):
        s.box(x, 250, 440, 130,
              f"Azure spoke {site} | {prefix}.0.0/24\nProbe {prefix}.0.10",
              BLUE, "#a5d8ff", 18)
        s.line([(x + 220, 380), (x + 220, 430)])
        s.box(x, 430, 440, 130,
              f"hub-{site.lower()} | {region}\n{hub_prefix} | fw-{site.lower()} | Private RI",
              BLUE, "#a5d8ff", 18)
    s.line([(510, 485), (680, 485)])
    s.line([(1120, 485), (1290, 485)])
    s.line([(290, 560), (290, 605), (1510, 605), (1510, 560)])
    s.text(560, 565, "Managed interhub full mesh (NOT WireGuard)", 18, 750)
    for x in columns:
        s.line([(x + 220, 560), (x + 220, 710)])
    s.text(75, 655, "2 eBGP peers to hub router IPs", 17, 470)
    s.text(685, 655, "2 eBGP peers to hub router IPs", 17, 470)
    s.text(1300, 655, "2 IPsec tunnels + 2 eBGP peers", 17, 470)
    s.box(70, 710, 440, 180,
          "EU transit VNet | 10.210.0.0/24\nHubBgpConnection: bgp-router-eu\nRouter endpoint 10.210.0.4", BLUE, "#a5d8ff", 18)
    s.box(680, 710, 440, 180,
          "US transit VNet | 10.220.0.0/24\nHubBgpConnection: bgp-router-us\nRouter endpoint 10.220.0.4", BLUE, "#a5d8ff", 18)
    s.box(1290, 710, 440, 180,
          "JP vpngw-jp | active-active S2S\nBGP local 169.254.21.1 (both)\nAzure peers .21.2 / .21.6", ORANGE, "#fff3bf", 18)
    s.line([(290, 890), (290, 1030)])
    s.line([(900, 890), (900, 1030)])
    s.line([(1510, 890), (1510, 1030)], ORANGE)
    s.box(30, 950, 1740, 840, color=PURPLE)
    s.text(50, 960, "PRIVATE SD-WAN MODEL  |  six unique WireGuard / eBGP links  |  physical endpoints over Azure peering", 19, 1700)
    s.box(70, 1030, 440, 230,
          "EU BIRD | ASN 65011 | 10.210.0.4\nDC VNet 10.110.0.0/24\nProbe 10.110.0.10 (via transit)\nNo direct DC-to-hub attachment",
          PURPLE, "#f3d9fa", 18)
    s.box(680, 1030, 440, 230,
          "US BIRD | ASN 65012 | 10.220.0.4\nDC VNet 10.120.0.0/24\nProbe 10.120.0.10 (via transit)\nNo direct DC-to-hub attachment",
          PURPLE, "#f3d9fa", 18)
    s.box(1290, 1030, 440, 230,
          "JP BIRD + strongSwan | ASN 65013\nDC VNet / router 10.130.0.0/24 / .4\nProbe 10.130.0.10\nOnly IPsec ingress in this lab",
          PURPLE, "#f3d9fa", 18)
    s.box(680, 1540, 440, 230,
          "CN logical DC | ASN 65014\nJapan East (not sovereign China)\nDC 10.140.0.0/24 | router/probe .4\nNo direct Azure ingress",
          PURPLE, "#f3d9fa", 18)
    s.line([(510, 1130), (680, 1130)], PURPLE)
    s.text(520, 1080, "EU-US\n.0/30", 16, 150)
    s.line([(1120, 1130), (1290, 1130)], PURPLE)
    s.text(1130, 1080, "US-JP\n.12/30", 16, 150)
    s.line([(290, 1260), (290, 1350), (1510, 1350), (1510, 1260)], PURPLE)
    s.text(710, 1300, "EU-JP 172.31.0.4/30", 17, 430)
    s.line([(210, 1260), (210, 1650), (680, 1650)], PURPLE)
    s.text(245, 1590, "EU-CN .8/30", 18, 390)
    s.line([(900, 1260), (900, 1540)], PURPLE)
    s.text(920, 1450, "US-CN .16/30", 17, 340)
    s.line([(1590, 1260), (1590, 1650), (1120, 1650)], PURPLE)
    s.text(1180, 1590, "JP-CN .20/30", 18, 390)
    s.text(70, 1810, "Purple: private WireGuard (all subnets 172.31.0.x/30). Blue: Azure fabric / hub BGP. Orange: JP IPsec.", 18, 1700)
    s.text(70, 1860, "Underlay: four DC VNets fully mesh-peered + transit endpoint peerings; 13 pairs / 26 directions (not drawn as overlay).", 18, 1700)
    s.text(70, 1910, "Each ingress exports ALL four DC /24s. 6 Azure + 6 mesh = 12 unique BGP adjacencies; 18 BIRD endpoint entries.", 18, 1700)
    s.save()


def routing_intent():
    s = Scene("routing-intent", 1800, 1510)
    s.text(40, 20, "Routing intent comparison: collect the right evidence", 30, 1700)
    s.text(40, 90, "LEFT: historical unsecured baseline. RIGHT: deployed PrivateTraffic RI; validation in progress.", 21, 1700)
    s.box(30, 190, 840, 1150, color=BLUE)
    s.box(930, 190, 840, 1150, color=ORANGE)
    s.text(60, 210, "WITHOUT RI | HISTORICAL BASELINE", 23, 790)
    s.text(960, 210, "WITH PRIVATE RI | DEPLOYED", 23, 790)
    s.box(90, 320, 720, 180,
          "Azure spoke -> its hub\nRepeat for EU, US, JP\nRecord actual HRP + RI metadata each step", BLUE, "#a5d8ff", 20)
    s.box(990, 320, 720, 180,
          "Azure spoke -> its hub\nAll three hubs must have converged PrivateTraffic RI\nRepeat for EU, US, JP", BLUE, "#a5d8ff", 20)
    s.line([(450, 500), (450, 590)])
    s.line([(1350, 500), (1350, 590)], ORANGE, True)
    s.box(90, 590, 720, 230,
          "READ: hub connection effective routes\nresourceId = actual conn-spoke-* ARM ID\nresource-type = HubVirtualNetworkConnection\nPreserve full winning prefixes / AS paths / next hops",
          BLUE, "#a5d8ff", 20)
    s.box(990, 590, 720, 230,
          "Default table: private aggregates -> firewall\nNOT post-inspection branch winners\nAZFW_Hub Standard firewall (deployed)\nOne firewall per hub; shared scoped policy",
          ORANGE, "#fff3bf", 20)
    s.line([(450, 810), (450, 900)])
    s.line([(1350, 810), (1350, 900)], ORANGE, True)
    s.box(90, 900, 720, 230,
          "Optional: defaultRouteTable effective view\nKnown provider result value=[] is visibility only\nDo not infer zero learned routes or forwarding\nCorrelate BIRD, FIB, NIC, VPN and packet evidence",
          GRAY, "#dee2e6", 20)
    s.box(990, 900, 720, 230,
          "DECISIVE READ: owning hub effectiveRoutes\nresourceId = ACTUAL Azure Firewall ARM ID\nresource-type = AzureFirewalls (PLURAL)\nThen correlate firewall flows + ingress candidates",
          ORANGE, "#fff3bf", 20)
    s.text(70, 1170, "CLI: az network vhub get-effective-routes\n-g <RG> -n <owning-hub> --resource-id <ARM-ID>\n--resource-type HubVirtualNetworkConnection -o json", 18, 780)
    s.text(970, 1170, "CLI: az network vhub get-effective-routes\n-g <RG> -n <owning-hub> --resource-id <FIREWALL-ID>\n--resource-type AzureFirewalls -o json", 18, 780)
    s.text(50, 1370, "Firewall show resolves identity ONLY; it is not route retrieval. Wait for LRO completion; HTTP 202 alone is not evidence.", 20, 1700)
    s.text(50, 1430, "Paired RI routes measured; traffic 18/24. Static-VPN reproduction, prepend thresholds and symmetry remain pending.", 20, 1700)
    s.save()


if __name__ == "__main__":
    topology()
    routing_intent()
    print("Rendered topology and routing-intent SVG + Excalidraw (offline).")
