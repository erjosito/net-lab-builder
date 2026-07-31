---
name: "vwan-ri-routemap-preservation"
description: "Checklist and analysis pattern for enabling Routing Intent on a vWAN secured hub that already carries summarization or manipulation route-maps on VPN connections, without destroying the route-map output."
domain: "azure-networking-lab-design"
confidence: "medium"
source: "earned — derived from vwan-routemap-summarization Phase 3 design, 2026-07-30. Confirmed against MS docs (how-to-routing-policies). Gate A empirically validated 2026-07-31 (FULL PASS, both hubs). Gate B empirically validated 2026-07-31 (FULL PASS — RI PrivateTraffic on hub-eu1 does NOT suppress route-map summaries). Gate C empirically validated 2026-07-31 (FULL PASS — RI on BOTH hubs; missing-summary bug NOT reproduced under sequential enablement; concurrent-churn variant untested)."
---

## Context

Applies when ALL of the following are true:
1. A vWAN hub has one or more **route-maps** applied to VPN connections (outbound summarization,
   inbound prepend, or similar).
2. The hub is being **converted to a secured hub** (Azure Firewall deployed into hub).
3. **Routing Intent PrivateTraffic** is being enabled on that hub.

The risk: Routing Intent installs RFC1918 aggregate routes (10.0.0.0/8, 172.16.0.0/12,
192.168.0.0/16) in the hub's defaultRouteTable. Whether this suppresses the more-specific
prefixes from per-connection advertisement (which the route-map needs to evaluate) is the
central question.

Skip this skill if: no route-maps on any VPN connections, or RI is InternetTraffic-only.

---

## The core tension

| Layer | What happens |
|-------|-------------|
| Route-map (summarize-out) | Operates on **per-connection outbound effective routes** — the set of prefixes the hub is about to advertise to the VPN-connected on-prem. Matches specific /24s with `Contains`, replaces them with summary /16 or /17. Needs SPECIFICS to function. |
| Routing Intent PrivateTraffic | Installs RFC1918 supernets in **defaultRouteTable** for forwarding purposes (directing private traffic through AzFW). Docs say spoke /24s from remote unsecured hubs should STILL be individually propagated. |
| Risk | If RI's RFC1918 aggregate suppresses the /24 specifics from appearing in the outbound advertisement set (before route-map evaluation), summaries are absent — not because of rule ordering but because the route-map has nothing to match. |

---

## Sequencing pattern (mandatory)

**Never enable Routing Intent simultaneously with Azure Firewall deployment.** Always:

1. **Deploy AzFW** into hub (no RI). Wait for Succeeded.
2. **Gate A**: Run `az network vhub route-map get-outbound-routes` on VPN connections.
   - Pass: N/N summaries present, 0 /24 leaks.
   - Fail: AzFW deployment broke route-maps. Investigate before enabling RI.
3. **Enable RI PrivateTraffic** on hub.
4. **Gate B**: Re-run outbound routes check.
   - Pass: summaries intact → RI is safe with this route-map configuration.
   - Fail: Repro found. Document which summaries missing, save defaultRouteTable state.

If multiple hubs carry route-maps, enable RI **one hub at a time** and gate after each,
enabling isolation of which hub's RI state triggers the bug.

---

## Azure Firewall SKU in vWAN

| SKU | vWAN secured hub | Notes |
|-----|-----------------|-------|
| Basic | ❌ NOT supported | VNet-only deployment |
| Standard | ✅ Supported | Minimum for secured hub; use for repro labs |
| Premium | ✅ Supported | Add only if IDPS or TLS inspection required |

---

## Subnet requirements for vWAN secured hubs

**No explicit AzureFirewallSubnet or AzureFirewallManagementSubnet needed.**
The vWAN hub manages firewall IP allocation internally from the hub address prefix (/23 or larger).
The platform carves approximately /26 equivalent from the hub prefix for AzFW instances.
Operator action: confirm hub prefix has sufficient space (a /23 is always adequate).

---

## RI pre-enablement prerequisites

Check BOTH before enabling RI (RI creation fails if violated):

1. No custom route tables (only `defaultRouteTable` and `noneRouteTable` may exist):
   ```bash
   az network vhub route-table list -g <rg> --vhub-name <hub> -o table
   ```
2. No static routes in defaultRouteTable with `nextHop` pointing to a VNet Connection:
   ```bash
   az network vhub route-table show -g <rg> --vhub-name <hub> -n defaultRouteTable -o json
   ```

---

## RI and defaultRouteTable — what changes

After enabling RI PrivateTraffic (via portal or CLI), the defaultRouteTable gains:

| Route name | Prefixes | Next hop |
|------------|----------|---------|
| `_policy_PrivateTraffic` | `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` | AzFW resource |

