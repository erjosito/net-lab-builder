#Requires -Version 7.0
<#
.SYNOPSIS
    TP-HH delta-only rollback skeleton — Dual-Hub Interconnect and Route Server Route-Map Policy.

.DESCRIPTION
    THIS SCRIPT DOES NOT DELETE OR MODIFY ANYTHING. It is the paired rollback skeleton for
    scripts/apply.ps1, written during the TP-HH extraction task (Tank, 2026-08-05) per Morpheus's
    approved extraction contract (.squad/decisions/inbox/morpheus-us10-us11-extraction.md §6, §8 row 21).

    This script reverses ONLY the additive deltas this lab's own apply.ps1 may have created
    (hub<->hub peering, route-map associations, NVA BGP/tunnel config). It NEVER targets, deletes,
    or recreates the shared resource group rg-dual-hub-hubless-region-ars-lab3d001 itself, and it
    NEVER runs any cleanup command against labs/dual-hub-hubless-region-ars's own resources beyond
    the specific delta named by -Scenario.

    Every Azure CLI / az rest call below is COMMENTED OUT, matching apply.ps1's gating discipline:
    this script refuses to execute any Azure command until -Scenario, -ResourceGroup,
    -SubscriptionId and -ApprovalConfirmed are all supplied and validated.

    Rollback is idempotent by design: re-running rollback against an already-rolled-back scenario
    must exit cleanly (the re-check step verifies current state before attempting any reversal).

    Phase-4 corrections (Trinity, 2026-08-05 -- see design.md §8a):
      * Dissociation is a PUT on the bgpConnection, NOT a PATCH (no PATCH operation exists on this
        child resource type; expect HTTP 405). The restore body must carry peerAsn + peerIp and
        OMIT routingConfiguration.inboundRouteMap entirely -- there is no "null" to set.
      * T2b reverts a routeMap under virtualHubs/<ars>/routeMaps/<name>, NOT virtualHubRouteTables.
      * T2a/T2b operate on the DEDICATED TEMPORARY map rm-hub1-tmp-assoc, which is DELETED at the
        end of T2a rollback. rm-hub1-activate must be left byte-identical and is never touched.
      * U0 rollback (deallocate) is additionally available and is the cheapest reversal in the set.

    Phase-4 corrections (Trinity, 2026-08-06 -- post-U0/U1, finding TANK-001):
      * NEW: -Scenario U15 (BIRD Poland-state removal) and -Scenario U3a (BIRD documentation-prefix
        injection). Both reverse on the NVA, not in ARM: `birdc configure undo` is the fast path,
        restoring /etc/bird/bird.conf.pre-u15.<STAMP> is the durable one. `systemctl restart bird`
        is a LAST RESORT ONLY -- it resets every BGP session and black-holes both spokes' 0/0.
      * T2a rollback body must be the SAVED PRE-U2 GET (00-pre-peer-nva1-GET.json), not a
        hand-written body: PUT replaces properties wholesale, so vnetRoutes AND its
        staticRoutesConfig must be sent back exactly as they were read.
      * T2b now reverts a rule keyed on 198.51.100.0/24, not 10.10.0.64/27.
#>

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('U0', 'T1', 'U15', 'T2a', 'U3a', 'T2b', 'T3', 'T5')]
    [string]$Scenario,

    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,          # Expected: rg-dual-hub-hubless-region-ars-lab3d001 (shared bed)

    [Parameter(Mandatory = $true)]
    [string]$SubscriptionId,

    [switch]$ApprovalConfirmed       # Explicit second gate -- separate from the built-in -Confirm/
                                      # -WhatIf that [CmdletBinding(SupportsShouldProcess)] already
                                      # provides. Must be passed explicitly; there is no default.
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------------------------
# Gate 1 — identical hard-refuse discipline as apply.ps1. Rollback is just as capable of BGP
# disruption (route refresh / hard reset) as apply, so it is gated exactly as strictly.
# ---------------------------------------------------------------------------------------------
$expectedRg = 'rg-dual-hub-hubless-region-ars-lab3d001'
if ($ResourceGroup -ne $expectedRg) {
    throw "REFUSED: -ResourceGroup '$ResourceGroup' does not match the expected shared bed RG " + `
          "'$expectedRg'. This rollback script will never target any other resource group, and " + `
          "will never issue a resource-group-level delete under any circumstance."
}

if ([string]::IsNullOrWhiteSpace($SubscriptionId) -or $SubscriptionId -match '<.*>') {
    throw "REFUSED: -SubscriptionId is missing or still a placeholder."
}

