# Results and Lessons Learned

## Current Status

| Scenario | Status | Evidence |
|----------|--------|----------|
| S3 — non-reserved control prefix | **Pass** | Foundry called `https://10.200.100.4/api/echo?msg=probe-control` successfully. |
| S4 — reserved `172.30.0.0/16` prefix | **Pass** | Foundry called `https://172.30.100.4/api/echo?msg=probe-reserved` successfully. |
| S5 — forwarded on-premises DNS | **Not run** | Optional DNS-specific follow-up; not required for the routing conclusion. |

## Confirmed Chat and Target Evidence

The final Foundry chat returned these completed OpenAPI tool outputs:

```json
{
  "control": {
    "server_ip": "10.200.100.4",
    "request_url": "https://10.200.100.4/api/echo?msg=probe-control",
    "src_ip": "192.168.0.49"
  },
  "reserved": {
    "server_ip": "172.30.100.4",
    "request_url": "https://172.30.100.4/api/echo?msg=probe-reserved",
    "src_ip": "192.168.0.49"
  }
}
```

The corresponding VM journals recorded HTTP 200 requests from `192.168.0.49`. An earlier successful
reserved-prefix call used `192.168.0.239`, showing that the data-proxy source IP can change within
AgentSubnet.

The full distilled evidence is stored in
`raw-output/foundry-chat-evidence-20260814.json`.

## Conclusion

In this tested configuration, Foundry's prohibition on assigning `172.30.0.0/16` to the Foundry VNet
or a peered VNet did **not** prevent a prompt agent from reaching that prefix when it existed behind a
VPN/BGP-learned route. Both the control and reserved-prefix endpoints completed successfully.

## Lessons Learned

1. **A prompt-agent OpenAPI call can use VPN/BGP-learned routes, including the tested reserved
   prefix.** The data proxy reached both `10.200.100.4` and `172.30.100.4` with source addresses from
   the delegated subnet.
2. **Keep the tool set deterministic during network experiments.** With the web-search tool also
   enabled, the agent produced an error instead of reliably invoking the control API. Removing the
   unrelated tool allowed the same OpenAPI call to succeed. Use a dedicated agent or strict tool
   instructions so orchestration behavior does not masquerade as a network failure.
3. **Instrument both sides of the request.** The echo response now reports `server_ip`,
   `request_url`, and `src_ip`. Together with the VM journal, these fields identify the selected
   endpoint, the URL used by Foundry, and the observed data-proxy source.
4. **The self-signed HTTPS endpoints worked in this lab configuration.** Foundry invoked both
   `https://` IP-address endpoints successfully despite their self-signed certificates. Treat this
   as observed behavior, not a documented trust-store contract or production recommendation.
5. **Use separate single-NIC targets for comparative routing tests.** This keeps the control and
   reserved-prefix return paths symmetric and avoids Linux policy-routing ambiguity.
6. **Allow the delegated subnet, not a single observed source IP.** Successful calls used both
   `192.168.0.49` and `192.168.0.239`; NSGs should permit the required traffic from AgentSubnet.
