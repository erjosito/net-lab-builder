## Active Decisions

> Active decisions from all agents (merged by Scribe).
> Previous decisions archived to decisions-archive.md on 2026-09-10 (Tier-2 archive: >50KB threshold, entries >7 days).




---

# Inside the agent's response handler, before returning:
try:
    resp_echo = requests.get(
        "http://echo.onprem.lab/api/echo",
        params={"msg": "hs2-direct-hosted-agent"},
        timeout=5,
    )
    echo_data = resp_echo.json()
except Exception as exc:
    echo_data = {"error": str(exc)}

try:
    resp_ctrl = requests.get(
        "http://ctrl.onprem.lab/api/echo",
        params={"msg": "hs3-ctrl-hosted-agent"},
        timeout=5,
    )
    ctrl_data = resp_ctrl.json()
except Exception as exc:
    ctrl_data = {"error": str(exc)}

# Include echo_data and ctrl_data in the response payload
```

> Use `http://` (not `https://`) for the initial run. This avoids the TLS cert hostname issue until the empirical HTTPS hostname test (TLS finding from original lab lesson 4 was for IP-addressed calls -- hostname calls may behave differently). Switch to `https://` only after Trinity confirms or the empirical run shows it works.

Add `requests` to `requirements.txt`. The scaffold already has `agent-framework` and `azure-ai-projects`.

---

## 7. Authentication Model

**Understand before running locally.**

| Context | Authentication |
|---------|---------------|
| Local run (`F5`) | `DefaultAzureCredential` -- picks up VS Code Azure Account sign-in. No extra config needed. |
| `azd` CLI commands | `azd auth login` -- separate credential from `az login` / VS Code account |
| Deployed agent (Micro VM) | Platform-assigned managed identity (auto-created per agent). By default: can call Foundry model endpoint. Cannot call external resources unless explicitly granted. |
| Calling the deployed agent endpoint | Caller needs **Foundry Agent Consumer** role (or higher) at project scope to invoke the hosted agent endpoint. |

> **Important:** The deployed agent's managed identity does NOT automatically have network access to private VPN routes. The network access comes from being in AgentSubnet -- the Micro VM NIC gets the VNet's effective route table, which includes `172.30.0.0/16` via VPN. No RBAC change is needed for network access; it's routing, not identity. This is confirmed when HS2 succeeds (or OQ3 answers the question empirically).

---

## 8. Local Run and Debug

**Jose does this in VS Code. This is one of the primary advantages of hosted agents.**

1. Make sure you have a virtual environment activated and dependencies installed:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
2. Press **F5** to start the agent in debug mode. VS Code starts the Responses protocol server on port 8088 and opens the **Agent Inspector** automatically.
3. In the Agent Inspector, type a test prompt such as:
   ```
   probe both echo endpoints and return the results
   ```
4. The agent calls your gpt-4o-mini model, then executes the `requests.get(...)` calls. You will see:
   - The model's reasoning in the Agent Inspector.
   - The HTTP call results (or errors, if DNS is not yet deployed or endpoints are unreachable locally).
5. Set a breakpoint on the `requests.get(...)` line and step through it. This is impossible with a prompt agent.

> **Local run limitation:** The `requests.get("http://echo.onprem.lab/...")` call will FAIL locally because your laptop is not inside vnet-foundry and has no VPN route to `172.30.100.4`. This is expected. The local run tests the agent protocol and LLM reasoning. Network connectivity is only tested after deployment (when the Micro VM NIC gets the VNet routing context). Catch the exception and return an informative error message in local mode.

---

## 9. Deploy to Foundry -- VS Code Path

**Jose does this. Resolve OQ4 (McR firewall) first.**

**Pre-deploy check (critical):** The source-ZIP `remote_build` deployment pulls a base image from `mcr.microsoft.com` during provisioning. The current lab NSG blocks all internet egress from AgentSubnet. Confirm with Trinity which path to take (NSG allowlist vs `bundled` mode) BEFORE deploying.

If Trinity approves NSG allowlist (outbound TCP 443 to `mcr.microsoft.com`): apply the NSG patch (Tank will have it staged), THEN deploy.

**Deployment steps:**

1. Open the Command Palette (`Ctrl+Shift+P`).
2. Select **`Foundry Toolkit: Deploy Hosted Agent`**. A deployment webview opens.
3. Fill in:

   | Field | Value |
   |-------|-------|
   | Deployment Method | **Code** (source-ZIP, no ACR needed) |
   | Package Mode | **Remote** (`remote_build` -- Foundry builds the image server-side) |
   | Agent Name | `echo-probe-agent` (auto-populated) |

4. Select **Next**, then review the summary (project endpoint, agent name, runtime).
5. Select **Deploy**.

Foundry packages the source as a ZIP, uploads it, and builds the image. This takes 3--8 minutes. When complete, `echo-probe-agent` appears under **Hosted Agents** in the Foundry Toolkit sidebar.

