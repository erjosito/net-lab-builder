> Diagrams: _(pending Oracle dispatch)_

# msee-hairpin-hns-vwan-ipv6 — validation skeleton

> 📝 **Blog post:** _pending publication_ (Kid)

**Lab slug:** `msee-hairpin-hns-vwan-ipv6`
**Drafted:** 2026-06-15T23:32:10+02:00
**Status:** pre-deploy skeleton — fill in evidence at lab live time.
**Scenarios:** S1–S5 (per Morpheus lab card)
**Expected show-output file count:** ~20–25

---

## Pre-flight checks (sign-off checklist)

### Subscription & Resource Group

- [ ] Subscription context set: `az account show --query id -o tsv`
- [ ] Resource Group exists: `az group show -n <RG> --query '{name:name,location:location,provisioningState:properties.provisioningState}' -o json`
- [ ] KV secrets accessible: `az keyvault secret list --vault-name platform-secrets-1138 --query "length(value)" -o tsv` → expect ≥ 1

**Evidence file:** `show-output/00-preflight-rg.json`

### ER Circuit Provisioning Status (both circuits)

**HnS Circuit:**
```bash
az network express-route show -n <circuit1-name> -g <RG> \
  --query '{circuitProvisioningState:circuitProvisioningState,serviceProviderProvisioningState:serviceProviderProvisioningState,peerings:peerings[].{name:name,peeringType:peeringType,state:state}}' \
  -o json
```
**Expected:** `circuitProvisioningState=Enabled`, `serviceProviderProvisioningState=Provisioned`, both IPv4 and IPv6 peering states present.

**vWAN Circuit:**
```bash
az network express-route show -n <circuit2-name> -g <RG> \
  --query '{circuitProvisioningState:circuitProvisioningState,serviceProviderProvisioningState:serviceProviderProvisioningState,peerings:peerings[].{name:name,peeringType:peeringType,state:state}}' \
  -o json
```

**Evidence files:** `show-output/01-preflight-circuit1-status.json`, `show-output/02-preflight-circuit2-status.json`

### ER Gateway BGP Peer Status

**HnS ER GW (IPv4 + IPv6 peers):**
```bash
az network vnet-gateway list-bgp-peer-status -n <hns-ergw-name> -g <RG> \
  --query 'value[].{neighbor:neighbor,asn:asn,state:state,upTime:upTime}' \
  -o json
```
**Expected:** ≥2 peers up (one IPv4 MSEE peer, one IPv6 MSEE peer per circuit; or combined session showing both neighbors).

**vWAN ER GW (IPv4 + IPv6 peers):**
```bash
az network vhub bgpconnection list --vhub-name <vwan-hub-name> -g <RG> \
  --query 'value[].{name:name,peerIp:peerIp,peerAsn:peerAsn,connectionState:connectionState}' \
  -o json
```
**Expected:** ≥2 connections showing `connectionState="Connected"` (IPv4 + IPv6 to MSEE).

**Evidence files:** `show-output/03-preflight-hns-bgp-peers.json`, `show-output/04-preflight-vwan-bgp-peers.json`

### ER Direct Port Status (Path A only)

```bash
az network express-route port show -n <port-name> -g <RG> \
  --query '{provisioningState:properties.provisioningState,allocationStatus:properties.allocationStatus,etherType:properties.etherType,bandwidthGbps:properties.bandwidthGbps}' \
  -o json
```
**Expected:** `provisioningState=Succeeded`, `allocationStatus=Allocated`, `bandwidthGbps=10`.

**Evidence file:** `show-output/05-preflight-port-status.json`

---

## S1 — IPv4 ping HnS spoke → vWAN spoke via MSEE hairpin (baseline)

**Objective:** Confirm IPv4 reachability over MSEE hairpin; ER GW learns spoke prefixes; BGP peers up.

