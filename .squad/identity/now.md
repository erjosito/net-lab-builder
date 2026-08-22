---
updated_at: 2026-08-19T15:45:00+02:00
focus_area: Lab #4 dual-hub-vnra-udr-transit -- Stage-1 validation COMPLETE, E1 FAILED
active_issues:
  - E1 FAIL: cross-VNRA UDR chaining non-functional; root cause unknown; handed to Trinity/Tank
  - E2 CONFIRMED: no subnet-scope effective route API for VirtualNetworkApplianceSubnet
  - E3 INCONCLUSIVE: metrics 200 OK / 8 definitions / all zero (ambiguous with E1 failure)
  - Cost still running (~$33-$170/day); cleanup gated on Jose approval
---

# What We're Focused On

Lab #4 `labs/dual-hub-vnra-udr-transit/manifest.md` -- Stage-1 validation COMPLETE (2026-08-19).

**Validation outcome:** All S1-S5 scenarios executed. 23 sanitized evidence files under `show-output/validation/`. S1 baseline confirmed (100% loss without UDRs, RT detach/reattach cycle clean). S3 effective routes PASS (UDRs Active on both spoke NICs). S4 configured routes PASS. S5 E2 gap confirmed (404 from regional backend). **E1 FAILED** -- transit broken 100% loss both directions despite correct control plane. VNRA metrics 0 bytes/packets throughout.

**Key learnings appended to lessons-learned.md (L1-L10):**
- L1: Managed VNRA cross-hub UDR chaining does not work (empirical)
- L2: No subnet-scope effective route API (E2)
- L3: VNRA reserves 5 IPs per instance (undocumented)
- L4: NW cannot proxy VNRA forwarding context
- L5: Azure Monitor 200 OK without diag settings; values zero (E3 inconclusive)
- L6: VNRA does not respond to ICMP echo (expected)
- L7: traceroute not on Ubuntu 22.04 minimal; use tracepath
- L8: auto-NSGs from az nic create; VNRA subnet NSGs Azure-managed
- L9: MDE.Linux extensions auto-deployed by Defender for Cloud
- L10: RT detach uses --route-table null not ""

**Next:** Trinity/Tank to assess E1 root cause (MS support or topology redesign). Jose to authorize cleanup when ready.