> **Monitoring deployment progress:** In VS Code Output panel (select `Foundry Toolkit` channel) or run `azd ai agent monitor echo-probe-agent` in the terminal to stream container logs.

---

## 10. First Invocation

**Jose does this -- three ways.**

### Way 1: VS Code Playground tab
1. In the Foundry Toolkit sidebar, expand **Hosted Agents** --> `echo-probe-agent`.
2. Select the **Playground** tab.
3. Send: `probe both echo endpoints and return the results`.
4. Capture the full response. Note whether `echo_data` and `ctrl_data` are populated or show an error.

### Way 2: Terminal (azd)
```bash
azd ai agent invoke echo-probe-agent "probe both echo endpoints"
```

### Way 3: Python SDK from vm-diag (HS5 scenario -- inside the VNet)
```python
# Run via az vm run-command invoke on vm-diag
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

project = AIProjectClient(
    endpoint="https://<account>.services.ai.azure.com/api/projects/<project>",
    credential=DefaultAzureCredential(),
)
client = project.get_openai_client(agent_name="echo-probe-agent")
response = client.responses.create(input="probe both echo endpoints")
print(response.output_text)
```

> **Note:** Way 3 requires the caller to have `Foundry Agent Consumer` (or higher) at project scope. `DefaultAzureCredential` on vm-diag picks up the VM's system-assigned managed identity -- verify the MI has the required role assigned before running.

---

## 11. Reproducing the Two Existing OpenAPI Tools -- Full Options

### Option A: Direct code call (Approach A -- recommended start)

Already covered in Section 6. The agent Python code calls the echo endpoints directly via `requests`. This is HS2 (Micro VM NIC egress). No additional Foundry setup needed.

**Capability difference from prompt agent:** The prompt agent's OpenAPI tool call is made BY THE PLATFORM (data proxy egress, source IP = data proxy IP). The hosted agent's direct code call is made BY YOUR CODE (Micro VM NIC egress, source IP = Micro VM NIC IP). These are network-observable differences.

### Option B: Foundry Toolbox with OpenAPI tool definition (Approach B -- advanced, replicates data proxy path)

This option routes the tool call through the Foundry data proxy, matching the prompt agent's network path. It does NOT replicate the prompt agent's declarative tool config exactly -- you still write code that calls the toolbox endpoint -- but the egress source IP matches.

**Why VS Code UI cannot do this alone:** The Foundry Toolkit VS Code UI does NOT support adding OpenAPI tools to a toolbox (confirmed from toolbox capability table: `Foundry Toolkit: No` for OpenAPI tool). You must use the Python SDK or `azd` CLI.

**How to add an OpenAPI tool via Python SDK (repository prepares the script, Jose runs it):**

```python
# agent-tools/create-echo-toolbox.py (repository stages this; Jose runs it)
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
import json

project = AIProjectClient(
    endpoint="https://<account>.services.ai.azure.com/api/projects/<project>",
    credential=DefaultAzureCredential(),
)

with open("echo-reserved-dns.openapi.json") as f:
    spec = json.load(f)

toolbox_version = project.toolboxes.create_version(
    name="echo-toolbox",
    description="Echo endpoint toolbox for reserved-prefix lab",
    tools=[
        {
            "type": "openapi",
            "name": "echoReserved",
            "spec": spec,
            "auth": {"type": "anonymous"},
            "description": "Call the reserved-prefix echo VM",
        }
    ],
)
print(f"Toolbox: {toolbox_version.name}, version: {toolbox_version.version}")
```

Then in `azure.yaml`, reference the toolbox (Tank prepares this addition to the template). The agent code calls the toolbox via the Responses API, and the platform handles the actual HTTP call through the data proxy.

**Recommendation for this lab:** Start with Option A. It's simpler, teaches the code-call path, and demonstrates the primary network difference. Add Option B when testing HS1 (to prove data proxy path is the same as prompt agent).

---

## 12. Responsibility Split Summary

| Step | Who | Notes |
|------|-----|-------|
| VS Code Foundry Toolkit installation | **Jose** | Cannot be automated |
| Azure sign-in in VS Code | **Jose** | Cannot be automated |
| Select existing Foundry project | **Jose** | Use existing project, not a new one |
| Scaffold hosted agent project | **Jose** (guided by Command Palette steps above) | Repository provides instructions |
| Insert HTTP call logic into `main.py` | **Jose** | Repository provides `echo_probe_patch.py` with the call stubs |
| Local run / F5 debug | **Jose** | Expected to fail on echo calls (no VPN from laptop) |
| NSG decision (McR allowlist or bundled) | **Trinity** decides; **Jose** applies if NSG patch approved | |
| Deploy via VS Code Foundry Toolkit | **Jose** | After Trinity decides on NSG |
| First invocation and evidence capture | **Jose** | Three invocation ways documented above |
| Add OpenAPI Toolbox (Option B) | **Jose** runs the staged script | Repository stages `create-echo-toolbox.py` |

