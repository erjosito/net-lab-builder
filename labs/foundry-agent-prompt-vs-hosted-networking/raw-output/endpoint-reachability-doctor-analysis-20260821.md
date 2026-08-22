# Endpoint Reachability and azd Doctor Analysis — 2026-08-21
# Lab: foundry-agent-prompt-vs-hosted-networking
# Sanitized: no subscription IDs, tenant IDs, endpoints, or tokens

---

## 1. Workstation Endpoint Reachability

### DNS Resolution (from workstation)
- <account>.services.ai.azure.com resolves to: **PUBLIC IP** (`<public-ip>`)
- NOT the private endpoint IP (192.168.1.10)
- Workstation is outside vnet-foundry; private DNS zones not applied

### Comparison: DNS from inside vnet-foundry (vm-diag, MgmtSubnet)
- <account>.services.ai.azure.com resolves to: **192.168.1.10** (PESubnet private endpoint IP)
- Azure Private DNS zone privatelink.services.ai.azure.com intercepts resolution from inside VNet

### TCP 443 Reachability
- Workstation → public IP:443 = **REACHABLE** (Test-NetConnection: True)
- Round-trip to project endpoint: 1,631ms (REST GET, authenticated)
- Public access on Foundry account: already enabled (pre-existing; not weakened by this lab)

### Security Assessment
- Public access was already enabled before this lab; no new exposure created
- Private endpoint provides additional private path for VNet-attached resources
- Workstation uses public path for azd deploy and invocations (functioning as designed)
- Niobe constraint satisfied: public access NOT weakened; existing state preserved

---

## 2. azd Doctor Authentication Timeout — Root Cause

### Symptom
zd ai agent doctor remote.auth check: "Token acquisition timed out after 10s."

### Root cause (confirmed)
- doctor's auth check has a hardcoded **10-second gRPC timeout**
- z account get-access-token --scope "https://management.azure.com/.default" takes **~15 seconds** on this workstation
- Token acquisition IS successful (returns valid 2407-char token); it just exceeds the 10s window
- Workstation-specific latency (network, Entra cache miss pattern, or MFA flow delay)

### Implication
- NOT an endpoint reachability failure
- NOT an authentication failure
- NOT a network block
- Doctor remote checks are all skipped (auth never resolves within timeout)
- zd deploy echo-probe-agent is NOT affected: deploy uses a different credential acquisition path (proven to work in prior session, 3m 5s)
- Direct REST API calls with z account get-access-token (default scope) work fast (<1s)

### Workaround
- Use z account get-access-token (default scope) + direct REST API for agent invocation and status checks
- Do NOT use zd ai agent invoke (gRPC chain, same 10s timeout risk)
- Do NOT use scope-based token for doctor; doctor works with whatever az CLI provides if within 10s

---

## 3. ENABLE_HOSTED_AGENTS and ENABLE_CAPABILITY_HOST — Provenance

### Values observed
- ENABLE_HOSTED_AGENTS="true"
- ENABLE_CAPABILITY_HOST="false"

### Binary evidence
- String "ENABLE_HOSTED_AGENTS" found in: ~/.azd/extensions/azure.ai.agents/azure-ai-agents-windows-amd64.exe
- The zure.ai.agents extension (NOT azd core) writes these vars

### Which command created them
- **zd deploy echo-probe-agent** — run on 2026-08-21 07:42–07:46 UTC+2
- The zure.ai.agents extension's pre-deploy hook queries the Foundry project to detect project capabilities
- It stamps these vars into the azd environment as capability flags for the deploy pipeline

### Doctor does NOT set these vars
- Confirmed by before/after comparison: doctor output shows no change to ENABLE_ vars across 2 runs
- Doctor reads (for remote.hosted-agents-active check) but does NOT write ENABLE_ vars

### Meaning
- ENABLE_HOSTED_AGENTS="true" — Foundry project has hosted agents capability enabled
- ENABLE_CAPABILITY_HOST="false" — project does NOT have capability host (a separate Foundry feature for hosting custom extensions) enabled
- These are benign project capability flags; they do not affect deploy behavior or security posture

---

## 4. Agent Status Verification (post-session)

### echo-probe-agent:1
- Status: **active** (confirmed via GET agent endpoint, HTTP 200)
- Created: 2026-08-21T05:44:28Z
- Runtime: python_3_13, host: azure.ai.agent
- Agent is persistent — no VMs required to maintain agent registration

### VM state
- vm-tools-echo, vm-tools-ctrl, vm-diag: deallocation requested (no-wait, end of prior session)
- Agent invocations require VMs to be running (probe_echo/probe_ctrl call HTTP to VNet targets)
- Agent registration itself persists regardless of VM state

---

## 5. Niobe Constraint Compliance

| Constraint | Status |
|-----------|--------|
| Use zd deploy echo-probe-agent (scoped) | COMPLIANT — only this command was run for deploy |
| Never zd provision, zd up, zd down | COMPLIANT — none of these were run |
| AZURE_RESOURCE_GROUP blast radius documented | DOCUMENTED — RG is shared lab RG; provision verbs prohibited |
| Doctor endpoint fail → do not weaken public access | COMPLIANT — public access was pre-existing; no change made |
| Consider vm-diag for invocations if endpoint blocked | N/A — workstation reaches public endpoint; vm-diag remains available as backup |