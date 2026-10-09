# GatewayManager treatment verdict

**Verdict: PASS — both validation gates passed.**

- **Pod egress preserved:** existing pod `default/web-6b6897c5b7-xvdrv` (`10.244.0.14`) returned `20.91.222.168` from both `api.ipify.org` and `ifconfig.me/ip` in the post-admission checks. The same source IP was confirmed again after the second healthy backend query. This matches the pre-treatment NVA source IP.
- **Application Gateway health recovered:** `agw1` reported backend `10.244.0.14` **Healthy** in both `web-private` and `web-public` backend settings, with probe detail `Success. Received 200 status code`, in two consecutive queries. The first query completed at `2026-10-09T13:13:31.6756581Z`, 4m 52s after GatewayManager admission at `13:08:39.632484Z`; the confirming query completed at `13:15:02.7073500Z`.
- **Routes preserved:** the current route list matched the post-admission snapshot: `0.0.0.0/0 → Internet`; `0.0.0.0/1` and `128.0.0.0/1 → VirtualAppliance 10.20.1.4`; pod route `10.244.0.0/24 → VirtualAppliance 10.21.1.4`; and `GatewayManager → Internet`. The treatment remained intact.

Evidence is in this directory. Successful decisive captures are `10-route-state.stdout.txt`, `11-backend-health-01.stdout.json`, `12-pod-ipify.stdout.txt`, `13-pod-ifconfig.stdout.txt`, then `15-backend-health-02.stdout.json`, `16-pod-ipify.stdout.txt`, and `17-pod-ifconfig.stdout.txt`. `19-local-closeout-check-corrected.json` records an exact five-route comparison and no matching validation CLI processes. Every Azure/kubectl invocation has timestamp, stdout, stderr, exit code, and timeout metadata; subscription/resource GUIDs are redacted. Initial launcher attempts are retained as captures but were not counted as probes because argument forwarding produced CLI help/error output.

No route, gateway, feature, NSG, outbound-type, or pod configuration was changed by this validation. No child command remains. The approved treatment is intentionally left in place; restore is **not** part of this lease and remains for the coordinator's separate restore decision. This is a bounded observed result, not a claim about permanent service behavior.