**Repository prepares (Tank stages, unapplied until Phase 4 approval):**
- `agent-tools/hosted-agent-scaffold/main.py` -- Responses protocol scaffold with Foundry model call
- `agent-tools/hosted-agent-scaffold/echo_probe_patch.py` -- HTTP call stubs to insert into main.py
- `agent-tools/hosted-agent-scaffold/requirements.txt` -- dependencies
- `agent-tools/hosted-agent-scaffold/azure.yaml` -- azd manifest template
- `agent-tools/create-echo-toolbox.py` -- Python SDK script to create Toolbox with OpenAPI tools (Option B)
- `echo-reserved-dns.openapi.json`, `echo-control-dns.openapi.json` -- hostname-based OpenAPI docs

---

## 13. Open Questions That the First Run Answers

| Question | How this walkthrough answers it |
|----------|-------------------------------|
| OQ1: Are Micro VM NIC IPs distinguishable from data proxy IPs? | Way 1/2 invocation + tcpdump on vm-onprem-echo; compare `src_ip` in response vs S4 run |
| OQ3: Does Micro VM NIC inherit VPN gateway route propagation? | HTTP call to echo endpoint either succeeds (TCP SYN arrives at vm-onprem-echo) or fails (no SYN) |
| OQ4: Does remote_build deployment work with current NSG? | Deployment step 9 will either succeed or fail with a pull error for mcr.microsoft.com |
| TLS finding: does Foundry validate hostname on HTTPS? | Switch echo URL to `https://echo.onprem.lab` in a second deploy; if it fails, apply cert update |

---

## 14. Authoritative References

| # | URL | Used for |
|---|-----|---------|
| 1 | https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent (vscode pivot) | VS Code toolkit steps 1--7; scaffold, local run, deploy, invoke |
| 2 | https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents | Isolation model; protocol options; per-session Micro VM |
| 3 | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent-code | source-ZIP path; remote_build vs bundled; McR firewall requirement |
| 4 | https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agent-permissions | Role requirements; Foundry Project Manager; agent managed identity |
| 5 | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox | Toolbox creation; OpenAPI tool support matrix (VS Code UI: No); Python SDK approach |
| 6 | https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agents-networking-deep-dive | Micro VM dedicated NIC; data proxy for tool calls; IP allocation |

All fetched on **2026-08-19** (CURRENT_DATETIME 2026-08-19T21:16:59+02:00).

---

# Decision: Cost model BacpacCompression default and throughput constants
**Author:** Tank
**Filed:** 2026-09-10T09:19:52Z
**Status:** Proposed - requires Oracle/Jose sign-off before updating the cost model workbook

## Summary

The lab's first live run measured the two unverified parameters that dominate cost model
accuracy. This decision captures what was found and recommends how to update the model.

## Findings

### BACPAC compression ratio

| Data shape | Source GB | Artifact GB | Ratio |
|---|---|---|---|
| Mixed (realistic blend, 75% repetitive text + 25% random) | 5.0781 | 1.269 | 4.00x |
| Mixed | 1.0781 | 0.254 | 4.25x |
| Mixed | 20.2031 | 5.076 | 3.98x |
| Compressible (repeated bytes) | 5.0781 | 0.035 | 145.3x |
| Random (CRYPT_GEN_RANDOM, incompressible) | 5.0781 | 4.903 | 1.04x |

The default of 4.0x is validated for realistic/mixed data. The range across data shapes
is 1.04x to 145.3x, a 140x spread. A single point value is dangerous for budgeting.

### Recommendation: replace single-point default with a range

Do NOT update the workbook to a single new default. Instead:
- Keep `BacpacCompression = 4.0` as the mixed/typical-data default.
- Document the range: 1.04x (incompressible, e.g. pre-compressed or binary data) to 145x
  (highly repetitive text).
- Add a `WorstCase` scenario column using 1.04x, because the storage term dominates cost
  and an underestimate here is the single largest source of error.
- Note: the existing README already states "a dry run of the fitter against synthetic
  ground truth reported a compression range of 1.02x to 33x". The 145x upper bound here
  is higher (the seed data used a pure 8-byte repeat pattern, which is more compressible
  than most real data). Real mixed business data should be close to 4x.

### Export throughput

| Measurement | Default (estimated) | Measured | Method |
|---|---|---|---|
| ExportMinPerGb | 1.20 | 0.159 | sqlpackage, private endpoint, D4s_v5, same region |
| ExportFixedMin | 0.00 | 0.36 | same |

The estimated 1.20 was likely based on a slower network path (public internet) or a
smaller VM. The measured 0.159 is 7.5x faster. For the compute term in the cost model
(which is ~2% of total cost anyway), this difference is financially immaterial. Update
the constants so the estimate is not wildly wrong, but note the context dependency.

### LTR + serverless auto-pause: incompatible