| # | Assertion | Verbatim command | Expected result | Evidence path |
|---:|---|---|---|---|
| 1 | HnS ER GW learned routes include vWAN spoke IPv4 (`10.4.0.0/24`) | `az network vnet-gateway list-learned-routes -n <hns-ergw-name> -g <RG> -o json` | `10.4.0.0/24` present with route origin showing MSEE/remote GW | `show-output/06-s1-hns-learned-routes.json` |
| 2 | HnS spoke VM effective route to vWAN spoke → next-hop = HnS GW | `az network nic show-effective-route-table -g <RG> --name <hns-spoke-vm-nic> -o table` | Route for `10.4.0.0/24` with `nextHopType=VirtualNetworkGateway` | `show-output/07-s1-hns-spoke-nic-routes.txt` |
| 3 | IPv4 ping HnS spoke VM → vWAN spoke VM succeeds (hair-pin works) | `az vm run-command invoke -g <RG> -n <hns-spoke-vm-name> --command-id RunShellScript --scripts 'ping -c 5 <vwan-spoke-vm-ip-ipv4>' 2>&1` | 5 packets sent, ≥4 packets received; round-trip time visible | `show-output/08-s1-hns-to-vwan-ipv4-ping.txt` |
| 4 | ER Circuit1 (HnS) route table shows vWAN peering subnet and spoke prefix | `az network express-route list-route-tables -n <circuit1-name> -g <RG> --path primary --peering-name AzurePrivatePeering -o json` | Primary path lists routes to MSEE and remote side (vWAN), including `10.4.0.0/24` | `show-output/09-s1-circuit1-route-table.json` |
| 5 | ER Circuit2 (vWAN) route table shows HnS peering subnet and spoke prefix | `az network express-route list-route-tables -n <circuit2-name> -g <RG> --path primary --peering-name AzurePrivatePeering -o json` | Primary path lists routes to MSEE and remote side (HnS), including `10.2.0.0/24` | `show-output/10-s1-circuit2-route-table.json` |

---

## S2 — IPv6 ping HnS spoke → vWAN spoke via MSEE hairpin (PRIMARY TEST)

**Objective:** Confirm dual-stack IPv6 reachability over MSEE hairpin; IPv6 BGP session established; ULA prefixes learned.

| # | Assertion | Verbatim command | Expected result | Evidence path |
|---:|---|---|---|---|
| 6 | HnS ER GW learned routes include vWAN spoke IPv6 (`fd00:4::/48`) | `az network vnet-gateway list-learned-routes -n <hns-ergw-name> -g <RG> -o json` | `fd00:4::/48` present; same route origin as IPv4 entry | `show-output/11-s2-hns-learned-routes-ipv6.json` |
| 7 | HnS spoke VM effective route to vWAN spoke IPv6 → next-hop = HnS GW | `az network nic show-effective-route-table -g <RG> --name <hns-spoke-vm-nic> -o table` | Route for `fd00:4::/48` with `nextHopType=VirtualNetworkGateway` | `show-output/12-s2-hns-spoke-nic-routes-ipv6.txt` |
| 8 | IPv6 ping HnS spoke VM → vWAN spoke VM succeeds (hair-pin + dual-stack works) | `az vm run-command invoke -g <RG> -n <hns-spoke-vm-name> --command-id RunShellScript --scripts 'ping6 -c 5 <vwan-spoke-vm-ip-ipv6>' 2>&1` | 5 packets sent, ≥4 packets received; IPv6 connectivity confirmed | `show-output/13-s2-hns-to-vwan-ipv6-ping.txt` |
| 9 | HnS BGP session to MSEE for IPv6 shows peer up and active | `az network vnet-gateway list-bgp-peer-status -n <hns-ergw-name> -g <RG> --query "value[?contains(neighbor, ':')]" -o json` | IPv6 neighbor (MSEE IPv6) present with `state=Connected` or `state=Up` | `show-output/14-s2-hns-bgp-ipv6-peer.json` |
| 10 | ER Circuit1 IPv6 peering status shows Enabled | `az network express-route peering show -n AzurePrivatePeering --express-route-name <circuit1-name> -g <RG> -o json` (or REST for IPv6 peering subnet detail) | IPv6 section present; `state=Enabled` | `show-output/15-s2-circuit1-ipv6-peering.json` |

---

## S3 — Route-table evidence (each ER GW learns other's spoke prefixes via MSEE)

**Objective:** Verify mutual prefix distribution; each GW advertises & learns spokes; MSEE hairpin is bidirectional.

