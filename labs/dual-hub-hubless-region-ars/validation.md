# Dual-Hub/Hubless-Region-ARS: PRE-DEPLOY VALIDATION SKELETON

## S1: Steady-State BGP Routing Verification

### Objective
Establish baseline: 10 BGP sessions UP, on-prem RIB prefers set-C via hub1 ([65515,65001] ASN path), effective routes functional on all endpoint NICs.

### Prerequisites
- All hubs (hub1, hub2) + Poland ARS deployed and peered (3 ARS × 3 = 9 sessions)
- All VPN GWs peered (3 VPN GWs × 1 = 3 sessions, total 10)
- BIRD running on NVA1 (65001) and NVA2 (65002)
- All connections established with correct PSKs

### S1 Test Actions
1. **Capture ARS BGP Sessions** (ars-hub1, ars-hub2, ars-poland)
   - Command: z network route-server peering list-learned-routes -g <rg> --routeserver-name ars-hub1 -n <peering-name>
   - Evidence file: outes_s1_ars-hub1_learned.json
   - Expected: 10 routes received (summarized by region + 0/0 from NVAs)
   - Assert: All BGP sessions in UP state; learned route count ≥ 10

2. **Verify On-Prem RIB Preference** (on-prem endpoint)
   - Command: ip route show table all (on vm-onprem-ep) or tysh -c "show ip bgp summary; show ip bgp all" (on NVA1)
   - Evidence file: outes_s1_onprem_rib.txt
   - Expected: Set-C prefixes (10.30.0.0/20, 10.30.128.0/20, 10.30.192.0/24) show next-hop via hub1 NVA1 (ASN [65515,65001])
   - Assert: On-prem prefers hub1 path; hub2 path [65515,65002,65002,65002] in FIB but lower preference

3. **Effective Routes on Endpoint NICs**
   - Command: z network nic show-effective-route-table -g <rg> -n vm-hub1-ep --query "value[].{Destination:destination, NextHop:nextHopIpAddress, Source:source}"
   - Evidence files: outes_s1_effective_hub1.json, outes_s1_effective_hub2.json, outes_s1_effective_c1.json, outes_s1_effective_onprem.json
   - Expected: Each endpoint NIC has routes to all subnets (on-prem, hub1, hub2, Poland); next-hop resolves to correct gateway/NVA
   - Assert: No black-hole routes; all overlays have next-hop ≠ null; set-C1 default route points to NVA1_IP

4. **NVA BIRD Status (NVA1 + NVA2)**
   - Command SSH: tysh -c "show ip bgp summary"
   - Evidence file: gp_s1_nva_summary.txt
   - Expected: NVA1 has 3 BGP peers UP (hub1 ARS, hub2 ARS, Poland ARS); NVA2 similar
   - Assert: Peer count = 3 for each NVA; state = Established

5. **Route-Map State** (Poland ARS inbound from NVA2 before S4 activation)
   - Command: z network route-server config show -g <rg> --routeserver-name ars-poland (if route-map field exists)
   - Evidence file: outes_s1_poland_ars_config.json
   - Expected: Route-map not yet applied (S4 activation step); AS-PATH differential 65515/65001 < 65515/65002/65002/65002
   - Assert: No inbound route-map active; AS-PATH lengths match BGP policy Δ2 (NVA2 ×2 prepend)

### S1 Assertions
- [ ] 10 BGP sessions in Established state
- [ ] On-prem RIB shows hub1 as preferred for set-C (AS-PATH [65515,65001] wins over [65515,65002×3])
- [ ] Effective routes on all 4 endpoint NICs include full routing domain (on-prem, hubs, Poland)
- [ ] BIRD on both NVAs reports Established peers = 3 each
- [ ] No unexplained AS-PATH lengths or prepends in S1 (Δ3 route-map not yet active)

### S1 Pass Criteria
All assertions ✓; convergence time baseline ≤ 60 seconds from ARS/VPN GW up.

---

## S2: Hub1 Outage Fault Injection

### Objective
Simulate hub1↔on-prem link failure via PSK mismatch + BIRD stop on NVA1. Verify traffic converges to hub2 (NVA2 path) within 30–180 seconds.

### Fault Injection Steps
1. **Wrong PSK on Hub1↔On-Prem Connections**
   - Command (on hub1 VPN GW): z network vpn-connection set --ids <vpngw-hub1-onprem-connection-id> --shared-key "WrongPSK123"
   - Command (on on-prem VPN GW): z network vpn-connection set --ids <vpngw-onprem-hub1-connection-id> --shared-key "WrongPSK123"
   - Evidence file: ault_s2_psk_changed.log
   - Expected: Connection state → Disconnected
   - Assert: BGP session hub1↔on-prem drops; hub2↔on-prem still UP

