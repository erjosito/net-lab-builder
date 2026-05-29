# expressroute-megaport-bgp

ExpressRoute + Megaport MCR validation lab for a Spain Central VNet connected through a provider-based ExpressRoute circuit and two Megaport VXCs.

## Deployed state validated

- Resource group: `rg-erlab-spaincentral`
- ExpressRoute circuit: `er-erlab-madrid`
- ExpressRoute gateway: `ergw-erlab-spaincentral`
- ER connection: `erconn-erlab`
- Validation VM: `vm-erlab-test` / NIC `nic-erlab-vm`
- Megaport MCR: Frankfurt FR5 (`locationId=131`)
- MCR-advertised routes observed in Azure: `172.31.100.0/24`, `172.31.101.1/32`

## Outcomes / validation results

- Provider gate passed: circuit is `Enabled` and `serviceProviderProvisioningState` is `Provisioned`.
- Azure gateway learned the MCR prefixes on both gateway instances, and the VM NIC effective route table points those prefixes to `VirtualNetworkGateway`.
- Megaport MCR and both VXCs are `LIVE`; both VXC resources report VLL `up: 1`.
- VLAN finding: both primary and secondary VXCs are configured with VLAN `100`. This matches Tank's report and differs from the preferred `100/200` plan.
- The ER circuit route-table CLI command returned `Gateway does not have any Bgp sessions` on both primary and secondary paths despite ARP, gateway learned routes, and VM effective routes showing convergence.
- MCR looking-glass/route-community evidence was inconclusive because the documented API path returned no endpoint in this session.
- Late VM ping and effective NSG checks were blocked because the VM deallocated; no start/action was taken.

See `validation.md` for pass/fail detail and `show-output/` for raw sanitized command output.

## Evidence layout

- `show-output/` — one file per command, with the exact command as line 1.
- `validation.md` — checklist derived from `manifest.md` §6 and §9.
- `lessons-learned.md` — live gotchas and anomalies captured during validation.
- `screenshots/` — created for optional screenshots; no screenshots captured in this run.
- `diagrams/` — topology drawio, BGP control plane, route propagation, and cleanup-chain diagrams.

## Diagrams

### Diagram 1 — Physical / logical topology

Three-zone overview: Megaport MCR in Frankfurt FR5, Equinix FR5 peering location with MSEE primary and secondary routers, and the Azure Spain Central VNet with ER gateway and test VM. Shows both VXC connections and the private peering link.

Open in draw.io for the full interactive view: [Source (draw.io)](diagrams/01-topology.drawio)

### Diagram 2 — BGP control plane

BGP session graph showing eBGP sessions between the Megaport MCR (ASN 64512) and the two MSEE peers (ASN 12076), then the iBGP relay to the ER gateway. Includes VXC IDs, VLAN 100, link-local BGP addresses, and the 2-route-received count on both gateway sessions.

```mermaid
flowchart LR
    MCR["Megaport MCR\nd801e2cd\nASN 64512\nFrankfurt FR5"]

    subgraph Peering["Equinix FR5 Peering Location"]
        MSEE_PRI["MSEE Primary\n10.100.255.4\nASN 12076"]
        MSEE_SEC["MSEE Secondary\n10.100.255.5\nASN 12076"]
    end

    ERGW["ER Gateway\nergw-erlab-spaincentral\nASN 12076\nLocal 10.100.255.13"]

    MCR -- "VXC cbb7a449 / VLAN 100\n169.254.194.41 ↔ 169.254.194.42\neBGP" --> MSEE_PRI
    MCR -- "VXC 60e77813 / VLAN 100\n169.254.194.45 ↔ 169.254.194.46\neBGP" --> MSEE_SEC
    MSEE_PRI -- "iBGP 10.100.255.4 ↔ .13\n2 routes received" --> ERGW
    MSEE_SEC -- "iBGP 10.100.255.5 ↔ .13\n2 routes received" --> ERGW

    classDef megaport fill:#ffe6cc,stroke:#d6b656,color:#000
    classDef msee fill:#00188D,color:#fff
    classDef azure fill:#dae8fc,stroke:#6c8ebf,color:#000

    class MCR megaport
    class MSEE_PRI,MSEE_SEC msee
    class ERGW azure
```