LTR policies cannot be set on serverless databases with auto-pause enabled. The README
assumed they could coexist to reduce wait-phase cost. This assumption is false.
Consequence: during the LTR wait phase, the databases will accumulate compute cost
(not just storage). At GP_S_Gen5_4 minimum (0.5 vCores), cost is ~$0.076/hour/DB for
5 databases = ~$0.38/hour = ~$64 over 7 days. Still modest compared to the ~$110 MI
option, but not free as the README implied.

## Proposed updates to cost model workbook

1. Add a `BacpacCompressionRange` row showing 1.04x (worst), 4.0x (typical), 145x (best).
2. Add a "Worst case" scenario column using 1.04x.
3. Update `ExportMinPerGb` from 1.20 to 0.16, noting the measurement context.
4. Add a footnote on LTR + auto-pause incompatibility and its cost implication.

---

# Oracle note: MI BACKUP TO URL path proven

Date: 2026-09-10

## Decision input

The Managed Instance drain path should be treated as proven, not speculative. The README
now removes the MI `BACKUP TO URL` unverified markers and states that a user-assigned
managed identity can write a native `.bak` to storage with shared-key access disabled and
public network access disabled, over a private endpoint.

## Process correction

The service-managed TDE remediation is not just "disable TDE, then backup". The required
sequence on the staged copy is:

1. `ALTER DATABASE ... SET ENCRYPTION OFF`
2. Wait until `sys.dm_database_encryption_keys` reports `encryption_state = 1`
3. Run `DROP DATABASE ENCRYPTION KEY;` inside the database
4. Run `BACKUP ... TO URL WITH COPY_ONLY, COMPRESSION`

The key operational trap is that `encryption_state = 1` is not sufficient. The backup still
fails with Msg 41938 until the DEK is dropped. Msg 41922 and Msg 41938 are now treated as
empirical lab findings.

## Roadmap judgement

The SQL Database managed export roadmap is promising but does not change the current
recommendation. Import/export over Private Link addresses the public endpoint blocker.
Import/export with managed identity addresses the shared-key blocker. The environment has
both blockers simultaneously, and the combined preview path is not documented as tested.
For a hard compliance drain deadline, use client-side `sqlpackage` from in-VNet compute
unless both features reach GA and the combined path is documented before execution.

---

# Decision: MI BACKUP TO URL managed identity is confirmed GA for Azure SQL Managed Instance PaaS

**Date:** 2026-09-10
**Author:** Oracle (roadmap scan)
**Status:** Confirmed finding, recommended for integration

## Decision

The last load-bearing unverified assumption in `labs/sql-ltr-backup-migration/README.md` is now resolved by primary-source Microsoft Learn documentation.

`CREATE CREDENTIAL ... WITH IDENTITY = 'Managed Identity'` followed by `BACKUP DATABASE ... TO URL ... WITH COPY_ONLY` is documented as a supported, non-preview capability for Azure SQL Managed Instance (PaaS), not just for SQL Server on Azure VMs or Arc-enabled SQL Server.

## Evidence

Two independent Microsoft Learn pages, scoped to Azure SQL Managed Instance, confirm this:

1. `https://learn.microsoft.com/en-us/azure/azure-sql/managed-instance/restore-database-to-sql-server` (page dated 2025-09-15): includes a "Managed identity" tab under "Take a backup on SQL Managed Instance" with explicit T-SQL showing `CREATE CREDENTIAL ... WITH IDENTITY = 'MANAGED IDENTITY'` and `BACKUP DATABASE ... WITH COPY_ONLY`.

2. `https://learn.microsoft.com/en-us/azure/azure-sql/managed-instance/transact-sql-tsql-differences-sql-server` (last updated 2026-07-16): states "you can authenticate using either managed identity or shared access signature (SAS)" for backup/restore to Azure storage, and under Credential: "Managed identity, Azure Key Vault and SHARED ACCESS SIGNATURE identities are supported."

## What this means for the drain process

The governance constraint `allowSharedKeyAccess=false` on the destination storage account is no longer a blocker for the MI drain path. The drain can authenticate using the MI's system-assigned or user-assigned managed identity (with `Storage Blob Data Contributor` RBAC on the storage account) instead of SAS.

The README caveat "UNVERIFIED: it is not confirmed to work for Azure SQL Managed Instance BACKUP TO URL. Do not treat it as a working solution until tested." should be updated to reflect this confirmation, with the caveat that empirical testing in the specific governed environment is still advisable before the production drain.

## Action for Jose

The README caveats section (under "Shared-key access may be disabled on storage accounts") should be updated to:
- Remove the "UNVERIFIED" label
- State that managed identity is documented as GA for MI BACKUP TO URL
- Retain a note recommending one integration test in the actual governed environment before starting the production drain, since documentation confirmation is not the same as empirical test evidence in a specific tenant

See `labs/sql-ltr-backup-migration/research/roadmap-scan.md` for the full scan with source URLs.

---

# Tank decision inbox: MI BACKUP TO URL with Managed Identity