⚠️ **This change is NOT automatically reversible.** Save defaultRouteTable JSON BEFORE enabling RI:
```bash
az network vhub route-table show -g <rg> --vhub-name <hub> -n defaultRouteTable -o json \
  > hub-defaultRT-pre-ri.json
```

---

## Advertising routes to on-prem with RI PrivateTraffic

Per MS docs (`how-to-routing-policies` — prefix advertisements section):

- Hub WITH RI advertises to local on-prem:
  - Routes from local hub VNets, VPN, ER, BGP connections
  - Routes from **remote hubs WITH RI**
  - Routes from **remote hubs WITHOUT RI** where those connections propagate to the local hub's
    defaultRouteTable (this is the default)

→ If hub-us has NO RI, spoke /24s from hub-us SHOULD still be individually propagated to
secured hub-eu1/eu2 via inter-hub → route-map sees specifics → summaries produced.

→ This is the expected behavior, NOT guaranteed until empirically validated (Phase 3 Niobe gates).

---

## BGP health with RI PrivateTraffic

With RI PrivateTraffic, **BGP sessions between the hub VPN gateway and on-prem NVAs are
routed through AzFW** (BGP TCP 179 is private traffic). Firewall must have an ALLOW rule for:
- Source: vpngw instance IPs (within hub /23 prefix block)
- Destination: NVA private IP
- Protocol: TCP, Port: 179 (or any/any for lab allow-all)

If BGP drops after RI enablement → first suspect is missing firewall rule for BGP, not RI itself.

---

## Measurement commands (Niobe)

```bash
# Outbound effective routes per VPN connection (key measurement)
# NOTE: --resource-uri is the correct flag, NOT --connection-name (unrecognized by CLI)
# Full ARM URI required:
#   /subscriptions/<SUB>/resourceGroups/<RG>/providers/Microsoft.Network/vpnGateways/<gw>/vpnConnections/<conn>
# Get the URI: az network vpn-gateway connection show -g <rg> --gateway-name <gw> -n <conn> --query id -o tsv
az network vhub route-map get-outbound-routes \
  -g <rg> \
  --vhub-name <hub> \
  --connection-type VpnConnection \
  --resource-uri "/subscriptions/<SUB>/resourceGroups/<RG>/providers/Microsoft.Network/vpnGateways/<gw>/vpnConnections/<conn>" \
  -o json
# ⚠️ WARNING: This API currently returns empty output (exit 0, no body) for secured hubs
# with route-maps in swedencentral/westeurope preview regions. Use L2 BIRD RIB as fallback.
# Evidence: labs/vwan-routemap-summarization/show-output/17, 29.

# Route-map still applied check
az network vhub route-map list -g <rg> --vhub-name <hub> -o table

# NVA BIRD RIB (authoritative fallback when get-outbound-routes is non-functional)
# Run via: az vm run-command invoke -g <rg> -n <nva> --command-id RunShellScript --scripts "sudo birdc show route" --query "value[0].message" -o tsv
# birdc show route   — shows all routes; filter manually for 10.0-10.4 summaries vs /24 leaks
# birdc show route count  — total routes/networks
# birdc show protocols    — confirm vpngw0+vpngw1 Established
```

---

## Empirical results summary (Gate A→B→C, 2026-07-31)

| Gate | State | nva1 (hub-eu1) | nva2 (hub-eu2) | Verdict |
|------|-------|----------------|----------------|---------|
| A | FW deployed, RI OFF | 6/6, 0 leaks | 6/6, 0 leaks | PASS |
| B | RI ON hub-eu1 | 6/6, 0 leaks | 6/6, 0 leaks | PASS |
| C | RI ON BOTH hubs | 6/6, 0 leaks | 6/6, 0 leaks | PASS — bug not reproduced |

**Key finding:** Under sequential RI enablement (stable state), RI PrivateTraffic does NOT
suppress outbound route-map summarization at any gate. The bug (missing summary reported in
production) was not reproduced. Possible trigger: concurrent VPN connection churn during RI
enablement (not tested). Recommend a "concurrent-churn Gate C" variant for a complete repro attempt.

## Citations

- Design spec: `labs/vwan-routemap-summarization/design-phase3.md`
- Gate A evidence: `labs/vwan-routemap-summarization/show-output/23-30`
- Gate B evidence: `labs/vwan-routemap-summarization/show-output/34-39`
- Gate C evidence: `labs/vwan-routemap-summarization/show-output/43-52`
- Validation record: `labs/vwan-routemap-summarization/validation.md` (Phase 3 Gate A/B/C sections)
- MS docs source: `https://learn.microsoft.com/en-us/azure/virtual-wan/how-to-routing-policies`
  (sections: Prefix advertisement to on-premises → Private routing policy; Static routes; Prerequisites)