2. **Stop BIRD on NVA1**
   - Command SSH: sudo systemctl stop bird (on NVA1)
   - Evidence file: ault_s2_nva1_bird_stopped.log
   - Expected: NVA1 stops advertising routes; BGP sessions from NVA1 drop
   - Assert: Hub1 ARS loses BGP peer NVA1

3. **Record Convergence Timeline**
   - Timestamp: T0 (fault injection start)
   - Poll every 10 seconds: z network route-server peering list-learned-routes -g <rg> --routeserver-name ars-hub1 -n vpngw-onprem (watch for peer drop)
   - Poll every 10 seconds: on-prem NVA tysh -c "show ip bgp summary" (watch for hub2-only paths)
   - Timestamp: T1 (convergence complete when on-prem RIB only has hub2 paths for set-C)
   - Evidence file: convergence_s2_timeline.txt (record T0, T1, Δ = T1 - T0)
   - Expected: Δ ∈ [30, 180] seconds
   - Assert: Convergence ≤ 180s; on-prem RIB ASN-path now [65515,65002,65002,65002] for set-C

### S2 After Fault Route Captures
- **On-Prem RIB after convergence**: tysh -c "show ip bgp all" 
  - Evidence file: outes_s2_onprem_rib_hub2only.txt
  - Expected: Set-C learned via hub2 only; hub1 paths gone
  - Assert: No hub1 prefixes; all paths via NVA2 (ASN 65515/65002×3)

- **Hub1 ARS Learned Routes after NVA1 stop**: z network route-server peering list-learned-routes -g <rg> --routeserver-name ars-hub1 -n <nva1-peering>
  - Evidence file: outes_s2_hub1_ars_nva1_dropped.json
  - Expected: Route count from NVA1 → 0 (NVA1 peer down)
  - Assert: BGP session NVA1→hub1 ARS = Down

- **Hub2 ARS Learned Routes during outage**: z network route-server peering list-learned-routes -g <rg> --routeserver-name ars-hub2 -n <nva2-peering>
  - Evidence file: outes_s2_hub2_ars_nva2_up.json
  - Expected: Route count from NVA2 still high; on-prem now learns set-C via hub2
  - Assert: BGP session NVA2→hub2 ARS = Up; learned route count for on-prem prefixes intact

- **Effective Routes on Set-C1 Endpoint** (vm-c1-ep):
  - Command: z network nic show-effective-route-table -g <rg> -n vm-c1-ep --query "value[].{Destination:destination, NextHop:nextHopIpAddress}"
  - Evidence file: outes_s2_effective_c1_hub2_path.json
  - Expected: Default route (0/0) now points to NVA2_IP; on-prem return paths via Poland ARS→hub2 VPN GW
  - Assert: No black-hole; next-hop = NVA2_IP (not NVA1_IP)

### S2 Pass Criteria
- Convergence time Δ ∈ [30, 180] seconds
- On-prem RIB converged to hub2-only paths
- Hub1 ARS NVA1 peer = Down
- Hub2 ARS NVA2 peer = Up
- Set-C1 effective default route via NVA2_IP
- All endpoint NICs still have no black-holes

---

## S3: Hub1 Recovery

### Objective
Restore correct PSK, restart BIRD on NVA1, verify convergence back to S1 state within 30–90 seconds.

### Recovery Steps
1. **Restore Correct PSK on Hub1↔On-Prem Connections**
   - Command (on hub1 VPN GW): z network vpn-connection set --ids <vpngw-hub1-onprem-connection-id> --shared-key "<CORRECT_PSK>"
   - Command (on on-prem VPN GW): z network vpn-connection set --ids <vpngw-onprem-hub1-connection-id> --shared-key "<CORRECT_PSK>"
   - Evidence file: ecovery_s3_psk_restored.log
   - Expected: Connection state → Connected
   - Assert: BGP session hub1↔on-prem re-establishes

2. **Start BIRD on NVA1**
   - Command SSH: sudo systemctl start bird (on NVA1)
   - Evidence file: ecovery_s3_nva1_bird_started.log
   - Expected: BIRD re-advertises routes; BGP sessions re-establish
   - Assert: NVA1 BGP peers transition to Established

