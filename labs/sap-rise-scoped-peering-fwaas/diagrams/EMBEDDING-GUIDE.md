## 📋 Diagram Integration Notes for README Owner (Niobe)

When you complete `labs/sap-rise-scoped-peering-fwaas/README.md`, please embed the following mermaid diagrams in the specified sections. Use GitHub's native mermaid rendering (` ```mermaid ` fences with file content).

### Section: Topology
Embed content from: `diagrams/01-topology.mmd`

### Section: Control Plane
Embed content from: `diagrams/02-bgp-control-plane.mmd`

### Section: Route Propagation
Embed content from: `diagrams/03-route-propagation.mmd`

### Section: Cleanup Order
Embed content from: `diagrams/04-cleanup-chain.mmd`

---

**Values used:** All diagrams label with planned values from the Stage 1 lab card (Morpheus). Once you complete `show-output/` during Execute phase, signal Oracle for re-labeling pass to capture live values (actual IP assignments, peer IPs, etc.).

**Data-plane caveat (S2):** The control-plane diagram (02-bgp-control-plane.mmd) and route-propagation sequence (03-route-propagation.mmd) include a flag that S2's `summarizedGatewayPrefixes` fixes BGP advertisement but may not restore end-to-end data-plane reachability without a corresponding UDR on the spoke workload subnet. This is the primary teaching point Trinity is validating — diagram data-plane arrows may need revision once her resolution is complete.

---

*Oracle, Documentation & Diagrams*
