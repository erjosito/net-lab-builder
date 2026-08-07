# lessons-learned.md — TP-HH: Dual-Hub Interconnect and Route Server Route-Map Policy

## Results

**U0, U1 (T1), U1.5 and T2a/U2 executed 2026-08-06** — see the "TP-HH's own findings" section below
for the findings from this execution. T2b–T5 (U3–U5) have not run as of 2026-08-06; those sections
of this file will be populated only after each scenario runs.

---

## TP-HH's own findings (from U0/U1/U1.5/U2, executed 2026-08-06)

**U0, U1 (T1), U1.5 and T2a/U2 executed and PASSED** (U0 with one note) on 2026-08-06 — see
`validation.md` §U0/§T1/§U1.5/§T2a-U2 and `deploy-log.md` §Change log. U1.5 and T2a/U2 were
independently verified live (read-only) by Niobe on 2026-08-06 —
`.squad/decisions/inbox/niobe-u15-u2-verification.md`. T2b–T5 (U3–U5) have not run; the entries below
are TP-HH's own new findings, not inherited.

| Finding | One-line summary | Evidence |
|---|---|---|
| `TANK-001` — stale Poland-shaped static route re-originated by both NVAs | Both `vm-nva1`/`vm-nva2`'s hand-edited `/etc/bird/bird.conf` (still not in version control) carry a stray `protocol static` route `10.30.0.0/27` (the former Poland RouteServerSubnet shape) alongside the expected `10.10.0.64/27`/`10.20.0.64/27` and `0.0.0.0/0`. The `export_to_hub*_ars` filter only strips AS 65515 — it does **not** filter by prefix — so `10.30.0.0/27` is genuinely learned by both `ars-hub1` and `ars-hub2` as soon as the NVAs power on. **Contained:** it is absent from ARS's advertised-back routes, from `vpngw-hub1`/`vpngw-hub2` (their BGP session to the local ARS is pre-existing, permanently `Connecting` — not caused by U0/U1), and from `vpngw-onprem`'s learned routes; it appears only in each NVA's own NIC effective-route table within its own hub VNet. Whether it reaches `vnet-spoke-a`/`vnet-spoke-b` could not be verified since the spoke endpoint VMs correctly remained deallocated (out of U0/U1 scope). **Not a violation of validation.md's "No Poland prefix may appear anywhere" clause for U0/U1** because that clause governs the ARS/gateway/on-prem control-plane surfaces this task validated, all of which stayed clean — but it **is** a live discrepancy that must be reviewed before any future T2b work, since it also invalidates the manifest's assumption that NVA1 "re-originates `10.10.0.64/27`" (that prefix does not actually appear in ARS's learned-routes set — Azure Route Server appears to reject a route matching its own RouteServerSubnet). BIRD config was **not** edited in this session, per explicit scope. **Remediation (Trinity plan, executed by Tank 2026-08-06 — PASS on both NVAs, independently verified live by Niobe):** the new prerequisite approval unit **U1.5** removed exactly this state (and the dead `ars_poland_0/1` protocols, their `export_to_poland_ars` filters, and NVA2's dead `10.31.0.0/24`/`10.32.0.0/24` prepend clause) from both NVAs — $0, no Azure object touched, graceful `birdc configure` only, no rollback trigger met. Contract: `nva-config/README.md`; criteria and results: `validation.md` §U1.5; evidence: `show-output/new/u15-u2/{pre,u15-nva1,u15-nva2,b1}/`. The as-found configs are now in version control at `nva-config/bird-nva{1,2}.as-found-2026-08-06.conf`, and `nva-config/bird-nva{1,2}.u15-target.conf` are now the authoritative live configs, closing the "hand-edited, not in version control" gap. **Consequence for U3:** the dead target `10.10.0.64/27` is formally withdrawn and replaced by an injected RFC 5737 TEST-NET-2 prefix `198.51.100.0/24` (unit U3a) — see `manifest.md` §"U3 — target prefix selection". | `show-output/new/u0-u1/post-u0/02-nva1-bird-conf.txt`, `02-nva2-bird-conf.txt`, `04-post-ars-hub1-peer-nva1-learned.json`, `04-post-ars-hub2-peer-nva2-learned.json`, `08-post-nva1-nic-effective-routes.json`, `08-post-nva2-nic-effective-routes.json` |
| `TANK-001a` — a route matching the Route Server's own RouteServerSubnet is silently rejected by ARS | Corollary of `TANK-001`, promoted to its own finding because it invalidated a planned test. `vm-nva1`'s `bird.conf` contains `route 10.10.0.64/27` — the local RouteServerSubnet — and exports it through `export_to_hub_ars` **identically** to every other static, including the `10.30.0.0/27` that *is* learned. Yet `10.10.0.64/27` never appears in `ars-hub1`'s learned-route set, on either instance, with no error surfaced anywhere. The practical lesson is the dangerous part: an inbound route map keyed on such a prefix would provision `Succeeded` and match nothing, so the test would have *read* as a PASS while proving nothing at all. **Never select a route-map test target without first confirming it appears in `list-learned-routes`.** | `show-output/new/u0-u1/post-u0/02-nva1-bird-conf.txt` vs `04-post-ars-hub1-peer-nva1-learned.json` (re-confirmed by live read-only capture 2026-08-06) |
| `TRIN-001` — `PUT` on `virtualHubs/bgpConnections` silently drops omitted properties, including `staticRoutesConfig` | `Microsoft.Network/virtualHubs/bgpConnections` defines **no PATCH** operation, so an association must be written with `PUT`, which replaces `properties` wholesale. The live `peer-nva1` carries `routingConfiguration.vnetRoutes.staticRoutesConfig` = `{propagateStaticRoutes: true, vnetLocalRouteOverrideCriteria: "Contains"}`. The lab's original U2 placeholder bodies omitted `vnetRoutes` entirely and would have silently reset both settings to service defaults — a routing-behaviour change with no PASS criterion that would have caught it. **Rule adopted: the PUT body is derived from a fresh GET, never authored** — take `properties`, delete only `provisioningState`, add `inboundRouteMap.id`, send with `If-Match: <etag>`. **Applied and confirmed in U2's execution (2026-08-06):** the rule was followed exactly and `vnetRoutes`/`staticRoutesConfig` were preserved byte-for-byte across the round trip, independently re-verified by Niobe. **Related API trap confirmed:** `api-version=2024-05-01` omits `routingConfiguration` from the GET response entirely, making an existing association look absent — always use `2024-10-01` or later. | Live read-only `az rest GET .../bgpConnections/peer-nva1?api-version=2024-10-01`, 2026-08-06; `scripts/bodies/routemap-assoc-inert-body-hub1.json`; `show-output/new/u15-u2/u2/10-diff-summary.md` || `TANK-002` — `az vm run-command invoke` does not detach backgrounded (`nohup ... &`) processes | Attempting a continuous background ping probe via `nohup ping ... &` inside a `run-command invoke --scripts` call hung — the command appears to wait for the full lifetime of the backgrounded child rather than returning once the parent script exits. Workaround: use simple blocking `ping -c N` calls immediately before and shortly after the change instead of a true continuous background probe; sufficient to prove pre-change unreachability and post-change 0% loss without a live continuous matrix. | Session execution log; see `show-output/new/u0-u1/pre-u1/01-pre-ping-nva1-to-nva2.txt` and `post-u1/02-ping-nva1-to-nva2.txt` / `02-ping-nva2-to-nva1.txt` |
| `TANK-003` — `az group list --query "[?contains(...)]" -o tsv` parsing failure on this Windows PowerShell setup | Complex JMESPath filters using `[?...]` combined with `-o tsv` at the top level produced a cmd.exe-style parse error (`].name was unexpected at this time`) rather than an Azure CLI error. Simple `--query "[].{...}"` projections without `?contains()` filtering worked fine. Workaround: pipe `az group list -o table` into `Select-String` instead when this is suspected. Not fully root-caused (likely an az.cmd batch-wrapper quoting interaction); just avoided. | Session execution log (command scratch-run, not saved as lab evidence — a CLI tooling note, not lab data) |