3. **Record Convergence Timeline (back to S1)**
   - Timestamp: T0 (recovery start)
   - Poll every 10 seconds: on-prem NVA tysh -c "show ip route bgp" (watch for hub1 re-emergence)
   - Timestamp: T1 (convergence complete when on-prem RIB shows hub1 as preferred for set-C)
   - Evidence file: convergence_s3_timeline.txt (record T0, T1, Δ = T1 - T0)
   - Expected: Δ ∈ [30, 90] seconds
   - Assert: Convergence ≤ 90s; on-prem RIB ASN-path now [65515,65001] for set-C (preferred)

### S3 After Recovery Route Captures
- **On-Prem RIB after convergence** (back to S1):
  - Command: tysh -c "show ip bgp all"
  - Evidence file: outes_s3_onprem_rib_s1_match.txt
  - Expected: Set-C learned via hub1 preferred [65515,65001]; hub2 alternative [65515,65002×3] present
  - Assert: Matches S1 state; hub1 path preferred (lower AS-PATH)

- **Hub1 ARS Learned Routes after NVA1 restart**:
  - Command: z network route-server peering list-learned-routes -g <rg> --routeserver-name ars-hub1 -n <nva1-peering>
  - Evidence file: outes_s3_hub1_ars_nva1_up.json
  - Expected: Route count from NVA1 restored
  - Assert: BGP session NVA1→hub1 ARS = Up; learned route count matches S1

- **Effective Routes on Set-C1 Endpoint**:
  - Command: z network nic show-effective-route-table -g <rg> -n vm-c1-ep --query "value[].{Destination:destination, NextHop:nextHopIpAddress}"
  - Evidence file: outes_s3_effective_c1_nva1_path.json
  - Expected: Default route (0/0) reverted to NVA1_IP
  - Assert: Matches S1 state; next-hop = NVA1_IP

### S3 Pass Criteria
- Convergence time Δ ∈ [30, 90] seconds
- On-prem RIB converged back to hub1-preferred paths (matches S1)
- Hub1 ARS NVA1 peer = Up
- Set-C1 effective default route via NVA1_IP
- All routing state matches S1 baseline

---

## S4: Route-Map Preview (Inbound Policy on Poland ARS)

### Objective
Demonstrate inbound route-map on Poland ARS↔NVA2 peering. Verify AS-PATH differential is maintained and NVA1 remains best-path for 0/0 despite route-map activation.

### Prerequisites
- S1 or S3 state (steady-state with hub1 active, on-prem preferring hub1 for set-C)
- Route-map public preview feature enabled on subscription (if applicable; requires Phase-4 approval per cost guardrail note)

### S4 Test Actions
1. **Apply Inbound Route-Map on Poland ARS↔NVA2**
   - Conceptual: z network route-server config set --ids <ars-poland-id> --inbound-route-map-id <route-map-id> (syntax TBD; feature in public preview)
   - Map rule: Prepend NVA2-originated 0/0 with NVA2 ASN ×2 (Δ3 policy)
   - Evidence file: config_s4_route_map_applied.log
   - Expected: Route-map active; inbound advertisements from NVA2 to Poland ARS now carry extra prepends
   - Assert: No BGP session disruption; NVA2 peer remains Established

2. **Verify AS-PATH Differential (0/0 comparison)**
   - Command: on-prem NVA tysh -c "show ip bgp 0/0/0" or show ip route bgp
   - Evidence file: gp_s4_onprem_0route_aspath.txt
   - Expected: 0/0 via NVA1 still has shorter AS-PATH [65515,65001] than 0/0 via NVA2 [65515,65002×2] (post-map prepend = 4 hops)
   - Assert: NVA1 remains preferred for 0/0; NVA2 is backup

3. **Effective Routes on Set-C1 Endpoint**:
   - Command: z network nic show-effective-route-table -g <rg> -n vm-c1-ep --query "value[].{Destination:destination, NextHop:nextHopIpAddress}"
   - Evidence file: outes_s4_effective_c1_nva1_preferred.json
   - Expected: Default route (0/0) still points to NVA1_IP despite route-map on NVA2 path
   - Assert: NVA1 remains primary; routing unchanged from S1/S3

### S4 Route-Map Before/After Evidence
- **Before Route-Map**: outes_s1_onprem_rib.txt (from S1) or re-capture if S4 starts from S3
- **After Route-Map**: outes_s4_onprem_rib_postmap.txt
  - Diff focus: Compare 0/0 AS-PATH lengths; no other changes expected
  - Expected: [65515,65001] unchanged; [65515,65002×2] new prepend ×2 per NVA2 advertisement
  - Assert: Δ3 prepend policy successfully applied by route-map