| # | Assertion | Verbatim command | Expected result | Evidence path |
|---:|---|---|---|---|
| 11 | HnS GW advertised routes to MSEE include HnS spokes (IPv4 + IPv6) | `az network vnet-gateway list-advertised-routes -n <hns-ergw-name> -g <RG> -o json` | `10.2.0.0/24` (IPv4 spoke) and `fd00:2::/48` (IPv6 spoke) both present | `show-output/16-s3-hns-advertised-routes.json` |
| 12 | vWAN ER GW advertised routes to MSEE include vWAN spokes (IPv4 + IPv6) | `az network vhub bgpconnection list --vhub-name <vwan-hub-name> -g <RG> -o json \| jq '.value[] \| select(.name | contains("bgp")) \| .sourceAsn'` (or REST POST `/virtualHubs/<vwan-hub>/bgpConnections/<cx>/advertisedRoutes`) | vWAN spokes `10.4.0.0/24` (IPv4) and `fd00:4::/48` (IPv6) advertised to each peer | `show-output/17-s3-vwan-advertised-routes.json` |
| 13 | HnS GW learned routes INCLUDE vWAN spokes (S1 check + S2 check confirm this) | Carry forward S1 assertion #1 + S2 assertion #6 | `10.4.0.0/24` and `fd00:4::/48` both learned | `show-output/11-s2-hns-learned-routes-ipv6.json` (evidence reused from S2) |
| 14 | vWAN ER GW learned routes INCLUDE HnS spokes (IPv4 + IPv6) | `az network vhub bgpconnection list --vhub-name <vwan-hub-name> -g <RG> -o json` (or REST POST `/virtualHubs/<vwan-hub>/bgpConnections/<cx>/learnedRoutes`) | HnS spokes `10.2.0.0/24` and `fd00:2::/48` present in learned routes | `show-output/18-s3-vwan-learned-routes.json` |

---

## S4 — Disable `allowVirtualWanTraffic`; confirm hairpin breaks (deliberate-break)

**Objective:** Toggle the hairpin-enabling flag off; verify ER connectivity severs; toggle back to restore.

### Phase A — Inject breakage

| # | Assertion / Action | Verbatim command | Expected result | Evidence path |
|---:|---|---|---|---|
| 15 | Pre-disable baseline: S1/S2 connectivity passes | Re-run S1 assertion #3 (IPv4 ping) and S2 assertion #8 (IPv6 ping) | Both pass; carry forward as baseline | `show-output/19-s4-pre-disable-s1-ipv4.txt`, `show-output/20-s4-pre-disable-s2-ipv6.txt` |
| 16 | Disable `allowVirtualWanTraffic` on HnS ER GW | `az network vnet-gateway update -n <hns-ergw-name> -g <RG> --set properties.allowVirtualWanTraffic=false` | Command succeeds; no error | `show-output/21-s4-toggle-disable.txt` |
| 17 | Verify flag is OFF: HnS GW config shows `allowVirtualWanTraffic=false` | `az network vnet-gateway show -n <hns-ergw-name> -g <RG> --query 'properties.{allowVirtualWanTraffic:allowVirtualWanTraffic,allowRemoteVnetTraffic:allowRemoteVnetTraffic}' -o json` | `allowVirtualWanTraffic: false` | `show-output/22-s4-verify-flag-off.json` |
| 18 | BGP session to MSEE drops within 30–60 sec (watch peer state) | `az network vnet-gateway list-bgp-peer-status -n <hns-ergw-name> -g <RG> --query "value[].{neighbor:neighbor,state:state}" -o json` | Peer state = `Down` or `Idle` (session terminated) | `show-output/23-s4-bgp-peer-down.json` |
| 19 | IPv4 ping HnS → vWAN fails (no route) | `az vm run-command invoke -g <RG> -n <hns-spoke-vm-name> --command-id RunShellScript --scripts 'timeout 5 ping -c 5 <vwan-spoke-vm-ip-ipv4> || echo "TIMEOUT/UNREACHABLE"' 2>&1` | Packets timeout; 0% success | `show-output/24-s4-ping-blocked-ipv4.txt` |
| 20 | IPv6 ping HnS → vWAN fails (no route) | `az vm run-command invoke -g <RG> -n <hns-spoke-vm-name> --command-id RunShellScript --scripts 'timeout 5 ping6 -c 5 <vwan-spoke-vm-ip-ipv6> || echo "TIMEOUT/UNREACHABLE"' 2>&1` | Packets timeout; 0% success | `show-output/25-s4-ping-blocked-ipv6.txt` |
| 21 | HnS learned-routes now EMPTY or no vWAN prefixes | `az network vnet-gateway list-learned-routes -n <hns-ergw-name> -g <RG> -o json` | No routes learned from remote (MSEE hairpin closed) | `show-output/26-s4-learned-routes-empty.json` |

### Phase B — Revert and verify

