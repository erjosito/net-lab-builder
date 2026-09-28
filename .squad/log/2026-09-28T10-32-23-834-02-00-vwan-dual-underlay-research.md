# Session Log: vWAN Dual-Underlay Research

**Timestamp:** 2026-09-28T10:32:23.834+02:00  
**Requested by:** Jose Moreno  
**Session type:** Architecture and lab-topology research

## Participants

| Agent | Focus | Outcome |
|---|---|---|
| Trinity | vWAN IPsec-over-ER plus Internet backup routing | Separate adjacencies recommended; managed vWAN cannot move one adjacency between underlays. Static Internet backup is conditional and health-blind without external controls. |
| Morpheus | Candidate validation topologies | Real ExpressRoute is required for exact validation. GCP Linux CPE offers highest fidelity; MCR is a possible minimum control-plane option pending feature and account verification. |

## Batch outcome

- The preferred production-oriented design uses distinct BGP adjacencies for the ER-carried and Internet-carried IPsec paths.
- A BGP-more-specific primary with a static aggregate backup can provide deterministic longest-prefix preference, but requires explicit testing and mitigation for stale static-route blackholing.
- The lab topology should include a real ExpressRoute circuit. Use a GCP Linux CPE for full routing-stack and payload fidelity, or consider MCR for a smaller control-plane-only validation after verifying support.
- No current-batch decision inbox files were present, so `decisions.md` was not changed.
- No cross-agent history propagation was required; both research outcomes were already recorded in the originating agent histories.