Date: 2026-09-10T12:23:44+02:00

**Verdict A, credential syntax: SUPPORTED.**

Azure SQL Managed Instance accepted:

```sql
CREATE CREDENTIAL [https://ltrlab552754sa.blob.core.windows.net/mi-backups]
  WITH IDENTITY = 'Managed Identity';
```

Evidence: `sys.credentials` returned `credential_identity = Managed Identity`.

**Verdict B, end-to-end backup to storage using that identity: SUPPORTED, after service-managed TDE is disabled and the database encryption key is dropped.**

Evidence:

- Storage account `ltrlab552754sa` has `allowSharedKeyAccess=false` and `publicNetworkAccess=Disabled`.
- UAMI principalId `6ae8e9fe-6b1a-437f-bf94-83430a391337` already had `Storage Blob Data Contributor` on the storage account.
- From `ltrlab-vm`, `ltrlab552754sa.blob.core.windows.net` resolves to privatelink IP `10.70.1.5`; TCP 443 succeeds.
- Container `mi-backups` was created from inside the VNet using the VM UAMI and a storage OAuth token from IMDS.
- `BACKUP DATABASE [mitest] TO URL = 'https://ltrlab552754sa.blob.core.windows.net/mi-backups/mitest.bak' WITH COPY_ONLY, COMPRESSION, STATS = 10` succeeded after TDE remediation.
- `RESTORE HEADERONLY` succeeded and reported `Compressed : 1`, `CompressedBackupSize : 11624952`, and `CompressionAlgorithm : MS_XPRESS`.
- `RESTORE VERIFYONLY` succeeded with `The backup set on file 1 is valid.`
- Blob REST from inside the VNet confirmed `mitest.bak` exists with `Content-Length=11927552`.

**Separate service-managed TDE caveat: CONFIRMED.**

The initial backup with service-managed TDE still enabled failed with Msg 41922:

```text
The backup operation for a database with service-managed transparent data encryption is not supported on SQL Database Managed Instance.
BACKUP DATABASE is terminating abnormally.
 Msg 41922, Level 16, State 1, Procedure , Line 1.
```

After `ALTER DATABASE [mitest] SET ENCRYPTION OFF`, Managed Instance still required `DROP DATABASE ENCRYPTION KEY`; the first retry failed with Msg 41938:

```text
BACKUP WITH COPY_ONLY cannot be performed since database encryption key for the database 'mitest' still exists. Retry command after you drop database encryption key.
BACKUP DATABASE is terminating abnormally.
 Msg 41938, Level 16, State 1, Procedure , Line 1.
```

Decision:

Keep the MI native backup path in the lab, but document the two-step TDE remediation precisely for staged copies: `ALTER DATABASE ... SET ENCRYPTION OFF`, poll until `encryption_state=1` or the DMV row is gone, then `DROP DATABASE ENCRYPTION KEY` before `BACKUP ... WITH COPY_ONLY`.

---

# Tank decision note: SQL MI provisioning network intent policy

**Date:** 2026-09-10

**Context:** `ltrlab552754-mi` provisioning was started in `rg-ltr-lab` with a
dedicated delegated subnet, empty route table, and default-only NSG.

**Decision:** Treat the MI route table and NSG as create-before-MI resources only.
Before `az sql mi create`, they must be empty/default and associated to the delegated
subnet. After MI provisioning starts, do not try to converge them back to empty/default.
Use read-only verification instead.

**Reason:** Azure SQL Managed Instance service-aided subnet configuration creates a
service association link plus Microsoft.Sql-managedInstances_UseOnly routes and NSG
rules. A later attempt to run `az network route-table create` over the existing route
table failed with `ConflictWithNetworkIntentPolicy` because it would have removed the
network intent policy routes.

**Reusable implication:** Idempotent deploy scripts should first check whether the MI
already exists. If it does, report current state and verify associations without
rewriting the subnet, route table, or NSG.




---

# Scribe merge note: sql-ltr-backup-migration inbox backlog (merged 2026-09-11)

**Merged by:** Scribe. **Requested by:** Jose.

Three inbox entries written around 2026-09-10 and 2026-09-11 were merged late and are
appended below verbatim, in the order they were written. Read them chronologically;
they are a sequence, not a contradiction:

1. `oracle-restore-proven.md` (2026-09-10) states that links 3 through 5 of the drain
   chain (extract a portable artifact, store it, later restore or import it) are proven,
   and that links 1 and 2 (an LTR backup exists, restore that LTR backup) were still
   unverified at the time of writing because no LTR backup had existed yet.
2. `tank-mi-timing.md` (2026-09-10T13:20) records the Managed Instance TDE decryption
   and PITR proxy timings, plus the artifact consumability update for both the MI `.bak`
   and the SQL Database BACPAC.
