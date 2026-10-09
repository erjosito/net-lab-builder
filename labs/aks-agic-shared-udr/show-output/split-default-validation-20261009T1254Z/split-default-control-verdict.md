# Split-default control verdict

**Verdict: PASS — both control-gate preconditions are established.** The pod egress gate passed, and the Application Gateway backend-health control-plane gate failed persistently. **GatewayManager exception test: READY** for its separately approved lease; the exception was not applied and its effectiveness is not established here.

- Split routes were admitted at 2026-10-09 12:53:35 UTC. Read-only route verification at 13:04:48 UTC confirmed `0.0.0.0/0 → Internet`, `0.0.0.0/1` and `128.0.0.0/1 → VirtualAppliance 10.20.1.4`, and pod route `10.244.0.0/24 → VirtualAppliance 10.21.1.4`.
- From existing pod `default/web-6b6897c5b7-xvdrv` (`10.244.0.14`), Python `urllib` returned public source IP **20.91.222.168** from both `api.ipify.org` and `ifconfig.me/ip` (exit 0 each). This matches NVA `nva1` public IP. The earlier baseline did not capture a pod-originated Internet source IP, so no before/after IP comparison is claimed.
- `az network application-gateway show-backend-health --resource-group rg-aks-agic-shared-udr --name agw1 --output json` exited 0; backend `10.244.0.14` was **Unknown** in all 7 observations from 12:57:29 through 13:03:51 UTC (last query completed 13:04:31 UTC), spanning more than 10 minutes after split-route admission. Exact health detail: “Unable to retrieve health status data. Check presence of NSG/UDR blocking access to ports 65503-65534 from Internet to Application Gateway.”

No Azure, route, gateway, AKS, or pod configuration was changed. The verified split-default route state is intentionally left in place as the treatment starting point; restore remains pending the coordinator's separate decision/lease. HTTP data-plane availability was not used as a control-plane test.

Evidence: `show-output\split-default-validation-20261009T1254Z\` (command start/end times, stdout, stderr, exit codes, timeouts, and sanitization notes).