---



These are the source lab's own findings, reproduced here **only as one-line pointers with a
backlink**. They are never restated as this lab's own findings — if TP-HH needs to reuse one of
these mechanisms, it re-derives or re-verifies the result under its own scenario evidence.

| Finding | One-line summary | Source |
|---|---|---|
| `EMP-001` / D2 locality constraint | Route maps can only attach to BGP peers whose peerIp is within the ARS VNet's own address space; undocumented by Microsoft as of 2026-08-03, runtime error is authoritative. This is *why* hub1/hub2 (not `ars-poland`) are TP-HH's only viable T2 attachment points. | `.squad/decisions.md` → D2; source lab `deploy-log.md` §"Δ3 Activation Attempt" |
| Route-map tier upgrade timings | `ars-hub1` Succeeded at +22.4 min, `ars-hub2` at +25.7 min (both triggered ~concurrently via `az rest` PUT, API `2024-10-01`). | source lab `deploy-log.md` §"Hub ARS Route-Map Upgrade" |
| `az rest` inline-body failure on Windows PowerShell | `az rest --body '{"json":"inline"}'` causes `UnsupportedMediaType: null` on Windows PowerShell (Content-Type header not set correctly for a raw inline string). Correct pattern: write the body to a `.json` file, then `az rest --body "@C:\full\path\to\body.json"`. **This applies directly to TP-HH's own `associate-hub-routemap.ps1` script** — every route-map/BGP-connection body is written to `scripts/bodies/*.json` and referenced with `@file`, never inlined. | `.squad/agents/tank/history.md` (Tank, 2026-08-05); source lab `show-output/route-map-upgrade/hub1-routemap-body.json` used as the template |
| `peeringState=null` CLI quirk | `az network routeserver peering list --query "[].peeringState"` returns `null` for all peers — the property is not populated by the ARS resource provider in the peering-list response. Use `provisioningState` instead when scripting a readiness check. | source lab `lessons-learned.md` §"ARS peeringState=null — CLI Behaviour Note" |
| PSK / IKE-SA lifetime observation | A PSK mismatch injected on `vpngw-hub1`↔`vpngw-onprem` did **not** drop the IKE SA within a ~3 min test window; all 4 VPN connections stayed reported `Connected` despite the mismatch. Anyone designing a PSK-based fault-injection test (relevant if T5 ever touches gateway connections) should account for this. | source lab `lessons-learned.md` §S2/S3 fault-injection section |
| `DEV-001` — PSK recovery via fresh secret (KV inaccessible) | When the original PSK could not be read back from Key Vault, a fresh matching PSK was set on both connection objects instead — functionally equivalent, tunnel re-establishes. PSK values were never logged, printed, or persisted in any file. | source lab `lessons-learned.md` §"DEV-001" |

