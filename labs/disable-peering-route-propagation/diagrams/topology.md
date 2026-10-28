# Architecture & Packet Flow Diagrams

## 1. Topology & Scenario S1 (Asymmetric Bypass when `disablePeeringRoute = None`)

```mermaid
flowchart TB
    subgraph OnPrem["Simulated On-Premises VNet (172.16.0.0/16)"]
        VMOnPrem["vm-onprem (172.16.1.4)<br/>StrongSwan IKEv2 + FRR BGP ASN 65010"]
    end

    subgraph Hub["Hub VNet: vnet-hub (10.0.0.0/16)"]
        VPNGW["vpngw-hub (VpnGw1AZ)<br/>GatewaySubnet (10.0.0.0/24)<br/>ASN 65515 | BGP IP 10.0.0.254<br/>Route Table: rt-gw"]
        NVA["vm-hub-nva (10.0.1.4)<br/>snet-nva (10.0.1.0/24)<br/>Stateful iptables / conntrack"]
        Probe["vm-hub-probe (10.0.2.4)<br/>snet-hub-probe (10.0.2.0/24)<br/>Route Table: rt-gw (Observer)"]
    end

    subgraph Spokes["10 Peered Spoke VNets (10.1.0.0/16 .. 10.10.0.0/16)"]
        Spoke1["vnet-spoke1 (10.1.0.0/16)<br/>vm-spoke1 (10.1.1.4)<br/>Route Table: rt-spoke1<br/>UDR: 172.16.0.0/16 -> 10.0.1.4"]
        SpokeN["vnet-spoke2 .. vnet-spoke10<br/>(10.2.0.0/16 .. 10.10.0.0/16)"]
    end

    VMOnPrem <==>|"S2S IPsec (vti0) + eBGP"| VPNGW
    VPNGW -.->|"S1 Forward Path (BYPASSES NVA!)<br/>Matches Default 10.1.0.0/16 VNetPeering<br/>over User 10.0.0.0/8 UDR"| Spoke1
    Spoke1 ==>|"S1 Return Path<br/>Matches UDR 172.16.0.0/16 -> 10.0.1.4<br/>(DROPPED by stateful NVA: ctstate INVALID)"| NVA
    NVA -.->|"System BGP route 172.16.0.0/16"| VPNGW
    Hub ---|"10 VNet Peerings"| Spokes
```

## 2. Scenario S2 (Symmetric NVA Routing when Peering Routes Are Suppressed/Overridden on `rt-gw`)

```mermaid
flowchart TB
    subgraph OnPrem["Simulated On-Premises VNet (172.16.0.0/16)"]
        VMOnPrem["vm-onprem (172.16.1.4)<br/>StrongSwan IKEv2 + FRR BGP ASN 65010"]
    end

    subgraph Hub["Hub VNet: vnet-hub (10.0.0.0/16)"]
        VPNGW["vpngw-hub (VpnGw1AZ)<br/>GatewaySubnet (10.0.0.0/24)<br/>Route Table: rt-gw"]
        NVA["vm-hub-nva (10.0.1.4)<br/>snet-nva (10.0.1.0/24)<br/>Stateful iptables: 0 drops"]
    end

    subgraph Spokes["10 Peered Spoke VNets (10.1.0.0/16 .. 10.10.0.0/16)"]
        Spoke1["vnet-spoke1 (10.1.0.0/16)<br/>vm-spoke1 (10.1.1.4)"]
    end

    VMOnPrem <==>|"1. S2S IPsec + eBGP"| VPNGW
    VPNGW ==>|"2. Forward Path -> NVA<br/>(disablePeeringRoute=All + 10.0.0.0/8 UDR<br/>OR explicit /16 UDRs)"| NVA
    NVA ==>|"3. Forward Path -> Spoke 1<br/>(NVA uses Default 10.1.0.0/16 VNetPeering)"| Spoke1
    Spoke1 ==>|"4. Return Path -> NVA<br/>(UDR 172.16.0.0/16 -> 10.0.1.4)"| NVA
    NVA ==>|"5. Return Path -> VPNGW<br/>(BGP route 172.16.0.0/16)"| VPNGW
```
