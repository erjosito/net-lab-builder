# Architecture & Packet Flow Diagrams

## 1. Expanded 3-Hybrid-Connection Topology & Asymmetric Bypass (`disablePeeringRoute = None` with Summary `10.0.0.0/8` UDR)

```mermaid
flowchart TB
    subgraph OnPrem1["Hybrid 1: S2S VPN On-Prem (172.16.0.0/16)"]
        VMOnPrem["vm-onprem (172.16.1.4)<br/>StrongSwan IKEv2 (vti0) + FRR BGP ASN 65010"]
    end

    subgraph OnPrem2["Hybrid 2: SD-WAN On-Prem (172.17.0.0/16)"]
        VMOnPremSDWAN["vm-onprem-sdwan (172.17.1.4)<br/>StrongSwan XFRM (xfrm0) + BIRD BGP ASN 65020"]
    end

    subgraph OnPrem3["Hybrid 3: ExpressRoute On-Prem (172.18.0.0/16)"]
        MCR["Megaport MCR (Frankfurt FR5)<br/>jomore-copilot-mcr-disable-peering<br/>ASN 65030 | Advertises 172.18.0.0/16"]
    end

    subgraph Hub["Hub VNet: vnet-hub (10.0.0.0/16)"]
        VPNGW["vpngw-hub (VpnGw1AZ)<br/>GatewaySubnet (10.0.0.0/24)<br/>ASN 65515 | BGP IP 10.0.0.254<br/>Route Table: rt-gw (UDR: 10.0.0.0/8 -> 10.0.1.4)"]
        ERGW["ergw-hub (Standard ER Gateway)<br/>GatewaySubnet (10.0.0.0/24)<br/>Connected to er-circuit-hub<br/>Route Table: rt-gw (UDR: 10.0.0.0/8 -> 10.0.1.4)"]
        Probe["vm-hub-probe (10.0.2.4)<br/>snet-hub-probe (10.0.2.0/24)<br/>Hub SD-WAN NVA: StrongSwan (xfrm0) + BIRD ASN 65002<br/>Route Table: rt-gw (UDR: 10.0.0.0/8 -> 10.0.1.4)"]
        NVA["vm-hub-nva (10.0.1.4)<br/>snet-nva (10.0.1.0/24)<br/>Central Firewall NVA (iptables / conntrack)<br/>Route Table: rt-nva (172.17.0.0/16 -> 10.0.2.4)"]
    end

    subgraph Spokes["10 Peered Spoke VNets (10.1.0.0/16 .. 10.10.0.0/16)"]
        Spoke1["vnet-spoke1 (10.1.0.0/16)<br/>vm-spoke1 (10.1.1.4)<br/>Route Table: rt-spoke1<br/>UDRs: 10.0.0.0/8, 172.16/16, 172.17/16, 172.18/16 -> 10.0.1.4"]
        SpokeN["vnet-spoke2 .. vnet-spoke10<br/>(10.2.0.0/16 .. 10.10.0.0/16)"]
    end

    VMOnPrem <==>|"S2S IPsec (vti0) + eBGP"| VPNGW
    VMOnPremSDWAN <==>|"SD-WAN IPsec (xfrm0) + eBGP"| Probe
    MCR <==>|"Primary + Secondary VXCs<br/>er-circuit-hub (50 Mbps)"| ERGW

    VPNGW -.->|"Forward Path BYPASSES vm-hub-nva!<br/>Matches Default 10.1.0.0/16 VNetPeering"| Spoke1
    Probe -.->|"Forward Path BYPASSES vm-hub-nva!<br/>Matches Default 10.1.0.0/16 VNetPeering"| Spoke1
    ERGW -.->|"Forward Path BYPASSES vm-hub-nva!<br/>Matches Default 10.1.0.0/16 VNetPeering"| Spoke1

    Spoke1 ==>|"Return Path via rt-spoke1<br/>-> 10.0.1.4 (Asymmetric!)"| NVA
    NVA -.->|"BGP route 172.16.0.0/16"| VPNGW
    NVA -.->|"UDR 172.17.0.0/16 -> 10.0.2.4"| Probe
    NVA -.->|"BGP route 172.18.0.0/16"| ERGW
    Hub ---|"10 VNet Peerings"| Spokes
```

## 2. Scenario S2 (Symmetric NVA Routing when Peering Routes Are Suppressed/Overridden on `rt-gw`)

```mermaid
flowchart TB
    subgraph OnPrem["3 Hybrid Entry Points (172.16.0.0/16, 172.17.0.0/16, 172.18.0.0/16)"]
        VMOnPrem["S2S VPN (172.16.0.0/16) / SD-WAN (172.17.0.0/16) / ExpressRoute (172.18.0.0/16)"]
    end

    subgraph Hub["Hub VNet: vnet-hub (10.0.0.0/16)"]
        Entry["vpngw-hub / ergw-hub (GatewaySubnet)<br/>& vm-hub-probe (snet-hub-probe)<br/>Route Table: rt-gw"]
        NVA["vm-hub-nva (10.0.1.4)<br/>snet-nva (10.0.1.0/24)<br/>Stateful iptables: 0 drops"]
    end

    subgraph Spokes["10 Peered Spoke VNets (10.1.0.0/16 .. 10.10.0.0/16)"]
        Spoke1["vnet-spoke1 (10.1.0.0/16)<br/>vm-spoke1 (10.1.1.4)"]
    end

    VMOnPrem <==>|"1. Hybrid BGP Connectivity"| Entry
    Entry ==>|"2. Forward Path -> NVA<br/>(disablePeeringRoute=All + 10.0.0.0/8 UDR<br/>OR explicit /16 UDRs)"| NVA
    NVA ==>|"3. Forward Path -> Spoke 1<br/>(NVA uses Default 10.1.0.0/16 VNetPeering)"| Spoke1
    Spoke1 ==>|"4. Return Path -> NVA<br/>(UDRs 172.16/16, 172.17/16, 172.18/16 -> 10.0.1.4)"| NVA
    NVA ==>|"5. Return Path -> Hybrid Entry"| Entry
```
