# Simulator routing assessment

**2026-11-24: PASS for the declared converged routing abstraction.
INCONCLUSIVE for the customer's failure.** No live packets, APIPA BGP source
selection, Palo Alto state or convergence timing were tested by the simulator.

Import [simulator-topology.json](simulator-topology.json) into the Azure Network
Simulator's classic/hub-spoke workspace. It uses a VNet VPN Gateway, not vWAN:
two private overlay connections and one Internet connection to the same overlay
site. The Internet advertisement has two extra `64513` prepends, producing the
observed total AS path length of three.

## Observed model results

Engine `2026.11.16.13`, contract 2, `evaluate`, complete control plane in all
three runs. [Evidence excerpts](simulator-results.json) retain the requirement
outcomes and decisive routes. All simulation-section chunks were read completely.

| State | Model input change | Observed selection |
|---|---|---|
| Healthy | None | VPN gateway prefers `private0` and `private1`, path `[64513]`; Internet `[64513,64513,64513]` is not preferred |
| Declared private withdrawal | Disable both ER links **and both private VPN connections** | Internet is the only preferred payload route; forward/reply routing requirement satisfied; ER outer `/32` absent |
| Boundary control | Disable only both ER links; leave VPN connections enabled | Private payload routes remain preferred despite losing the outer `/32`; proves this model does not infer the nested transport dependency |

The healthy CPE RIB has three equally preferred Azure routes with AS path
`[65515]`. Prepending CPE advertisements changes Azure's selection, not the
CPE's import preference. The sample forward/reply trace selected `private0`
in both directions, but that deterministic trace does not prove all real flows
are symmetric. This supports checking the customer's reverse-path policy,
not concluding that asymmetry is the confirmed fault.

The boundary control is deliberately unrealistic. It is an abstraction check,
**not a successful live failover**. The second run assumes private withdrawal;
it does not predict whether or when Azure/CPE detect ER loss.

## Fidelity limits

Only the outer endpoint `10.245.0.10/32` is advertised over ER. The payload
`10.246.1.0/24` is never advertised directly on ER to force a desired result.
The extra `underlay` site is a logical provider/outer-endpoint abstraction,
not another physical CPE. Its separate modeled RIB does **not** reproduce the
real CPE's shared underlay/overlay FIB, recursive peer routing or feedback.
All three overlay connections do use one modeled overlay site.

The model does not encode the default/APIPA peer TCP tuples, gateway-instance
listener/source binding, IKE initiation, IPsec SAs, private outer addresses,
stateful PAN-OS behavior, in-place static-to-BGP history or convergence timers.
The simulator's route-level "delivered" label is not packet delivery evidence.
These remain live-lab acceptance gates in [customer-fidelity.md](customer-fidelity.md).
The static migration sequence was not simulated.

## Repeating the runs

Use the native topology in a request with `contractVersion: 2`,
`operation: "evaluate"` and `document: {mode: "hub-spoke", topology: ...}`.
Use `budget: {maxMillis: 15000, maxOutputBytes: 1000000}`.
Each run starts from a fresh copy of the healthy JSON.

The common flow requirement uses:

```json
{
  "id": "overlay-payload-configured",
  "kind": "flow",
  "source": {"kind": "subnet", "vnetId": "azure", "subnetId": "workload"},
  "target": {"kind": "site", "siteId": "cpe"},
  "sourceAddress": "10.244.1.4",
  "destinationAddress": "10.246.1.1",
  "expectation": "allow"
}
```

For private withdrawal, set `enabled: false` on `azure-er`, `gcp-er`,
`private0` and `private1`, leaving `internet` enabled. Add exact-prefix route
requirements on table `workload`: `10.245.0.10/32` absent and
`10.246.1.0/24` present. The boundary control disables only `azure-er` and
`gcp-er`, and checks the same flow plus absence of the outer `/32`.
The evaluated snapshots used descriptive state-specific topology names and
flow requirement IDs recorded in the evidence excerpts.