3. `tank-ltr-restore-invalidation.md` (2026-09-11), written one day later, records that
   the `az sql db ltr-backup restore` path did subsequently execute end to end, which
   closes Oracle's link 2 as a mechanism, while the restored databases were empty, so the
   timing measurement itself was discarded. Oracle's entry is preserved as written and has
   not been back-edited.

Standing conclusion for this lab is unchanged: LTR backups cannot be moved between servers
or subscriptions, so the only route is a drain (restore the LTR backup to a temporary
database, extract a portable artifact, write it to a storage account, delete the temporary
copy).

# Oracle decision: artifact restore proof is now first-class evidence

Date: 2026-09-10

## Decision

Treat artifact consumption as proven for both halves of `sql-ltr-backup-migration`, and
separate it explicitly from `RESTORE VERIFYONLY` and from LTR restore.

## Rationale

Jose challenged whether the lab had verified a restore or only an export. The answer before
the second round was only export plus `.bak` readability. The second round restored or
imported real archive artifacts into new databases and verified row counts plus aggregate
checksums against the sources.

## Evidence folded into README

| Path | Result |
|---|---|
| Managed Instance `.bak` | Restored into a new database in 30.5 s. Row count 130000 matched, checksum -1557385128 matched, ROWS allocation 1056 MiB matched. |
| SQL Database BACPAC | Imported with client-side sqlpackage in 198.6 s. Row count 131072 matched, checksum 12517530 matched, ROWS allocation 1104 MiB matched. |

The SQL Database LOG allocation differed after import, 1224 MiB source vs 472 MiB imported.
That is expected after a logical import and is not data loss.

## Boundary kept explicit

The production chain is:

1. LTR backup exists.
2. Restore the LTR backup.
3. Extract a portable artifact.
4. Store the artifact.
5. Later, restore or import the artifact.

Links 3 through 5 are now proven by the lab. Links 1 and 2 remain unverified and unmeasured
because no LTR backup has existed yet.

## Related documentation choices

- Keep R-squared null on the MI two-point timing fits because any two-point fit would be
  tautological.
- State that the TDE decryption slope is fitted on ROWS file GiB from `sys.database_files`.
  Using total file footprint including LOG changes the apparent rate by nearly 2x.
- Document Msg 41901 for `RESTORE ... WITH STATS` on Managed Instance.
- Document MI storage headroom as a hard planning constraint.
- Do not publish the 347.8 s BACPAC download as a throughput planning rate. It was a
  single-stream lab artifact; production should use `azcopy` or another parallel-capable
  transfer tool.

---

# Tank MI timing measurements

Date: 2026-09-10T13:20:00+02:00

## Decision input

The Managed Instance was kept running and used to close two timing gaps immediately, while avoiding the multi-day wait for an actual LTR backup.

## Observations

- LTR hedge policy was set on `mitest` at 2026-09-10T11:02:07Z with `az sql midb ltr-policy set -g rg-ltr-lab --mi ltrlab552754-mi -n mitest --weekly-retention P12W`.
- Immediate LTR backup list check at 2026-09-10T11:02:34Z returned no backups.
- TDE decryption was measured on service-managed TDE calibration databases seeded with mixed repeated text and `CRYPT_GEN_RANDOM` bytes.
- `mi_tde_1gb_20260910`: 1.0313 GiB ROWS file, decryption 25.716 s, DEK drop 0.047 s, compressed backup 10.741 s, blob 250.5625 MiB.
- `mi_tde_5gb_20260910`: 5.0156 GiB ROWS file, decryption 80.701 s, DEK drop 0.094 s, compressed backup 51.986 s, blob 1247.9375 MiB.
- Decryption fit is a two-point slope only: fixed 0.1914 min, 0.2300 min/GiB, R-squared null because a two-point R-squared would overstate confidence.
- Same-instance PITR restore of `mitest` to `mitest_pitr_proxy_20260910` completed in 55.549 s. This is a PROXY only, not a measured LTR restore duration.

## Artifacts

- `labs/sql-ltr-backup-migration/research/mi-timing-measurements.md`
- `labs/sql-ltr-backup-migration/deploy/mi-calibrated-parameters.json`

## Open items

Managed Instance LTR backup availability delay and LTR restore duration remain unmeasured until an actual LTR backup exists.

## 2026-09-10 artifact consumability update

- Managed Instance `.bak` consumption is now proven with data intact.
- Restored `mi_tde_1gb_20260910-20260910T110634Z.bak` to `mi_tde_1gb_restored` in 30.503 s.
- Source and restored `dbo.Payload` both had 130000 rows, checksum -1557385128, 1056 MiB ROWS file, 88 MiB LOG file.
- Initial MI restore attempt with `WITH STATS = 10` failed before artifact consumption with Msg 41901 because MI does not support that restore option. The same artifact restored successfully without `STATS`.
- SQL Database BACPAC consumption is now proven with data intact.
- Imported existing `ltrlab552754-calib-1gb.bacpac` into `ltrlab552754-calib-1gb-imported` using `C:\tools\sqlpackage\sqlpackage.exe` from `ltrlab-vm` with an Entra token from IMDS.
- BACPAC download from private blob to VM took 347.754 s. sqlpackage import took 198.644 s.
- Source and imported `dbo.LabPayload` both had 131072 rows, checksum 12517530, and 1104 MiB ROWS file. LOG allocation differed, 1224 MiB source vs 472 MiB imported, expected after import.
- Three facts remain separate: `RESTORE VERIFYONLY` passed for the `.bak`; both portable artifact types now restore or import into working databases with data intact; LTR restore remains unmeasured and unverified until an LTR backup exists.

