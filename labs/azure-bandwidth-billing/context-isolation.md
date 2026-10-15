# Context isolation and execution safety

**No login, config-directory creation, token copy, account switching or provider
registration was performed.** The later D0 infrastructure deployment reused the
existing profile with an explicit subscription on every CLI command and fresh
expected-tenant checks before mutations. See [deployment-log.md](deployment-log.md).
Only this lab folder may be changed; another active lab/session is unrelated.
Do not touch .squad history/state, shared IaC, skills, vaults or root indexes.

## Shared Windows CLI: read-only now

- Initial account discovery used an explicit supplied subscription display name;
  subsequent commands use the discovered ID held **in process memory only**.
  Never persist account names/emails/subscription/tenant IDs in tracked files.
- Every `az` call, including `az rest`, receives `--subscription $SubId`.
  Explicit REST subscription URL scope must match that argument.
- Never run `az account set`, shared `az login/logout`, `az config set`, extension
  changes or resource-provider registration. Even “helpful” registration is a
  mutation. Inspect registration read-only; ask coordinator if a gate fails.
- Catalogue availability is not live capacity proof. No preflight RG creation
  or validation in an unrelated existing RG is authorized by a design task.

## Future isolated Windows session (requires appropriate approval)

Use a **dedicated process** with process-local AZURE_CONFIG_DIR pointing strictly
inside this lab's ignored private directory. Do not set User/Machine variables.
The following is an illustrative setup, **not executed**:

```powershell
$LabRoot = 'C:\Users\jomore\Repos\net-lab-builder\labs\azure-bandwidth-billing'
# In a new dedicated shell, before its first Azure CLI call:
$env:AZURE_CONFIG_DIR = Join-Path $LabRoot 'private\azure-active'
# Provision/authenticate this isolated profile only under an approved auth lease.
# Obtain $SubId and $ExpectedTenantId privately; never hard-code them in this file.
$ActualTenantId = az account show --subscription $SubId --query tenantId -o tsv
if ($LASTEXITCODE -ne 0 -or $ActualTenantId.Trim() -ne $ExpectedTenantId) {
    throw 'Tenant verification failed; do not perform the action.'
}
```

That variable assignment affects only the shell and its children. In a reused
interactive shell, save the previous value and restore it in `finally`, or close
the dedicated shell. Fresh tool processes do not inherit a prior tool call's
assignment: set the environment in the same process that executes its CLI calls.
Do not create these private directories as part of this design task.

An empty isolated profile needs its own approved authentication; never copy
`.azure`, MSAL token files, access tokens, client secrets or refresh tokens from
the shared profile into it. Do not print credentials or use token/debug logging.
Use separate `private\azure-active` and `private\azure-msdn` profiles/processes.
No automatic fallback to shared credentials if isolated authentication fails.
Do not change global CLI extension/config state even in isolation without scope.

Before **every** live action: verify lease, STOP, expected subscription and
tenantId; verify resource RG/run tags for mutation. A cached earlier tenant check
does not authorize a later context change. Read-only discovery uses the same
explicit subscription pinning. Save only equality assertions in published results.
For two tenants compare actual tenantIds privately and require inequality;
for same-tenant/different-subscription control require tenant equality and
subscription inequality. Same user/account membership proves neither.

## Optional WSL strategy

**Current read-only comparison (2026-10-15):** Jose authorized use of the
existing authenticated Ubuntu-24.04 Linux CLI profile. It was reused unchanged;
no new profile, login, config directory, token copy or account switch occurred.
Subscription and tenant were privately verified distinct from Windows, then
every cost action was pinned and tenant-checked. Temporary private context is
not durable authentication knowledge. See [costs/README.md](costs/README.md).
The isolated-profile strategy below is an alternative, not a description of
what the comparison performed.

WSL is not required for first wave. If later approved, use a dedicated WSL process
with its **own Linux Azure CLI binary and separate config directory**, authenticated
independently. Keep any lab-owned persistent files under this lab's ignored private
tree, accessible via the approved WSL mount mapping; never use temporary folders
or copy Windows tokens into WSL. Check which CLI executable actually runs:
invoking Windows az from WSL can still use the Windows profile.

Pass process-local AZURE_CONFIG_DIR explicitly to that process and pin
`--subscription` on every call. Use separate isolated processes per tenant, no
shared `account set`, no global shell-profile/environment changes, no copied
credentials. Verify expected tenantId before each action, not just once at login.
Do not put subscription IDs or authentication commands in shell history/public
artifacts. Obtain a separate auth lease if identity setup is needed.

## Evidence and process boundaries

- Runtime maps, API bodies with IDs, endpoint PIPs, raw billing, transfer logs,
  certificates, keys, SAS URLs, Terraform state and leases belong in ignored
  local lab subdirectories only. Ignore rules are not a sanitization guarantee;
  explicitly review tracked artifacts before any future publication.
- Tiny Query probes are lab-filtered; never enumerate unrelated subscription
  costs. Detailed reports can include non-lab rows: filter in memory and persist
  **only lab rows**, or use a supported scoped path; never publish full reports.
- Each subprocess/HTTP operation gets <=120 seconds and a specific PID tree.
  On timeout terminate descendants before returning. No name-based process kills,
  detached collectors or billing wait loops; return idle and acquire a fresh
  bounded collection lease for 24/48/72h/day-7.
- Cleanup previews compare exact created inventory plus run tags. An approved
  deletion never includes another lab, unrelated RG or borrowed resources.
  Preserve subscription-level billing access and private ID/timestamp evidence
  before deleting lab infrastructure.

Historical design preflight: explicit-subscription account discovery succeeded;
SC SKU catalogue request timed out at 35 seconds. No result was obtained,
no NE/catalog or billing probe completed, and no live validation was attempted
in that design lease. Current billing prerequisite is documented in
[preflight.md](preflight.md); current D0 deployment/restore is documented in
[deployment-log.md](deployment-log.md). Do not treat those older design results
as current capacity or billing-access status.
