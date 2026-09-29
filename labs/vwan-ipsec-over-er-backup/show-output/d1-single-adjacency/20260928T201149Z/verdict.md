# D1 single-adjacency binding verdict

- Correlation: `d1-single-adjacency-20260928`
- Verdict: **Baseline acceptance failed; float not attempted; restored.**
- Azure D1 activation: ER site peer `10.250.254.242` with BGP enabled; Internet connection BGP disabled; no provider or physical-resource change.
- CPE D1 activation: one FRR neighbor `10.240.0.12` sourced from `10.250.254.242`; host route via `xfrm-pri1`; all four IPsec SAs preserved.
- Baseline control plane: BGP established and learned `10.240.0.0/24` and `10.241.0.0/24`. The first captured established state had an uptime of 17 seconds.
- Baseline application plane: two HTTP probes to `10.241.0.4:8080/health` timed out after 3 seconds. The required healthy application baseline was therefore not proven.
- Float behavior and return path: not tested. The host route was never moved to `xfrm-pub1`.
- Runtime incident: the bounded IAP observation channel hung and the CPE VM was later found stopped. The lease expired, so execution entered rollback only.
- Restore: ER site peer `10.250.254.240`, Internet BGP enabled, Instance0/Instance1 custom peers `169.254.21.5` and `169.254.22.5`, original four-neighbor FRR shape, and D2 payload state restored.
- Final health: ExpressRoute `Succeeded/Provisioned`, CPE VM `RUNNING`, and `pri0`, `pri1`, `pub0`, and `pub1` all `ESTABLISHED/INSTALLED`.
- Cost/resource state: no resources were created or deleted; existing Azure, GCP, and Megaport resources remain live and billable.

Primary evidence:

- `03-activation-azure/`
- `04-activation-cpe/`
- `05-baseline/`
- `06-restore-azure/`
- `07-restore-cpe/`
- `08-final-restored/`