---

### 2026-09-11: LTR restore mechanism proven, but RestoreMinPerGb stays null
**By:** Tank (requested by Jose)
**What:** All three LTR backups restored successfully into new databases, proving the
`az sql db ltr-backup restore` path end to end for the first time. However all three
restored databases were verified EMPTY (zero tables, against source row counts
131072 / 655360 / 2621440 which all matched). The LTR backups are copies of the first
automatic PITR full backup, taken before seeding completed. `RestoreMinPerGb` and
`RestoreRSquared` remain null; a provisional fit of 3.860445 + 0.037921*GB with
R-squared 0.468043 was computed and DISCARDED as an artifact.
**Why:** A restore can succeed, report Online, and produce a plausible linear fit while
carrying no data. New standing gate: any future restore timing run must verify restored
row counts against the source before a slope is fitted. A valid measurement needs an
LTR backup taken AFTER seeding; the existing three can never provide one.

---

# Decision: Cross-tenant drain is possible, and the CSP subscription is the root cause

Date: 2026-09-11

**By:** Jose (via Copilot), recorded by Scribe. **Status:** accepted. Reframes the premise
of `labs/sql-ltr-backup-migration/`.

## Reframing (the headline)

The drain exists because the SUBSCRIPTION cannot move, not because LTR backups are
inherently unmovable. This is the single most important correction to the lab's framing.

Customer context: an old CSP subscription in one Entra tenant, moving to a new subscription
in a DIFFERENT tenant.

**Root cause (DOCUMENTED, quoted from Microsoft Learn):**

> For Azure Cloud Solution Providers (CSP) subscriptions, changing the Microsoft Entra
> directory for the subscription isn't supported.

That is why the databases had to be re-created. The subscription itself is immovable across
directories, so every resource bound to that subscription has to be drained and rebuilt
rather than transferred.

## Mechanism (EMPIRICALLY VERIFIED in this lab)

A managed identity cannot hold cross-tenant RBAC directly. It CAN, however, act as a
federated credential for a multi-tenant app registration provisioned into the target tenant.
This is GA, not preview.

Identifier asymmetry, worth calling out because it is an easy misconfiguration:

- The federated identity credential is configured with the UAMI **principalId**.
- The runtime token request uses the UAMI **clientId**.

These are different values and they are not interchangeable.

## Measurement (EMPIRICALLY VERIFIED in this lab)

- 1.219 GiB artifact moved cross-tenant in 12.1 seconds.
- 0.1655 min/GiB, approximately 103 MiB/s.
- MD5 identical on both sides. Verified independently from the TARGET tenant rather than
  trusting the source VM's self-report.
- Within roughly 4 percent of the same-tenant `BACKUP TO URL` rate. Conclusion: the tenant
  boundary costs authorization setup, not throughput.
- One data point only, so R-squared is deliberately null. Do not present this as a fitted
  throughput model.

## Superseded claim (recorded deliberately)

A previous assertion in this session held that because managed identity is single-tenant,
the drain path "stops at the tenant boundary." **That claim was wrong** and was corrected in
the repo and to the user. It is recorded here rather than quietly deleted because a recalled
limitation is a hypothesis, not a fact, and the distinction is the reusable lesson.

## Dead ends (do not re-walk)

| Path | Why it fails |
|---|---|
| CSP subscription directory transfer | Not supported at all for CSP subscriptions. |
| Azure Lighthouse | Grants cross-tenant access; moves nothing. Delegation is not migration. |
| Backup Cross-Tenant Restore | Covers "SQL Server in Azure VM" but NOT Azure SQL PaaS. It operates on Recovery Services vault recovery points, and PaaS LTR backups never land in a vault. |

## Teardown addendum (2026-09-11): the cross-tenant footprint is invisible to RG deletion

The teardown experiment surfaced a cleanup gap specific to this mechanism. The app
registration, its federated identity credential, and the target-tenant service principal are
DIRECTORY objects. They live outside every resource group, so deleting both resource groups
left a working cross-tenant trust standing until those objects were removed explicitly.

Treat the cross-tenant trust as a separate teardown step, never as something an infrastructure
cleanup will sweep up. `Remove-LtrLab.ps1` now covers this, commit `f3c2911`.

---

# Decision: LTR backup binding scope is the subscription, not the server

Date: 2026-09-11

