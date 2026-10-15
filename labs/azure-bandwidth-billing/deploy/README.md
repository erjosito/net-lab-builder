# D0 infrastructure

## Additional isolated MSDN endpoint T (native WSL)

`msdn.py` + `msdn-main.json` are the separate one-VM deploy/cleanup pair;
they do not modify the Windows A/B/P template or profile. Actual T is
Standard_B1s in Sweden Central, allocated successfully and verified deallocated
2026-10-15 08:22:55Z. Its $0.0108/hour retail rate equals the approved B2ts_v2
ceiling; B1ls is excluded below 1 GiB. Six resources plus a new tagged RG;
all inbound denied, no downloads/harness/extensions.

From the repository root, with an already authenticated Ubuntu-24.04 native
Linux CLI and ignored `private\wsl-cost-context.private.json` containing explicit
`subscriptionId`/`expectedTenantId`:

```powershell
python -B -m unittest discover -s labs\azure-bandwidth-billing\deploy -p test_msdn.py
$checkout = (Get-Location).Path
$mount = '/mnt/' + $checkout.Substring(0, 1).ToLowerInvariant() + $checkout.Substring(2).Replace('\', '/')
$script = "$mount/labs/azure-bandwidth-billing/deploy/msdn.py"
wsl.exe -d Ubuntu-24.04 --exec timeout --kill-after=5s 180s /usr/bin/python3 -B $script preflight
wsl.exe -d Ubuntu-24.04 --exec timeout --kill-after=5s 600s /usr/bin/python3 -B $script deploy --confirm DEPLOY-ONE-MSDN-ENDPOINT
wsl.exe -d Ubuntu-24.04 --exec timeout --kill-after=5s 120s /usr/bin/python3 -B $script preview-cleanup
# Only after separate deletion approval and a NEW cleanup-authorized lease:
wsl.exe -d Ubuntu-24.04 --exec timeout --kill-after=5s 600s /usr/bin/python3 -B $script cleanup --confirm <private-run-id>
```

Adjust only the intrinsic WSL mount path for another checkout. Every live action,
including preview, requires an active `deploy\.runtime-control\msdn-lease.json`
and absent STOP. Deploy consumes four reserved mutation commands, refuses existing
inventory/groups, automatically deallocates even after deployment failure, and
closes its lease completed/blocked. Therefore preview after deployment needs a
fresh read-only lease (the initial live preview preceded lease closure).
Never remove inventory to force a redeployment. `restore` deallocates only the
exact inventoried VM, under an active restore-authorized lease.

Reuse requires fresh cost approval/price verification, a <=30-minute lease with
bounded calls/timeouts, and explicit `allowedMutations` strings matching the
operations in `msdn.py`. Cleanup additionally requires the exact string
`delete the exact inventoried MSDN lab resource group`; the deployment lease
does **not** authorize deletion. Preview compares exact identities, names and
tags against creation inventory; unrecorded/foreign resources block deletion.
Cleanup is idempotent only after a recorded verified deletion. Source/template
contain no keys: an existing native Linux public key, or the existing Windows
`~\.ssh\id_rsa.pub`, is read into an ignored ARM secure-parameter JSON file.
Tokens remain in native WSL memory. No login/account-set/register/config writes.

**$4 additional envelope, max 12 allocated hours and 72 hours disk/PIP lifetime.**
Disk and static PIP still accrue charges after deallocation. Current cleanup
deadline **2026-10-18 08:20:59Z**; no deletion or traffic was authorized/executed.
Full actual facts: [MSDN deployment log](../msdn-deployment-log.md).

## Windows A/B/P infrastructure

`main.json` is native ARM: three non-Spot Ubuntu 22.04 Gen2 VMs (A/B/P),
30 GiB Standard SSD OS disks, two static Standard IPv4 PIPs, three NIC/NSGs,
and two unpeered Sweden Central VNets. A/P share a VNet; P has no public IP or
implicit outbound. Azure's management agent is the intended control channel;
private P run-command reachability is not yet verified. No apt/pip/download
bootstrap, certificates, listener or transfer runner is installed.

**All inbound, including intra-VNet traffic, is explicitly denied.** Opening
private/public 443 is a separate approved harness deployment: require pinned
mTLS, exact peer allowlists, one-use IDs, 5 GiB handlers, 20 Mbit/s, 45-minute
deadlines, streaming hashes and the aggregate 35 GiB wire cap before opening.
Do not mistake infrastructure provisioning for a transport/billing result.
No public SSH rule, operator IP discovery, NAT/LB/peering, C/NE or paid logs.
The tagging extension applies mandatory tags to implicitly created OS disks.

## Reproduction (PowerShell 7, existing installed Azure CLI only)

1. Obtain a fresh active lease and owner approval. Resolve subscription and
   expected tenant privately from the authorized profile/owner; never switch
   CLI context. Privately create `private\context.private.json` with
   `subscriptionId`, `expectedTenantId`, `runId` (`bwb-` plus 12 lowercase
   hexadecimal characters), and matching `resourceGroup` (`rg-` plus runId).
   Never copy tokens or create authentication state for this task.
2. `.\deploy\Test-Local.ps1` — offline only.
3. `.\deploy\Preflight.ps1 -ContextPath .\private\context.private.json -SshPublicKeyPath <existing-public-key>`
   — explicit-subscription identity check, read-only provider state and bounded
   directly authenticated HTTPS catalogue (120 seconds total, <=10 pages).
   No billing requests. Location restrictions block; zone restrictions do not
   prevent a nonzonal request. Walk B1ls/B1s/B2ts_v2/B2ls_v2/B2s_v2 in order;
   exclude B1ls's 0.5 GiB for TLS/agent memory. Current approved price evidence
   covers SC B2ts_v2; another selected size blocks pending a fresh price gate.
4. `.\deploy\Deploy.ps1 -ContextPath .\private\context.private.json` —
   refuses existing RG, requires fresh gate and six reserved mutation slots.
   Creates one RG, performs native ARM `deployment group validate` using a
   parameters JSON file (no VM creation), deploys one template, then deallocates
   each of three VMs and records private inventory/power evidence. Validation
   **does not guarantee capacity**; only successful actual allocation does.
   All errors surface; partial-deployment inventory is retained. Never rerun
   blindly; existing groups are intentionally rejected.
5. Cleanup defaults to preview:
   `.\deploy\Cleanup.ps1 -ContextPath .\private\context.private.json`.
   After separate explicit owner deletion approval and a fresh cleanup lease:
   add `-Confirmed -ConfirmRunId <private-run-id>`. Exact group/run tags and
   created inventory must match; foreign/unrecorded resources freeze deletion.
   Inventory/power/cleanup timestamps and all resource identifiers stay private.

The $0.08/hour / $8 envelope is planning, not an Azure spend hard stop.
Deallocated disks/PIPs remain billable: enforce <=72 hours lifetime and
<=12 allocated hours/slot across the core. No overnight allocation or
unapproved deletion/scheduler. Failure/expiry/STOP requires coordinator handoff;
do not authorize yourself another operation. `Common.ps1` enforces bounded
specific-process execution, explicit subscription, tenant and lease checks.
Deployment restore actions may cross the 80% **new-work** cutoff but never
the mutation maximum or expiry. Every lease here is a 30-minute lease.