---

## Stage 2 (TP-SQ) findings

| Finding | Result |
|---|---|
| `SQ-001` — the four connected sides do not imply end-to-end hybrid transit | All six VPN connection objects and every intended BGP adjacency can be healthy while DC1/DC2 endpoints still lack hub VNet reachability. The DCI carries site prefixes, and global peering carries the two hub address spaces, but native variant N does not compose these into transitive site↔remote-hub forwarding. |
| `SQ-002` — DCI and hub interconnect are independently healthy | DC1↔DC2 endpoint ICMP passed bidirectionally, and NVA1↔NVA2 ICMP passed bidirectionally. This isolates the missing site↔hub outcome from basic tunnel or peering failure. |
| `SQ-003` — Azure gateway BGP status includes self/unknown entries | Active-active gateway peer-status output contains expected `Unknown` self-neighbor rows alongside connected external peers. Readiness must be based on intended remote neighbors and connection objects, not “every row is Connected.” |
| `SQ-004` — connection list output is insufficient for readiness in this CLI build | `az network vpn-connection list` omitted useful runtime status; individual `show` calls returned the authoritative `Connected` state. Final certification queried every named connection separately. |
| `SQ-005` — a connected square is not a transit square | All four sides can be healthy while none of the requested spoke/hybrid services work. Physical adjacency, BGP adjacency, route advertisement, next-hop validity, and return path must be validated separately. |
| `SQ-006` — branch-to-branch did not export NVA summaries to simulated sites | Both hub gateways returned an empty advertised-route set toward their VNet-to-VNet site peers, even with branch-to-branch enabled. The Azure-gateway “on-premises” analogue cannot faithfully test enterprise-router import/export policy for these paths. |
| `SQ-007` — broad NVA export caused route feedback | Deleting ASN 65515 and accepting every imported route reflected site prefixes back to Route Server, producing shorter iBGP copies at the gateway and TTL loops. NVA export must be deny-by-default. |
| `SQ-008` — Route Server spoke injection requires a shorter supernet | Equal or longer advertisements than the VNet address space were not propagated. Bounded `/23` summaries were accepted by Route Server, matching Microsoft documentation, but the gateway still did not advertise them to the simulated sites. |
| `SQ-009` — PSK fault injection needs an explicit connection reset | Updating one directional connection's PSK did not immediately guarantee a clean fault. Calling the REST `resetconnection` operation forced renegotiation; restoration used a fresh matching key on both directional objects. |
| `SQ-010` — cross-VNet NVA peering requires remote Route Server consumption | Route Server supports an NVA in a directly peered VNet, but the remote VNet must enable **Use remote gateway or Route Server** and the upgraded API requires an explicit `hubVirtualNetworkConnection`. A VNet that already owns a VPN gateway cannot enable that setting, so NVA1 and NVA2 cannot consume the opposite hub's Route Server in this topology. |
| `SQ-011` — Route Server route maps reject `Vnet2Vnet` connections | The portal omitted the square's VPN objects because they are `Microsoft.Network/connections` with `connectionType=Vnet2Vnet`. A direct API attempt returned `InvalidRoutingConfigurationForConnectionType`; route-map-capable VPN connectivity must use supported S2S `IPsec` connection objects. |
| `SQ-012` — branch-to-branch learning and VPN export are separate gates | The hub gateways demonstrably learn NVA routes through Route Server, but advertise an empty set to the simulated-site `Vnet2Vnet` peers. The missing site routes are therefore not caused by disabled branch-to-branch or a failed ARS-to-gateway exchange. |

