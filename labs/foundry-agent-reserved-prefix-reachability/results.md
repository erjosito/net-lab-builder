# Results and Lessons Learned

## Current Status

| Scenario | Status | Evidence |
|----------|--------|----------|
| S3 — non-reserved control prefix | **Pass** | Foundry called `http://10.200.100.4/api/echo?msg=probe-control` successfully. |
| S4 — reserved `172.30.0.0/16` prefix | **Not run** | The primary lab question remains open. |
| S5 — forwarded on-premises DNS | **Not run** | Optional follow-up after S4. |

## Confirmed S3 Evidence

On 2026-08-14, the control VM recorded:

```text
192.168.0.49 "GET /api/echo?msg=probe-control HTTP/1.1" 200
```

The source address `192.168.0.49` belongs to the delegated `AgentSubnet`. This confirms that the
prompt agent's OpenAPI call traversed the single-tenant data proxy in the customer VNet, followed
the VPN/BGP path to `10.200.100.0/24`, and returned successfully.

## Lessons Learned

1. **A prompt-agent OpenAPI call can use a VPN-learned route.** The S3 call reached an address
   outside the Foundry VNet through Azure VPN Gateway and BGP, with a source address from the
   delegated subnet.
2. **Keep the tool set deterministic during network experiments.** With the web-search tool also
   enabled, the agent produced an error instead of reliably invoking the control API. Removing the
   unrelated tool allowed the same OpenAPI call to succeed. Use a dedicated agent or strict tool
   instructions so orchestration behavior does not masquerade as a network failure.
3. **Instrument both sides of the request.** The echo response now reports `server_ip`,
   `request_url`, and `src_ip`. Together with the VM journal, these fields identify the selected
   endpoint, the URL used by Foundry, and the observed data-proxy source.
4. **Plain HTTP worked in this lab configuration.** Foundry accepted and invoked the private
   `http://10.200.100.4` OpenAPI endpoint. Treat this as an observed lab behavior, not a general
   security recommendation or guarantee for every Foundry experience.
5. **Use separate single-NIC targets for comparative routing tests.** This keeps the control and
   reserved-prefix return paths symmetric and avoids Linux policy-routing ambiguity.

## Open Question

S3 proves the Foundry data proxy can traverse the VPN path. It does **not** prove that the reserved
`172.30.0.0/16` route is accepted at runtime. S4 must call `172.30.100.4` and correlate the agent
result with the target VM journal or packet capture before drawing that conclusion.