if (-not $ApprovalConfirmed) {
    throw "REFUSED: pass -ApprovalConfirmed explicitly to acknowledge you have read design.md §7 " + `
          "(maintenance-window / BGP-reset protocol) before rolling back scenario '$Scenario'."
}

Write-Host "Gates passed for rollback of scenario '$Scenario'. NO AZURE COMMAND HAS BEEN EXECUTED." -ForegroundColor Yellow

switch ($Scenario) {

    'U0' {
        # --- Revert: deallocate vm-nva1 + vm-nva2 (return to the 2026-08-05 quiescent state) ----
        # Cheapest reversal in the set. Stops the +$0.58/day compute delta. Disks and any public
        # IPs continue to bill exactly as they do today.
        # Roll back T1/T2a/T2b FIRST if they were applied -- deallocating the NVAs while an
        # association or peering is in place leaves the bed in a state no baseline describes.
        #
        # az vm deallocate --resource-group $ResourceGroup --name vm-nva1
        # az vm deallocate --resource-group $ResourceGroup --name vm-nva2
        #
        # Post-rollback: az vm list -d must show both as "VM deallocated"; both ARS learned and
        # advertised sets must return to empty.
        Write-Host "U0 rollback block is commented out. Nothing executed." -ForegroundColor DarkYellow
    }

    'T1' {
        # --- Revert: delete both peering objects created by apply.ps1 -T1 -----------------------
        # Idempotency check first (uncomment): confirm the peering objects still exist before
        # attempting delete; if already absent, log and exit 0 rather than erroring.
        #
        # az network vnet peering delete --name peer-hub1-to-hub2 --resource-group $ResourceGroup --vnet-name vnet-hub1
        # az network vnet peering delete --name peer-hub2-to-hub1 --resource-group $ResourceGroup --vnet-name vnet-hub2
        #
        # Post-rollback: re-capture show-output/new/t1-hub-peering/ and diff against the
        # pre-T1 baseline to confirm byte-comparable state. The hub<->spoke peerings
        # (peer-hub1-to-spoke-a, peer-hub2-to-spoke-b) must be left untouched.
        Write-Host "T1 rollback block is commented out. Nothing executed." -ForegroundColor DarkYellow
    }

    'U15' {
        # --- Revert: restore the pre-U1.5 bird.conf on the affected NVA(s) -----------------------
        # Roll back ONE NVA at a time, the one that tripped the trigger. Rolling back both when
        # only one misbehaved destroys the comparison that made the fault diagnosable.
        #
        # ROLLBACK TRIGGERS (any one, checked at T+30/60/120/180 s) -- full text in
        # ../nva-config/README.md section 6:
        #   1. any ars_hub1_0/1 or ars_hub2_0/1 session not Established, OR its Since timestamp moved
        #   2. 0.0.0.0/0 absent from either ARS learned set on either instance at T+60 s
        #   3. 10.10.0.64/27 or 10.20.0.64/27 absent from `birdc show route`
        #   4. any non-zero ICMP loss vm-nva1 <-> vm-nva2
        #   5. any byte change in vpngw-hub1/hub2 advertised-to-onprem or vpngw-onprem learned
        #   6. any of the four VPN connections leaves Connected
        #   7. `birdc configure` did not report a successful reconfiguration
        #   8. any prefix other than 10.30.0.0/27 changed anywhere
        #
        # FAST PATH (valid only while this was the most recent `configure`):
        #   sudo birdc configure undo
        #
        # DURABLE PATH (always valid):
        #   sudo cp -p /etc/bird/bird.conf.pre-u15.$STAMP /etc/bird/bird.conf
        #   sudo bird -p -c /etc/bird/bird.conf
        #   sudo birdc configure
        #
        # A second, independent restore source exists in version control if the on-disk backup is
        # lost: ../nva-config/bird-nva1.as-found-2026-08-06.conf / bird-nva2.as-found-2026-08-06.conf.
        #
        # VERIFY: `birdc show protocols` -> ars_hub*_0/1 Established, ars_poland_0/1 back and
        # sitting in Connect/Active (expected, harmless). ARS learned set contains 10.30.0.0/27
        # again on BOTH instances -- rollback is complete only when the bed is back in its KNOWN
        # state, stale prefix and all. Expected duration: under 2 minutes per NVA.
        #
        # LAST RESORT ONLY, if the daemon will not accept `configure`: sudo systemctl restart bird.
        # This resets every session and momentarily black-holes both spokes' 0/0. Record it as a
        # deviation with its exact duration.
        Write-Host "U15 rollback block is commented out. Nothing executed." -ForegroundColor DarkYellow
    }

    'T2a' {
        # --- Revert: dissociate the map, then delete the temporary map --------------------------
        # HUB1 ONLY (unit U2 associated hub1 only). VERB IS PUT, NOT PATCH.
        # The restore body carries peerAsn 65001 + peerIp 10.10.1.4 and OMITS
        # routingConfiguration.inboundRouteMap entirely -- there is no "null" form to set.
        #
        # Step 1 -- restore the bgpConnection to its pre-U2 shape. THE BODY MUST BE THE SAVED
        # PRE-U2 GET (show-output/new/t2-routemap-assoc/00-pre-peer-nva1-GET.json), with only
        # properties.provisioningState deleted and routingConfiguration.inboundRouteMap omitted.
        # PUT replaces properties wholesale: vnetRoutes AND its staticRoutesConfig
        # (propagateStaticRoutes, vnetLocalRouteOverrideCriteria) must go back exactly as read,
        # or the rollback silently changes settings U2 never touched. bodies/bgpconn-restore-hub1.json
        # reproduces the live 2026-08-06 shape and is the fallback if the evidence file is lost.
        # az rest --method put `
        #   --uri "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Network/virtualHubs/ars-hub1/bgpConnections/peer-nva1?api-version=2024-10-01" `
        #   --body "@$PSScriptRoot/bodies/bgpconn-restore-hub1.json"
        #
        # Step 2 -- delete the temporary map (only after Step 1 returns Succeeded):
        # az rest --method delete `
        #   --uri "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Network/virtualHubs/ars-hub1/routeMaps/rm-hub1-tmp-assoc?api-version=2024-10-01"
        #
        # rm-hub1-activate and rm-hub2-activate MUST be left byte-identical -- they are the source
        # lab's tier-activation artefacts and are never touched by this rollback.
        #
        # NOTE: the ARS route-map tier surcharge does NOT revert via this rollback (it is a
        # tier-level charge, already sunk against the source lab, not reversible short of ARS
        # delete+recreate). This rollback only removes the association, not the tier.
        Write-Host "T2a rollback block is commented out. Nothing executed." -ForegroundColor DarkYellow
    }

    'U3a' {
        # --- Revert: remove the temporary documentation prefix from vm-nva1 ---------------------
        # Deletes the `protocol static u3_doc_test { ipv4; route 198.51.100.0/24 blackhole; }`
        # block, returning /etc/bird/bird.conf to ../nva-config/bird-nva1.u15-target.conf.
        #
        #   sudo birdc configure undo                                   # fast path
        #   # -- or --
        #   sudo cp -p /etc/bird/bird.conf.pre-u3a.$STAMP /etc/bird/bird.conf
        #   sudo bird -p -c /etc/bird/bird.conf
        #   sudo birdc configure
        #
        # ORDER MATTERS: if U3b (the AS-Path map rule) is still applied, roll THAT back first, or
        # the map is left keyed on a prefix that no longer exists -- harmless but undocumented.
        #
        # VERIFY: 198.51.100.0/24 absent from `birdc show route`, absent from ars-hub1's learned
        # set on BOTH instances, and ars_hub1_0/1 still Established with unchanged Since.
        Write-Host "U3a rollback block is commented out. Nothing executed." -ForegroundColor DarkYellow
    }

    'T2b' {
        # --- Revert: restore the U2 inert rule (undo the AS-Path Add on 198.51.100.0/24) --------
        # Returns rm-hub1-tmp-assoc to the unmatchable 203.0.113.0/24 (TEST-NET-3) rule, i.e. the
        # U2 state. To go all the way back to the U1.5 state, run -Scenario T2a afterwards, then
        # -Scenario U3a to remove the documentation prefix from BIRD.
        #
        # az rest --method put `
        #   --uri "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Network/virtualHubs/ars-hub1/routeMaps/rm-hub1-tmp-assoc?api-version=2024-10-01" `
        #   --body "@$PSScriptRoot/bodies/routemap-tmp-assoc-hub1.json"
        #
        # Post-rollback: 198.51.100.0/24 must show AS-PATH "65001" again at both ARS instances.
        Write-Host "T2b rollback block is commented out. Nothing executed." -ForegroundColor DarkYellow
    }

    'T3' {
        # --- Revert: tear down the eBGP session/tunnel; restore T1-only state -------------------
        # Would also have to remove the TCP/179 NSG rules added to nsg-nva-hub1/nsg-nva-hub2 and
        # restore both bird.conf files from the copies captured in U0 (they are NOT in version
        # control). T3 is not preapproved and has no apply block, so this has no implementation.
        Write-Host "T3 rollback has no implemented block yet (T3 itself is not yet implemented)." -ForegroundColor DarkYellow
    }

    'T5' {
        # --- Revert: association back to None on the VPN gateway connection ----------------------
        # Applies only if T5 Step 2 ever ran. Step 1 is read-only and needs no rollback.
        # NOTE: the connection resource type/ID form is UNKNOWN -- the live bed exposes only
        # Microsoft.Network/connections (VirtualNetworkGatewayConnection), which has no
        # inboundRouteMap/outboundRouteMap member. The URI below is a placeholder and must be
        # replaced with whatever Step 1's read-only probe actually finds, if anything.
        #
        # az rest --method put `
        #   --uri "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Network/<TYPE-FROM-STEP-1>/<NAME>?api-version=2024-10-01" `
        #   --body "@$PSScriptRoot/bodies/routemap-dissociate-body.json"
        #
        # Post-rollback: re-verify all four Microsoft.Network/connections objects stay Connected
        # with 4 tunnels each and byte-comparable to the pre-T5 baseline.
        Write-Host "T5 rollback block is commented out. Nothing executed." -ForegroundColor DarkYellow
    }
}

Write-Host "Skeleton rollback complete. No Azure resource was created, modified, or deleted." -ForegroundColor Green