The following inherited constraints still govern any later failover experiment:

| Constraint carried forward | Where it bites in the square | Source |
|---|---|---|
| D2 locality (`EMP-001`) — superseded by SQ-010 | The old “same-VNet only” conclusion was too broad. Directly peered-VNet NVAs are supported, but require remote Route Server consumption and an explicit `hubVirtualNetworkConnection`; that prerequisite is incompatible with the two gateway-owning hub VNets in this lab. | `ars-peer-route-map-vpn-investigation.md` |
| ARS loop prevention runs **before** inbound policy | A map cannot rescue a 65515-carrying route; the NVA-side strip is permanent | design.md §5, §10.2 L2 |
| `az rest` inline-body failure on Windows PowerShell | Every Stage-2 route-map / BGP-connection body must be written to `scripts/bodies/*.json` and referenced with `@file` | Tank history 2026-08-05; design.md §11 |
| `peeringState=null` CLI quirk | Stage-2 readiness checks must key on `provisioningState` | source lab `lessons-learned.md` |
| PSK mismatch does **not** promptly drop the IKE SA (~3 min window observed) | A Stage-2 fault injection on S-A/S-C cannot rely on a PSK swap to produce a fast, clean fault | source lab `lessons-learned.md` §S2/S3 |
| `DEV-001` — PSK recovery via a fresh matching secret | Rollback step 6, recreating `conn-hub2-to-onprem` / `conn-onprem-to-hub2`, must assume the original PSK is unreadable and set a fresh matching pair | source lab `lessons-learned.md` §DEV-001 |
| `NonAzSkusNotAllowedForVPNGateway` / `VmssVpnGatewayPublicIpsMustHaveZonesConfigured` are invisible to `validate` and `what-if` | The S0 preflight gate is mandatory before `vpngw-onprem2` is attempted | design.md §10.4 |

**Nothing above is a Stage-2 result.** Stage-2 findings are written only after E0–E6 evidence exists,
and the square's verdict is chosen from the four possibilities in design.md §13.2 — never in advance.

---

## Backlinks

[README.md](./README.md) · [validation.md](./validation.md) · [manifest.md](./manifest.md) ·
source lab [`lessons-learned.md`](../dual-hub-hubless-region-ars/lessons-learned.md) (full findings,
referenced not duplicated) · source lab
[`deploy-log.md`](../dual-hub-hubless-region-ars/deploy-log.md).