| # | Assertion / Action | Verbatim command | Expected result | Evidence path |
|---:|---|---|---|---|
| 22 | Re-enable `allowVirtualWanTraffic` on HnS ER GW | `az network vnet-gateway update -n <hns-ergw-name> -g <RG> --set properties.allowVirtualWanTraffic=true` | Command succeeds | `show-output/27-s4-toggle-enable.txt` |
| 23 | Verify flag is ON: HnS GW config shows `allowVirtualWanTraffic=true` | `az network vnet-gateway show -n <hns-ergw-name> -g <RG> --query 'properties.{allowVirtualWanTraffic:allowVirtualWanTraffic,allowRemoteVnetTraffic:allowRemoteVnetTraffic}' -o json` | `allowVirtualWanTraffic: true` | `show-output/28-s4-verify-flag-on.json` |
| 24 | BGP session recovers within 30–60 sec (wait, then check peer state) | Wait 60s, then: `az network vnet-gateway list-bgp-peer-status -n <hns-ergw-name> -g <RG> --query "value[].{neighbor:neighbor,state:state}" -o json` | Peer state = `Connected` or `Up` | `show-output/29-s4-bgp-peer-up.json` |
| 25 | IPv4 ping HnS → vWAN passes again (symmetry restored) | Re-run S1 assertion #3 command | ≥4 pings success; connectivity restored | `show-output/30-s4-ping-restored-ipv4.txt` |
| 26 | IPv6 ping HnS → vWAN passes again (symmetry restored) | Re-run S2 assertion #8 command | ≥4 pings success; IPv6 restored | `show-output/31-s4-ping-restored-ipv6.txt` |

---

## S5 — IPsec S2S BGP fallback (stretch; only if S2 fails or Jose requests)

**Objective:** *(SKETCH — expand only if lab pivots to Path C; primary test is S1–S4)*

| # | Assertion | Verbatim command | Expected result | Evidence path |
|---:|---|---|---|---|
| 27 | S5 only runs if S2 (IPv6 MSEE hairpin) fails OR Jose explicitly approves Path C pivot | — | See Jose gate in lab-card.md §10 | — |
| 28 | If Path C: VPN GW BGP session to MSEE shows IPv6 neighbor up | `az network vpn-gateway list -g <RG> -o json \| jq '.[] \| .name'` (then BGP peer status for that GW) | IPv6 peer present and `Connected` | `show-output/32-s5-vpn-bgp-ipv6-peer.json` |
| 29 | IPv6 ping via IPsec tunnel succeeds (same endpoints as S2, but via S2S, not MSEE) | Same VM command as S2 #8 | ≥4 pings success | `show-output/33-s5-ipsec-ipv6-ping.txt` |

---

## Three-layer route-collection checklist

**Mandatory per charter § "Three-layer route collection when ER is involved."** For this lab: ER Gateway layer + ER Circuit layer only (no Megaport MCR, no vWAN hub REST inbound/outbound routes — MSEE hairpin is simpler topology).

| Layer | Description | Commands | File(s) | Captured |
|---|---|---|---|---|
| **A1** | HnS ER GW learned routes (IPv4 + IPv6) | `az network vnet-gateway list-learned-routes -n <hns-ergw-name> -g <RG> -o json` | `show-output/06-s1-hns-learned-routes.json`, `show-output/11-s2-hns-learned-routes-ipv6.json` | ☐ |
| **A2** | HnS ER GW advertised routes (IPv4 + IPv6) | `az network vnet-gateway list-advertised-routes -n <hns-ergw-name> -g <RG> -o json` | `show-output/16-s3-hns-advertised-routes.json` | ☐ |
| **A3** | vWAN ER GW learned routes (IPv4 + IPv6) | `az network vhub bgpconnection list --vhub-name <vwan-hub-name> -g <RG> -o json` (or REST POST `learnedRoutes`) | `show-output/18-s3-vwan-learned-routes.json` | ☐ |
| **A4** | vWAN ER GW advertised routes (IPv4 + IPv6) | `az network vhub bgpconnection list --vhub-name <vwan-hub-name> -g <RG> -o json` (or REST POST `advertisedRoutes`) | `show-output/17-s3-vwan-advertised-routes.json` | ☐ |
| **B1** | ER Circuit1 route table (primary path, AzurePrivatePeering) | `az network express-route list-route-tables -n <circuit1-name> -g <RG> --path primary --peering-name AzurePrivatePeering -o json` | `show-output/09-s1-circuit1-route-table.json` | ☐ |
| **B2** | ER Circuit2 route table (primary path, AzurePrivatePeering) | `az network express-route list-route-tables -n <circuit2-name> -g <RG> --path primary --peering-name AzurePrivatePeering -o json` | `show-output/10-s1-circuit2-route-table.json` | ☐ |

