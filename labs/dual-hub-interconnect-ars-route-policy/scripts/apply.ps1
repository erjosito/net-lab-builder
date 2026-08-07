#Requires -Version 7.0
<#
.SYNOPSIS
    TP-HH delta-only apply skeleton — Dual-Hub Interconnect and Route Server Route-Map Policy.

.DESCRIPTION
    THIS SCRIPT DOES NOT DEPLOY ANYTHING. It is a gated, commented skeleton written during the
    TP-HH extraction task (Tank, 2026-08-05) per Morpheus's approved extraction contract
    (.squad/decisions/inbox/morpheus-us10-us11-extraction.md §6, §8 row 21).

    All live resources exercised by this script are OWNED BY, and remain the responsibility of,
    labs/dual-hub-hubless-region-ars (resource group rg-dual-hub-hubless-region-ars-lab3d001,
    deployed 2026-08-03, certified 2026-08-04). This script only ever adds ADDITIVE, REVERSIBLE
    deltas on top of that bed -- it never deletes, recreates, or redeploys the shared bed itself.

    Every Azure CLI / az rest call below is COMMENTED OUT. This script refuses to execute any
    Azure command until:
      (a) -Scenario is supplied and matches an implemented case, AND
      (b) -ResourceGroup, -SubscriptionId are supplied and match the expected shared bed values
          (safety check against accidental cross-subscription / cross-RG execution), AND
      (c) -ApprovalConfirmed is passed explicitly (this is a second, independent, explicit gate,
          separate from the built-in ShouldProcess -Confirm/-WhatIf), AND
      (d) the operator has read design.md §7 (maintenance-window / BGP-reset protocol) and
          manifest.md §Approval gate for the scenario being run.

    Scenarios covered (see manifest.md for full pass/fail):
      U0   -- start vm-nva1 + vm-nva2 only (power state); PREREQUISITE for every other scenario
      T1   -- vnet-hub1 <-> vnet-hub2 global VNet peering (both directions)          [unit U1]
      U15  -- remove retired Poland BIRD state from BOTH NVAs (TANK-001)             [unit U1.5]
      T2a  -- inert route-map association on ars-hub1/peer-nva1 ONLY (hub1 first)    [unit U2]
      U3a  -- inject the temporary RFC 5737 TEST-NET-2 doc prefix on vm-nva1 only    [unit U3a]
      T2b  -- real AS-Path Add modification on the T2a association (only after U3a)  [unit U3b]
      T3   -- NVA-to-NVA eBGP + conditional encapsulation (CONDITIONAL -- may never run) [unit U5]
      T5   -- VPN gateway connection route-map attachment (OPTIONAL -- separate approval) [unit U4]

    T4 has no apply step of its own -- it reuses T2b's association and a BIRD-side filter change
    that is applied and reverted via version control (see design.md §5, §T4).

    Phase-4 corrections (Trinity, 2026-08-05 -- see design.md §8a):
      * The route-map association write target is the CONNECTION
        (virtualHubs/<ars>/bgpConnections/<peer> -> properties.routingConfiguration.inboundRouteMap),
        NOT the route map. routeMaps/*.associatedInboundConnections is a READ-ONLY composite.
      * The verb is PUT, not PATCH -- this child resource type defines no PATCH operation (405).
        The PUT body must carry peerAsn + peerIp + the full routingConfiguration or the peering is
        recreated with defaults.
      * T2b targets routeMaps under virtualHubs/<ars>/routeMaps/<name>, NOT virtualHubRouteTables.
      * T2a/T2b use a DEDICATED TEMPORARY map rm-hub1-tmp-assoc. rm-hub1-activate is NOT reused:
        it is not empty (rule-activate-synthetic) and its tier-activation provenance is preserved.
      * All five lab VMs are deallocated as of 2026-08-05, so U0 must run first or there is no
        BGP state to observe at all.

    Phase-4 corrections (Trinity, 2026-08-06 -- post-U0/U1, finding TANK-001):
      * U0 and U1 have EXECUTED and PASSED. vm-nva1/vm-nva2 are running and both hub<->hub
        peerings exist. The U0/U1 blocks below are retained as the executed record.
      * NEW UNIT U1.5 (-Scenario U15): both NVAs still carry retired Poland BIRD state and
        re-originate a stale 10.30.0.0/27 into their local ARS. U1.5 removes it. It is now a
        PREREQUISITE for U2 and U3. Authoritative configs live in ../nva-config/.
      * T2b's target prefix 10.10.0.64/27 is DEAD. Azure Route Server silently rejects a route
        matching its own RouteServerSubnet, so it never appears in ars-hub1's learned set and a
        map keyed on it could never match. T2b now targets 198.51.100.0/24, injected by U3a.
      * The U2 inert map now matches 203.0.113.0/24 (TEST-NET-3), not 192.0.2.0/24 -- the latter
        is already rm-hub1-activate's match prefix and would make evidence ambiguous.
      * The PUT body for bgpConnections MUST preserve properties.routingConfiguration.vnetRoutes
        INCLUDING staticRoutesConfig. PUT replaces properties wholesale; there is no PATCH.

.NOTES
    Windows PowerShell / az rest body-file finding (Tank, 2026-08-05): "az rest --body
    '{\"json\":\"inline\"}'" fails with UnsupportedMediaType on Windows PowerShell. Every body in
    this script MUST be written to a file under scripts/bodies/ first, then referenced as
    "az rest --body `"@<full-path-to-file>.json`"". Never pass an inline JSON string.
#>

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('U0', 'T1', 'U15', 'T2a', 'U3a', 'T2b', 'T3', 'T5')]
    [string]$Scenario,

    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,          # Expected: rg-dual-hub-hubless-region-ars-lab3d001 (shared bed)

    [Parameter(Mandatory = $true)]
    [string]$SubscriptionId,         # Must match the subscription the shared bed lives in

    [switch]$ApprovalConfirmed       # Explicit second gate -- separate from the built-in -Confirm/
                                      # -WhatIf that [CmdletBinding(SupportsShouldProcess)] already
                                      # provides. Must be passed explicitly; there is no default.
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------------------------
# Step 0 — Rehydrate HKCU env vars (Windows only; no-op on Linux/macOS).
# Pattern from Tank's charter (discovered lab #1 cleanup, 2026-05-29): PowerShell child processes
# do not inherit HKCU registry values. Uncomment and extend only if this script grows to depend
# on stored credentials (it should not need any for peering / route-map association).
# ---------------------------------------------------------------------------------------------
# $varsToRehydrate = @()
# foreach ($varName in $varsToRehydrate) {
#     $val = [System.Environment]::GetEnvironmentVariable($varName, 'User')
#     if ($val) { [System.Environment]::SetEnvironmentVariable($varName, $val, 'Process') }
# }

# ---------------------------------------------------------------------------------------------
# Gate 1 — hard refuse unless every required identifier is a real, non-placeholder value.
# ---------------------------------------------------------------------------------------------
$expectedRg = 'rg-dual-hub-hubless-region-ars-lab3d001'
if ($ResourceGroup -ne $expectedRg) {
    throw "REFUSED: -ResourceGroup '$ResourceGroup' does not match the expected shared bed RG " + `
          "'$expectedRg' (owned by labs/dual-hub-hubless-region-ars). This script will not run " + `
          "against any other resource group. If the shared bed's RG name has genuinely changed, " + `
          "update `$expectedRg here only after confirming with the source lab's manifest.md."
}

if ([string]::IsNullOrWhiteSpace($SubscriptionId) -or $SubscriptionId -match '<.*>') {
    throw "REFUSED: -SubscriptionId is missing or still a placeholder. Supply the real " + `
          "subscription GUID for the shared bed. This script never hardcodes a subscription ID."
}

if (-not $ApprovalConfirmed) {
    throw "REFUSED: pass -ApprovalConfirmed explicitly to acknowledge you have read design.md §7 " + `
          "(maintenance-window / BGP-reset protocol) and manifest.md §Approval gate for scenario " + `
          "'$Scenario', and that Jose has approved this scenario's execution."
}

Write-Host "Gates passed for scenario '$Scenario'. NO AZURE COMMAND HAS BEEN EXECUTED." -ForegroundColor Yellow
Write-Host "This is a skeleton. Uncomment the scenario block below only after review." -ForegroundColor Yellow

# ---------------------------------------------------------------------------------------------
# Fresh-baseline reminder (validation.md): capture show-output/new/<scenario-dir>/00-pre-*.json
# BEFORE uncommenting any block below. The inherited show-output/inherited/ captures are context
# only, not the diff reference.
# ---------------------------------------------------------------------------------------------

switch ($Scenario) {

    'U0' {
        # --- U0: start vm-nva1 + vm-nva2 ONLY (power state; PREREQUISITE) -----------------------
        # Approval unit U0. Cost delta: +$0.024/hr (+$0.58/day) at 2026-08-05 retail
        # (B2ts_v2 Linux: swedencentral $0.0108/hr, switzerlandnorth $0.0132/hr).
        # NOT routing-neutral: BIRD re-originates 0.0.0.0/0 and the RouteServerSubnet /27 into both
        # Route Servers, hub gateways resume advertising to on-prem, and the spoke 0/0 UDRs stop
        # black-holing. vm-hub1-ep / vm-hub2-ep / vm-onprem-ep MUST stay deallocated.
        # Rollback owner: Tank (scripts/rollback.ps1 -Scenario U0).
        #
        # az vm start --resource-group $ResourceGroup --name vm-nva1
        # az vm start --resource-group $ResourceGroup --name vm-nva2
        #
        # Wait 10 minutes, then capture show-output/new/u0-vm-start/ per validation.md §U0.
        # The gating capture for U1 is BIRD route-refresh capability, which has NEVER been taken:
        #   az vm run-command invoke -g $ResourceGroup -n vm-nva1 --command-id RunShellScript `
        #     --scripts "birdc show protocols all"
        # Expect ars_poland_0/1 to sit in Connect/Active permanently (peers 10.30.0.4/.5 deleted) --
        # that is EXPECTED, not a failure. No Poland prefix may reappear anywhere.
        Write-Host "U0 block is commented out. Nothing executed." -ForegroundColor DarkYellow
    }

    'T1' {
        # --- T1 (unit U1): vnet-hub1 <-> vnet-hub2 global VNet peering, both directions ---------
        # PREREQUISITE: U0 executed and route-refresh capability captured.
        # Exactly two objects. Cost: $0/hr; inter-region transfer $0.04/GB egress + $0.04/GB
        # ingress => ~$0.00 for an ICMP probe. Rollback owner: Tank (rollback.ps1 -Scenario T1).
        #
        # az network vnet peering create `
        #   --name peer-hub1-to-hub2 --resource-group $ResourceGroup --vnet-name vnet-hub1 `
        #   --remote-vnet vnet-hub2 --allow-vnet-access true --allow-forwarded-traffic true `
        #   --allow-gateway-transit false --use-remote-gateways false
        #
        # az network vnet peering create `
        #   --name peer-hub2-to-hub1 --resource-group $ResourceGroup --vnet-name vnet-hub2 `
        #   --remote-vnet vnet-hub1 --allow-vnet-access true --allow-forwarded-traffic true `
        #   --allow-gateway-transit false --use-remote-gateways false
        #
        # Headline PASS evidence is a NON-effect: spoke, ARS-learned and gateway-learned prefixes
        # must NOT cross the peering. Only 10.10.0.0/16 <-> 10.20.0.0/16 reachability is in scope.
        Write-Host "T1 block is commented out. Nothing executed." -ForegroundColor DarkYellow
    }

    'U15' {
        # --- U1.5: remove RETIRED POLAND BIRD STATE from BOTH NVAs (finding TANK-001) -----------
        # PREREQUISITE FOR U2 AND U3. Not approved. Cost delta: $0 (no Azure resource changes;
        # az vm run-command invocations are free). Blast radius: the BIRD control plane on each
        # NVA and, through it, exactly one prefix in each hub's ARS learned set.
        #
        # EXACT REMOVALS -- taken from the captured config, not from guessed names. Full table,
        # rationale and per-layer proof plan: ../nva-config/README.md (section U1.5).
        #   vm-nva1: (1) `route 10.30.0.0/27 via 10.10.1.1;` from protocol static
        #            (2) protocol bgp ars_poland_0   (neighbor 10.30.0.4, multihop 4)
        #            (3) protocol bgp ars_poland_1   (neighbor 10.30.0.5, multihop 4)
        #            (4) filter export_to_poland_ars (unreferenced after 2+3)
        #   vm-nva2: (1) `route 10.30.0.0/27 via 10.20.1.1;` from protocol static
        #            (2) protocol bgp ars_poland_0   (3) protocol bgp ars_poland_1
        #            (4) filter export_to_poland_ars
        #            (5) the dead set-C clause inside filter export_to_hub2_ars:
        #                `if net ~ [ 10.31.0.0/24, 10.32.0.0/24 ] then { prepend 65002 x2 }`
        # NEVER REMOVED: 0.0.0.0/0 static, the local RouteServerSubnet static, bgp_path.delete(65515),
        #                device/direct/kernel, ars_hub1_0/1, ars_hub2_0/1.
        #
        # ONE NVA AT A TIME. vm-nva1 first, full L1-L4 verification, only then vm-nva2.
        #
        # Step 0 -- baseline (read-only), into show-output/new/u15-bird-cleanup/00-pre-*:
        #   az network routeserver peering list-learned-routes -g $ResourceGroup --routeserver ars-hub1 -n peer-nva1
        #   az network routeserver peering list-advertised-routes -g $ResourceGroup --routeserver ars-hub1 -n peer-nva1
        #   az network nic show-effective-route-table -g $ResourceGroup -n <nva1-nic>
        #   az network vnet-gateway list-advertised-routes -g $ResourceGroup -n vpngw-hub1 --peer 10.40.0.4
        #   az network vnet-gateway list-learned-routes   -g $ResourceGroup -n vpngw-onprem
        #   (+ mirrored for hub2/nva2), and birdc show protocols all / show route all on both NVAs.
        #
        # Step 1 -- BACKUP on the NVA (run-command RunShellScript):
        #   STAMP=$(date -u +%Y%m%dT%H%M%SZ)
        #   sudo cp -p /etc/bird/bird.conf /etc/bird/bird.conf.pre-u15.$STAMP
        #   sudo sha256sum /etc/bird/bird.conf.pre-u15.$STAMP /etc/bird/bird.conf
        #
        # Step 2 -- STAGE the new config (never write over the live file first). Contents are
        #           ../nva-config/bird-nva1.u15-target.conf verbatim:
        #   sudo install -m 0640 -o root -g bird /dev/stdin /etc/bird/bird.conf.u15 <<'EOF' ... EOF
        #
        # Step 3 -- VALIDATE SYNTAX, BLOCKING. Both checks must pass before anything is applied:
        #   sudo bird -p -c /etc/bird/bird.conf.u15
        #   sudo birdc configure check "/etc/bird/bird.conf.u15"
        #   On any failure: rm the staging file, abort. The live config was never touched.
        #
        # Step 4 -- APPLY WITH A GRACEFUL RELOAD. `systemctl restart bird` is FORBIDDEN here: a
        #           restart tears down ars_hub*_0/1 and black-holes both spokes' 0/0 for the
        #           reset duration. `birdc configure` reconfigures unchanged protocols in place,
        #           so the established sessions do not flap.
        #   sudo cp -p /etc/bird/bird.conf.u15 /etc/bird/bird.conf
        #   sudo birdc configure
        #
        # Step 5 -- PROVE IT, at 30/60/120/180 s. Expected delta is ONE prefix:
        #   NVA:      10.30.0.0/27 absent from `birdc show route`; ars_poland_* absent from
        #             `birdc show protocols`; ars_hub*_0/1 Established with UNCHANGED Since.
        #   ARS:      10.30.0.0/27 gone from BOTH RouteServiceRole_IN_0 and _IN_1; 0.0.0.0/0 and
        #             the 10.40.0.0/16 boomerang unchanged; advertised set byte-identical.
        #   Gateway:  vpngw-hub1/hub2 peer status + advertised-to-onprem byte-identical.
        #   On-prem:  vpngw-onprem learned routes byte-identical.
        #   NIC:      the 10.30.0.0/27 VirtualNetworkGateway entry gone from the NVA NIC.
        #   Ping:     vm-nva1 <-> vm-nva2 continuous ICMP, 0% loss across the reload.
        #
        # ROLLBACK TRIGGERS and the exact rollback: ../nva-config/README.md section 6, and
        # rollback.ps1 -Scenario U15. Fast path `sudo birdc configure undo`; durable path is the
        # backup restore. Under 2 minutes per NVA.
        Write-Host "U15 block is commented out. Nothing executed." -ForegroundColor DarkYellow
    }

    'T2a' {
        # --- T2a (unit U2): inert route-map association on ars-hub1/peer-nva1 ONLY --------------
        # HUB1 ONLY. The ars-hub2 mirror (T2a') is a SEPARATE approval -- this halves the blast
        # radius of the first-ever association in this lab family.
        # PREREQUISITE: U1.5 executed and a settled post-U1.5 baseline captured. U2's headline
        # PASS criterion is "the learned set did not change"; running it before U1.5 would mean
        # comparing against a set that is about to lose a prefix for an unrelated reason.
        # MUST NOT share a maintenance window with T1/U1 or with U15.
        # Rollback owner: Tank (scripts/rollback.ps1 -Scenario T2a).
        #
        # Step 0 -- MANDATORY read-only capture. The PUT body is DERIVED FROM THIS, not authored:
        # az rest --method get `
        #   --uri "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Network/virtualHubs/ars-hub1/bgpConnections/peer-nva1?api-version=2024-10-01" `
        #   > show-output/new/t2-routemap-assoc/00-pre-peer-nva1-GET.json
        #   Live shape 2026-08-06: properties = { peerAsn: 65001, peerIp: "10.10.1.4",
        #     provisioningState: "Succeeded", routingConfiguration: { vnetRoutes: {
        #       staticRoutes: [], staticRoutesConfig: { propagateStaticRoutes: true,
        #       vnetLocalRouteOverrideCriteria: "Contains" } } } }
        #   BODY PRESERVATION RULE: take response.properties EXACTLY, delete ONLY
        #   provisioningState, ADD routingConfiguration.inboundRouteMap.id, send
        #   {"properties": <that object>}. Do not send id/name/type/etag in the body. PUT
        #   REPLACES properties wholesale -- omitting vnetRoutes (or just staticRoutesConfig)
        #   silently resets propagateStaticRoutes / vnetLocalRouteOverrideCriteria. Pass the
        #   GET's etag as If-Match so a concurrent change fails the write instead of clobbering it.
        #
        # Step 1 -- create the DEDICATED TEMPORARY map (rm-hub1-activate is deliberately NOT reused).
        # Its single rule matches RFC 5737 TEST-NET-3 203.0.113.0/24 under Equals -- verified
        # absent from every live surface on 2026-08-06, so the association is INERT BY
        # CONSTRUCTION. (192.0.2.0/24 is NOT used: it is rm-hub1-activate's own match prefix and
        # would make any observed or absent effect ambiguous between the two maps.)
        # az rest --method put `
        #   --uri "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Network/virtualHubs/ars-hub1/routeMaps/rm-hub1-tmp-assoc?api-version=2024-10-01" `
        #   --body "@$PSScriptRoot/bodies/routemap-tmp-assoc-hub1.json"
        #
        # Step 2 -- associate it INBOUND on the bgpConnection. VERB IS PUT, NOT PATCH (this child
        # resource type defines no PATCH operation; a PATCH is expected to return HTTP 405).
        # az rest --method put --headers "If-Match=<etag-from-step-0>" `
        #   --uri "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Network/virtualHubs/ars-hub1/bgpConnections/peer-nva1?api-version=2024-10-01" `
        #   --body "@$PSScriptRoot/bodies/routemap-assoc-inert-body-hub1.json"
        #
        # PASS = provisioningState Succeeded AND ars-hub1 learned/advertised sets byte-identical
        # to the post-U1.5 baseline AND all four VPN connections still Connected. A BGP session
        # reset is a PASS-WITH-NOTE only if its duration is measured and recorded, never assumed.
        # Route maps for Azure Route Server are a PREVIEW feature -- record that in the result.
        #
        # DO NOT write to routeMaps/*.associatedInboundConnections -- it is a READ-ONLY composite
        # (live GET returns []). Documented fallback surface if the PUT is rejected: portal ->
        # ARS -> route maps -> "Apply route maps". Record any rejection verbatim (closes gate G4).
        #
        # The ars-hub2 mirror body (bodies/routemap-assoc-inert-body-hub2.json, peerAsn 65002,
        # peerIp 10.20.1.4) is retained for T2a' but is NOT part of unit U2.
        Write-Host "T2a block is commented out. Nothing executed." -ForegroundColor DarkYellow
    }

    'U3a' {
        # --- U3a: inject the TEMPORARY documentation test prefix on vm-nva1 ONLY ----------------
        # Runs only after U1.5 and U2 have both PASSED. Cost delta: $0.
        # WHY: after U1.5, ars-hub1 learns only 0.0.0.0/0 (forbidden target) and 10.40.0.0/16
        # (forbidden -- on-prem prefix, and present on RouteServiceRole_IN_1 only, so any diff is
        # instance-asymmetric). The old target 10.10.0.64/27 is DEAD: U0 proved Azure Route Server
        # silently rejects a route matching its own RouteServerSubnet, so it never enters the
        # learned set and an inbound map keyed on it could never match. U3 therefore has to
        # create its own harmless target.
        #
        # Config block: ../nva-config/bird-nva1.u3a-doctest.snippet.conf, appended verbatim to
        # ../nva-config/bird-nva1.u15-target.conf:
        #     protocol static u3_doc_test { ipv4; route 198.51.100.0/24 blackhole; }
        # 198.51.100.0/24 = RFC 5737 TEST-NET-2; verified absent from every live surface
        # 2026-08-06; deliberately distinct from 192.0.2.0/24 (rm-hub1-activate) and
        # 203.0.113.0/24 (U2's inert rule).
        #
        # Same mechanics as U15: backup -> stage -> `bird -p -c` + `birdc configure check` ->
        # `birdc configure`. NEVER `systemctl restart bird`. Adding a new protocol does not
        # restart the existing ones, so ars_hub1_0/1 do not flap.
        #
        # PASS: ars-hub1 learns 198.51.100.0/24 with asPath "65001", nextHop 10.10.1.4, on BOTH
        # instances; every other prefix byte-identical to the post-U2 baseline; the prefix does
        # NOT appear at vpngw-hub1, vpngw-hub2 or vpngw-onprem (re-prove containment, do not
        # assume it from the 10.30.0.0/27 precedent); all four VPN connections still Connected.
        # ACCEPTED SIDE EFFECT, stated in the approval: the prefix is programmed into vnet-hub1
        # NIC effective routes and probably into vnet-spoke-a's, which cannot be read this window
        # (vm-hub1-ep stays deallocated) -- record as unverified-by-design, not as a claim.
        #
        # ROLLBACK: delete the u3_doc_test block, `birdc configure`, confirm the prefix is
        # withdrawn from both ars-hub1 instances. Or `birdc configure undo` if it is the last
        # change. Under 2 minutes.
        Write-Host "U3a block is commented out. Nothing executed." -ForegroundColor DarkYellow
    }

    'T2b' {
        # --- T2b (unit U3b): real AS-Path Add modification (only after U2 AND U3a PASS) ---------
        # TARGET PREFIX CHANGED 2026-08-06 and may NOT be changed back at execution time:
        #   198.51.100.0/24 -- the RFC 5737 TEST-NET-2 documentation prefix injected by U3a.
        # THE OLD TARGET 10.10.0.64/27 IS INVALID. U0 proved Azure Route Server silently rejects a
        # route matching its own RouteServerSubnet: 10.10.0.64/27 is in vm-nva1's bird.conf and is
        # exported like every other static, but it never appears in ars-hub1's learned-routes set.
        # An inbound map keyed on it could never match, and T2b would have proven nothing while
        # appearing to run. Evidence: show-output/new/u0-u1/post-u0/04-post-ars-hub1-peer-nva1-learned.json.
        # Also forbidden: 0.0.0.0/0 (spoke UDR semantics + DEF-001), 10.10.0.0/16 and 10.11.0.0/24
        # (route maps cannot modify the VNet address space ARS advertises), 10.40.0.0/16 (on-prem
        # prefix, and present on RouteServiceRole_IN_1 only), 10.30.0.0/27 (removed by U1.5 --
        # never resurrect it as a test target).
        # Attribute: Add asPath ["64496","64496"]. 64496 is the RFC 5398 2-byte documentation ASN;
        # it is NOT private (64512-65534) and NOT on Azure's reserved-for-prepending list
        # (8074, 8075, 12076, 65515, 65517-65520). Route maps support 2-byte ASNs only.
        # Rollback owner: Tank (scripts/rollback.ps1 -Scenario T2b -- reverts to the U2 inert state).
        #
        # az rest --method put `
        #   --uri "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Network/virtualHubs/ars-hub1/routeMaps/rm-hub1-tmp-assoc?api-version=2024-10-01" `
        #   --body "@$PSScriptRoot/bodies/routemap-aspath-add-body-hub1.json"
        #
        # Expected evidence: AS-PATH on 198.51.100.0/24 goes from "65001" to "64496-64496-65001"
        # at BOTH ars-hub1 instances; every other prefix byte-identical to the post-U3a baseline.
        # EVIDENCE-FIDELITY RISK, declared before execution: it is not established that
        # `list-learned-routes` reports post-inbound-map attributes rather than as-received ones.
        # If neither the CLI nor the portal Route Map dashboard shows the change, the result is
        # INCONCLUSIVE, not FAIL -- U2 still stands as the association proof. Do not retry with a
        # production prefix to force a visible result.
        Write-Host "T2b block is commented out. Nothing executed." -ForegroundColor DarkYellow
    }

    'T3' {
        # --- T3 (unit U5): NVA-to-NVA eBGP + conditional encapsulation (CONDITIONAL) -------------
        # NOT PREAPPROVED AND NOT REQUESTED. Fires only if the bow-tie failover contract requires
        # (1) automatic propagation of remote-region prefixes, (2) automatic withdrawal within the
        # BGP hold window, or (3) preference surviving the regional boundary.
        # Hard prerequisites discovered 2026-08-05, stated so they are never found mid-window:
        #   * NSG MUTATION on BOTH nsg-nva-hub1 and nsg-nva-hub2 -- today each allows TCP/179 only
        #     from its own hub /16 (p100) with deny-all at p4000, so 10.10.1.4 <-> 10.20.1.4 eBGP
        #     would be DENIED. (ICMP is already allowed from 10.0.0.0/8, so the T1 probe is fine.)
        #   * BIRD mutation on both NVAs, with the deny-by-default prefix policy in place BEFORE
        #     the session is established (design.md §6). BIRD configs are hand-edited on the OS
        #     disks and are NOT in version control -- capture them in U0 first.
        # Rollback owner: Tank. No apply block is written, deliberately.
        Write-Host "T3 is conditional and has no implemented apply block yet." -ForegroundColor DarkYellow
    }

    'T5' {
        # --- T5 (unit U4): VPN gateway connection route-map attachment (OPTIONAL) ----------------
        # STEP 1 IS READ-ONLY and is the only part currently proposed: enumerate the portal
        # ARS -> route maps -> "Apply route maps" blade verbatim and record
        #   Get-Module -ListAvailable Az.Network
        # into show-output/new/t5-gwconn-assoc/01-api-semantics-probe.md.
        #
        # STEP 2 (the write) may be UNTESTABLE: the live model exposes no ARS<->VPN-gateway
        # connection object. ars-hub1 has no connection children beyond bgpConnections/peer-nva1
        # and routeMaps/*; the four Microsoft.Network/connections resources use the
        # VirtualNetworkGatewayConnection schema, which has no inboundRouteMap/outboundRouteMap
        # member (live routingConfiguration is {}). If Step 1 finds nothing eligible, record
        # "RM-C/RM-D unverifiable in this bed" and close gate G4 on T2a's result alone.
        #
        # Step 2, if it ever runs, requires separate explicit approval on top of T2a passing --
        # blast radius is the shared vpngw-hub* <-> vpngw-onprem connections that carry the source
        # lab's certified S1/S2/S3 evidence.
        Write-Host "T5 block is commented out. Nothing executed." -ForegroundColor DarkYellow
    }
}

Write-Host "Skeleton run complete. No Azure resource was created, modified, or deleted." -ForegroundColor Green