- Niobe skill: `.squad/skills/vwan-secured-hub-detection/SKILL.md`

---

## Root-cause analysis: why steady-state RI + route-map coexist (Trinity, 2026-07-31)

### Layer separation

| Layer | Mechanism | Plane | Who is affected |
|-------|-----------|-------|----------------|
| RI `_policy_PrivateTraffic` | Installs 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 as static routes in hub defaultRouteTable → next-hop AzFW | **Data-plane / forwarding** | Packets in transit through hub |
| `summarize-out` route-map | Applied per-connection during BGP outbound advertisement set computation; matches specific /24 prefixes learned via inter-hub BGP propagation; replaces with summary /16+/17 | **Control-plane / BGP advertisement** | BGP UPDATE messages toward NVA |

**Why no collision in steady state:** The hub VPN gateway's outbound advertisement set is derived from **learned BGP routes** (hub-us spoke /24s propagated via inter-hub), not from defaultRouteTable static entries. RI's RFC1918 aggregate is a forwarding directive; it does not participate in the per-connection BGP advertisement pipeline. In a hub where no remote hub carries RI (hub-us is unsecured), spoke /24 specifics propagate individually, and the route-map evaluation input is unchanged.

**Empirical confirmation:** BGP session timestamps on nva1 (vpngw0: 07:37:23, vpngw1: 07:37:38) were identical across Gates A, B, and C. Neither RI enablement reset or interrupted the BGP control plane. RIBs on both NVAs were structurally identical (37/27 routes) throughout.

### Why sequential stable-state masked the production bug

The lab applied RI to a fully converged hub:
- BGP sessions healthy and stable before RI enable  
- No concurrent VPN connection churn (teardown/re-establishment)  
- Hub advertisement-set computation was not racing against a reconvergence event  

The production bug requires a concurrent trigger (see Gate D below).

---

## Gate D: concurrent-churn experiment design (Trinity, 2026-07-31)

**Status: DORMANT** — do not run until Jose explicitly authorizes.

### Hypothesis

The missing-summary bug fires when RI policy-install races with VPN connection reconvergence on the same hub. If the hub recomputes per-connection outbound advertisement export during RI programming AND the NVA's BGP session is simultaneously tearing down/re-establishing, the /24 specifics may be transiently absent from the route-map evaluation input. A cached zero-match result persists after reconvergence → missing summary in steady state.

**Failure matrix mapping (design-phase3.md §7):** F5 (VPN GW reconvergence) + F4 (RI config mid-churn) concurrent.

### Step sequence

| Step | Actor | Action | Timing |
|------|-------|--------|--------|
| D0 | Niobe | Confirm 6/6 baseline on both NVAs (Gate C state) | T−5 min |
| D1 | Niobe | Start BIRD RIB poll on nva2 every 30 s (`birdc show route count` + protocols); log timestamps | T=0 |
| D2 | Tank | Tear down nva2 IPsec: `sudo swanctl --terminate` | T=0 |
| D3 | Tank | **Concurrently** (< 30 s after D2): `az network vhub routing-intent delete -g routemap-test-rg --vhub hub-eu2 -n hub-eu2-ri --yes ; sleep 5 ; az network vhub routing-intent create …` | T=+30 s |
| D4 | Niobe | Continue BIRD RIB polls through reconvergence window | T+0 → T+10 min |
| D5 | Tank | Re-initiate nva2 tunnels: `sudo swanctl --initiate` after RI Succeeded | T = RI done |
| D6 | Niobe | Final RIB on nva2: 6/6 intact or missing? Persistent or resolved? Also capture nva1 (hub-eu1 control) | T+15 min |
| D7 | Niobe/Tank | If no repro: repeat D1–D6 with hub-eu1 / nva1 | T+20 min |

**Repro signal:** A summary absent from BIRD RIB AFTER vpngw0+vpngw1 re-establish AND RI Succeeded. Transient miss during churn = noise; **persistent miss after full reconvergence = customer bug reproduced.**

**Alternative churn trigger:** Disable a Megaport VXC BGP session for 60 s (if credentials available) while RI is being reprovisioned — exercises ER path; closer to a production "re-provisioning" event.

**Cost:** ~$0.10 incremental (30–45 min additional AzFW runtime; no new resources).

**Residual gaps after Gate D:**
- Cross-hub: hub-eu1 RI churn while hub-eu2 VPN connection churns (untested)
- VPN gateway-side restart as churn trigger (not NVA-side) (untested)
- RI enable on a fresh hub with an in-flight VPN connection change (untested)