**Total expected files in `show-output/` at lab end: ~31 (preflight + S1–S4 evidence).**

---

## Post-deploy validation order

1. **Run pre-flight checks** (§ "Pre-flight checks" above — 6 files, must all pass).
2. **Wait 2 min for ER circuits to stabilize after GW config propagates.**
3. **Run S1 (IPv4 baseline)** — assertions #1–5 (5 files).
4. **Run S2 (IPv6 primary)** — assertions #6–10 (5 files).
5. **Run S3 (route-table evidence)** — assertions #11–14 (4 files; reuse S1/S2 evidence where noted).
6. **Run S4 (deliberate-break)** — Phase A disable (7 files) + Phase B revert (6 files = 13 total).
7. **Final check:** All assertions Pass (or documented anomaly), all files present, sanitization sweep done.
8. **Skip S5** unless Jose explicitly gates it (see lab-card.md §10).

---

## BGP Peer Status Check Pattern (before capturing routes)

**Always run this FIRST in each scenario to confirm peering is up, then proceed to route/ping capture.**

**HnS ER GW:**
```bash
az network vnet-gateway list-bgp-peer-status -n <hns-ergw-name> -g <RG> \
  --query 'value[] | {neighbor:neighbor,asn:asn,state:state,upTime:upTime}' -o table
```

**vWAN ER GW:**
```bash
az network vhub bgpconnection list --vhub-name <vwan-hub-name> -g <RG> \
  --query 'value[] | {name:name,sourceAsn:sourceAsn,peerAsn:peerAsn,connectionState:connectionState}' -o table
```

**Pass criteria:** All peers show `state=Connected` or `state=Up` (HnS) / `connectionState=Connected` (vWAN). If any peer is Down/Idle, BGP convergence is incomplete — wait 30–60 sec and retry.

---

## Sanitization checklist (pre-commit — every file in `show-output/`)

| Item | Replace with | Verified |
|---|---|---|
| Subscription ID GUIDs in resource IDs | `<SUBSCRIPTION_ID>` | ☐ |
| ER service keys (circuit provisioning UUID) | `<ER_SERVICE_KEY_REDACTED>` | ☐ |
| VM admin passwords (if visible in run-command output) | `<REDACTED>` | ☐ |
| Base64-encoded tokens / SAS / JWT | `<TOKEN_REDACTED>` | ☐ |

---

## Designs Studied

| # | Design | Status | Verdict | Evidence | Why this verdict | Use when | Avoid when |
|---|---|---|---|---|---|---|---|
| **A** | ER Direct — MSEE hairpin (dual-stack IPv4+IPv6) | _pending evidence_ | ✅ Recommended if S1–S2 pass with learned routes + connectivity | S1–S4 evidence files | ER hairpinning eliminates Megaport dependency; dual-stack BGP proven viable; port free first 45 days from provisioning | Testing MSEE multi-tenant reflector; no on-prem site needed | Lab needs to outlive the 45-day free port window, or Megaport preference |
| **B** | Megaport circuits — MSEE hairpin (fallback) | _pending evidence_ | ⚠️ Not recommended per Jose gate | N/A (not deployed in Path A) | Cheaper port + MCR BGP adds complexity; Jose explicit "no Megaport" constraint | Downgrade if Path A cost overruns | Jose has ruled out for this lab |
| **C** | IPsec VPN — S2S with BGP (anti-pattern / stretch) | _pending evidence_ | 📚 Teaching-only (mechanism differs entirely) | S5 evidence (if captured) | Dual-stack VPN over IKEv2 is valid but not an MSEE hairpin; different test surface | Demonstrating site-to-site VPN as ER fallback | Replacing ER Direct for hairpin use-case |

---

## Lab-live deliverables (after deploy — separate dispatch)

- `show-output/` (~31 files, numbered, one command per file, verbatim capture)
- `screenshots/` — ER GW config blade (`allowVirtualWanTraffic` toggle), ER circuit peering blade (IPv6), circuit status blade
- `lessons-learned.md`
- `README.md` finalization (exec summary, deployed shape, validation results)
- `validation.md` fill-in (Pass/Fail + evidence paths — this file)

---

_Niobe — Lab Validator & Diagnostics | pre-deploy skeleton | 2026-06-15T23:32:10+02:00_