### S4 Pass Criteria
- Route-map applied without BGP session disruption
- On-prem NVA's AS-PATH for 0/0 via NVA1 remains shorter than via NVA2
- Set-C1 effective default route still via NVA1_IP
- NVA1 remains best-path for 0/0
- Route-map feature flag functional (public preview validation)

---

## S5: Prefix-Only Spoke Scale (No VM Validation)

### Objective
Prove that a spoke (10.32.0.0/24) with no VM can still advertise prefixes to on-prem via both hubs. Demonstrates ARS scales per-region, not per-spoke.

### Prerequisites
- S1 or S3 steady-state active
- Spoke VNet 10.32.0.0/24 created but with no VMs deployed
- Spoke peered to Poland ARS (default BGP eBGP)

### S5 Test Actions
1. **Verify Spoke VNet BGP Advertisement**
   - Command: z network route-server peering show -g <rg> --routeserver-name ars-poland -n <spoke-peering-name> --query "{bgpState:bgp.bgpState, learnedRoutes:routeConfig[0].inboundRouteMap}"
   - Evidence file: config_s5_spoke_peering_status.json
   - Expected: BGP state = Established; spoke VNet CIDR (10.32.0.0/24) advertised by Poland ARS
   - Assert: Peering up; no conditional on VM existence

2. **On-Prem RIB Receives Spoke Prefix via Both Hubs**
   - Command: on-prem NVA tysh -c "show ip route bgp 10.32.0.0/24"
   - Evidence file: outes_s5_onprem_rib_spoke_prefix.txt
   - Expected: 10.32.0.0/24 learned from hub1 (via NVA1 + hub1 ARS) and hub2 (via NVA2 + hub2 ARS)
   - Assert: Prefix reachable on-prem; both hub paths present

3. **Poland ARS Learned Routes**:
   - Command: z network route-server peering list-learned-routes -g <rg> --routeserver-name ars-poland -n <spoke-peering-name>
   - Evidence file: outes_s5_poland_ars_learned_spoke.json
   - Expected: 10.32.0.0/24 in learned routes from spoke peering
   - Assert: Spoke prefix visible in ARS despite no VM in spoke

4. **Spoke Effective Routes** (proof-of-concept):
   - Command: On a management VM or test endpoint, query spoke RT: z network route-table show -g <rg> -n <spoke-rt-name> --query "routes[]"
   - Evidence file: outes_s5_effective_spoke_rt.json
   - Expected: Spoke RT has routes to on-prem and hub subnets injected by ARS
   - Assert: Spoke can route back to on-prem despite no local VM traffic

### S5 Pass Criteria
- Spoke VNet 10.32.0.0/24 prefix reaches on-prem RIB via both hubs
- Poland ARS advertises spoke peering up; learned routes include 10.32.0.0/24
- Spoke effective routes include on-prem destinations
- **Scale implication verified**: ARS operates per-region + per-peering, not per-spoke-VM; spoke without VM still participates in routing domain

---

## Evidence Inventory & Storage

All evidence files (JSON, TXT, logs) should be stored in: labs/dual-hub-hubless-region-ars/evidence/

### File Naming Convention
- outes_<scenario>_<resource>_<aspect>.json (e.g., outes_s1_ars-hub1_learned.json)
- gp_<scenario>_<resource>_<aspect>.txt (e.g., gp_s1_nva_summary.txt)
- convergence_<scenario>_<aspect>.txt (timing logs)
- config_<scenario>_<aspect>.log (configuration change logs)
- ault_<scenario>_<aspect>.log (fault injection logs)
- ecovery_<scenario>_<aspect>.log (recovery logs)

### Route/BGP Capture Layer Checklist
- [ ] S1: 3 ARS (hub1, hub2, poland) + 3 VPN GWs (hub1, hub2, onprem) + 2 NVAs (nva1, nva2) + 4 endpoints (hub1-ep, hub2-ep, c1-ep, onprem-ep)
- [ ] S2: Same as S1 + before/during/after fault injection
- [ ] S3: Same as S1 + before/during/after recovery
- [ ] S4: Same as S1 + before/after route-map activation
- [ ] S5: Spoke prefix reachability proof (on-prem RIB, Poland ARS, spoke RT)

---

## Post-Deployment Validation Notes
- Convergence timing (S2/S3) may vary based on BGP timers; 30–180s and 30–90s are expected ranges
- Route-map feature (S4) requires Phase-4 cost escalation approval; validation skeleton can proceed, but deployment gated by Trinity/Tank decision
- PSK swap (S2) is non-destructive; infrastructure remains intact after fault injection
- BIRD stop/start (S2/S3) does not require NVA reboot; systemctl sufficient
- All route captures should include timestamps for correlation with convergence timeline