**By:** Jose (via Copilot), recorded by Scribe. **Status:** accepted and now LAB-PROVEN.
Originally written 2026-09-11 with the teardown verification still in progress; the
teardown result was appended the same day (see "Teardown experiment" below).

## Documented behaviour (quoted from Microsoft Learn, long-term-retention-overview)

> If you delete a logical server or a SQL managed instance, all databases on that server or
> managed instance are also deleted... However, if you had configured LTR for a database, LTR
> backups aren't deleted and can be used to restore databases to a different server or
> managed instance in the same subscription.

The binding scope is therefore the SUBSCRIPTION. The server is not the anchor; deleting it
does not take the LTR backups with it.

## Also verified

LTR backups are enumerable by LOCATION ALONE, with no `--server` argument. That is the
mechanism by which you find backups orphaned by a deleted server.

## Practical consequences

1. Deleting a resource group does NOT clean up LTR backups. They keep billing for the full
   retention period and must be deleted explicitly.
2. Conversely, this is exactly why the drain is mandatory when the SUBSCRIPTION itself is
   going away. Within a subscription the backups survive a server deletion; across
   subscriptions they do not survive at all.

## Teardown experiment (EMPIRICALLY VERIFIED, 2026-09-11)

Run as a controlled experiment by Jose. This fills the slot left open above; the documented
behaviour is now lab-proven.

Sequence:

1. Recorded the inventory before touching anything: 3 Azure SQL Database LTR backups and
   1 Managed Instance LTR backup.
2. Deleted the WHOLE resource group, containing the logical server, the managed instance,
   its virtual cluster, a VM, storage, the VNet and private endpoints. Elapsed time about
   16 minutes, dominated by the managed instance and the virtual cluster.
3. Confirmed the resource group was gone and that `az sql server list` returned zero lab
   servers.
4. Re-enumerated by location. **ALL FOUR LTR BACKUPS SURVIVED**, with unchanged
   `backupTime` and unchanged expiry of 2026-12-03, still naming a server and a managed
   instance that no longer exist.
5. Deleted all four explicitly, then verified the count is zero for both SQL Database and
   Managed Instance.

Three findings newly established by this run:

- **MI-side LTR survival is proven for the first time.** This lab had previously shown
  survival only for Azure SQL Database after DATABASE deletion. Survival after deletion of
  the server, the managed instance, and the entire resource group is new, and the Managed
  Instance case had never been tested at all.
- **Location-only enumeration is the orphan handle.**
  `az sql db ltr-backup list --location <loc> --database-state All` and the `midb`
  equivalent both work with no `--server` argument. Once the server is deleted, this is the
  ONLY way to find the backups.
- **The cleanup trap is confirmed, not theoretical.** Resource group deletion does not stop
  LTR billing. The four backups stayed billable to their full 2026-12-03 expiry and required
  explicit deletion.

## Evidence status

- The quoted binding-scope behaviour and the location-only enumeration are **DOCUMENTED**
  and now also **EMPIRICALLY VERIFIED** by the teardown experiment above.
- The billing and persistence consequence is **LAB-PROVEN**, no longer documentation only.
- Not tested: whether a surviving orphaned backup still RESTORES into a fresh server. The
  backups were enumerated and then deleted, not restored. Do not claim restorability of an
  orphaned backup on the strength of this run.

## Source-quality note

An AI web-search summary confidently asserted the OPPOSITE, that deleting the server
destroys the LTR backups. The primary Microsoft Learn source contradicted it. Recorded as a
standing reminder: a search summary is not a primary source, and confident phrasing is not
evidence.

---

# Decision: RestoreMinPerGb is permanently unresolved for this lab (abandoned, not pending)

Date: 2026-09-11

**By:** Jose (via Copilot), recorded by Scribe. **Status:** ABANDONED. Closes the open item
carried by the 2026-09-11 Tank entry "LTR restore mechanism proven, but RestoreMinPerGb
stays null."

## What

`RestoreMinPerGb` and `RestoreRSquared` are recorded as PERMANENTLY UNRESOLVED for
`labs/sql-ltr-backup-migration/`. They are not a pending task and must not be carried forward
as one.

## Why

- A valid LTR restore slope requires an LTR backup taken AFTER seeding. The three existing
  LTR backups were copies of the first automatic PITR full backup, taken before seeding
  completed, which is why the restores came back with zero rows.
- The three post-seed calibration databases never received an LTR backup within about
  5 hours of observation. Documentation allows up to seven days for an LTR backup to appear,
  so this is not an anomaly; the wait was simply longer than the lab window.
- The teardown experiment deleted the server, which ended the experiment. No further LTR
  backup can ever be produced from those databases.

## Consequence

The measurement is closed as abandoned. Anyone reviving it must stand up a new environment,
seed first, then wait out the LTR backup availability delay (up to seven days) before
attempting a timing run. The standing gate from the Tank entry still applies: verify restored
row counts against the source before fitting any slope.