[Source (Mermaid)](diagrams/02-bgp-control-plane.mmd)

### Diagram 3 — Route propagation

Sequence diagram tracing prefix flow in both directions: MCR-originated prefixes (`172.31.100.0/24`, `172.31.101.1/32`) propagating into Azure with BGP community `12076:51013`, and the VNet prefix (`10.100.0.0/16`) flowing back to the MCR.

```mermaid
sequenceDiagram
    participant MCR as Megaport MCR\nASN 64512
    participant MSEE_P as MSEE Primary\n10.100.255.4
    participant MSEE_S as MSEE Secondary\n10.100.255.5
    participant ERGW as ER Gateway\n10.100.255.13

    Note over MCR,ERGW: Outbound: MCR → Azure (MCR-originated prefixes)
    MCR->>MSEE_P: eBGP UPDATE 172.31.100.0/24, 172.31.101.1/32\n(VXC cbb7a449 / 169.254.194.41→.42)
    MCR->>MSEE_S: eBGP UPDATE 172.31.100.0/24, 172.31.101.1/32\n(VXC 60e77813 / 169.254.194.45→.46)
    MSEE_P->>ERGW: BGP UPDATE → 172.31.100.0/24, 172.31.101.1/32\ncommunity 12076:51013 (Spain Central)
    MSEE_S->>ERGW: BGP UPDATE → 172.31.100.0/24, 172.31.101.1/32\ncommunity 12076:51013 (Spain Central)
    Note over ERGW: Installs routes in VNet effective route table\nvia VirtualNetworkGateway next-hop

    Note over MCR,ERGW: Inbound: Azure → MCR (VNet prefix)
    ERGW->>MSEE_P: BGP UPDATE → 10.100.0.0/16
    ERGW->>MSEE_S: BGP UPDATE → 10.100.0.0/16
    MSEE_P->>MCR: eBGP UPDATE → 10.100.0.0/16
    MSEE_S->>MCR: eBGP UPDATE → 10.100.0.0/16
    Note over MCR: 10.100.0.0/16 reachable from on-prem
```

[Source (Mermaid)](diagrams/03-route-propagation.mmd)

### Diagram 4 — Cleanup chain

Ordered teardown sequence from VXC deletion through MCR, ER connection, ER circuit, ER gateway (20–45 min), gateway public IP, and final resource group deletion. Colour-coded: orange = Megaport resources, blue = Azure resources.

```mermaid
flowchart TD
    Start([Begin Teardown]) --> VXC1
    VXC1["Delete Primary VXC\ncbb7a449"] --> VXC2
    VXC2["Delete Secondary VXC\n60e77813"] --> MCR_del
    MCR_del["Delete Megaport MCR\nd801e2cd"] --> ERConn
    ERConn["Delete ER Connection\nerconn-erlab\naz network vpn-connection delete"] --> ERCircuit
    ERCircuit["Delete ER Circuit\ner-erlab-madrid\naz network express-route delete"] --> ERGW
    ERGW["Delete ER Gateway\nergw-erlab-spaincentral\naz network vnet-gateway delete\n(20-45 min)"] --> GWIP
    GWIP["Delete Public IP for Gateway"] --> RG
    RG["Delete Resource Group\nrg-erlab-spaincentral\naz group delete"] --> Done

    Done([Lab fully torn down])

    style Start fill:#e8f5e9,stroke:#2e7d32
    style Done fill:#e8f5e9,stroke:#2e7d32
    style VXC1 fill:#ffe6cc,stroke:#d6b656
    style VXC2 fill:#ffe6cc,stroke:#d6b656
    style MCR_del fill:#ffe6cc,stroke:#d6b656
    style ERConn fill:#dae8fc,stroke:#6c8ebf
    style ERCircuit fill:#dae8fc,stroke:#6c8ebf
    style ERGW fill:#dae8fc,stroke:#6c8ebf
    style GWIP fill:#dae8fc,stroke:#6c8ebf
    style RG fill:#dae8fc,stroke:#6c8ebf
```

[Source (Mermaid)](diagrams/04-cleanup-chain.mmd)
