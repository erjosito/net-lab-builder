# Skill: Moving data across an Entra tenant boundary without secrets

## Context

Applies when compute in tenant A must write to a storage account in tenant B, and the
environment forbids the easy answers:

- Shared keys and SAS disabled (`allowSharedKeyAccess=false`), so RBAC is the only option
- No secrets in code or pipelines, so app passwords are unacceptable
- The two tenants are separate organisations, so no single identity exists in both

The common conclusion is that this is impossible because managed identities are
single-tenant. That conclusion is wrong, and the correct answer is generally available.

## The constraint, stated correctly

A managed identity is a service principal in exactly one tenant. It **cannot** be granted
an RBAC role in another tenant, and no amount of portal searching will find it there.

**But** a managed identity can act as a *federated credential* for a multi-tenant app
registration, and that app can be provisioned into the other tenant and hold RBAC there.
This is workload identity federation, and it is GA, not preview.

Primary source: `https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-config-app-trust-managed-identity`

## The working sequence

Automated in `labs/sql-ltr-backup-migration/deploy/New-CrossTenantDrainIdentity.ps1`
(idempotent, so it doubles as a configuration check).

1. **Source tenant:** create an app registration with `--sign-in-audience AzureADMultipleOrgs`.
   A single-tenant app cannot be provisioned into the other tenant, and the failure appears
   later and confusingly, so check this first.
2. **Source tenant:** add a federated identity credential on that app.
   - `issuer`: `https://login.microsoftonline.com/<SOURCE_TENANT_ID>/v2.0`
   - `subject`: the managed identity's **principalId**, not its clientId
   - `audiences`: `api://AzureADTokenExchange`
3. **Target tenant:** `az ad sp create --id <APP_ID>` to provision the app.
4. **Target tenant:** grant that service principal the data-plane role it needs, for example
   `Storage Blob Data Contributor`, scoped to the account.
5. **Source compute:** request an IMDS token with `resource=api://AzureADTokenExchange` and
   the managed identity's **clientId**.
6. **Source compute:** exchange it at the target tenant:
   `POST https://login.microsoftonline.com/<TARGET_TENANT_ID>/oauth2/v2.0/token`
   with `grant_type=client_credentials`,
   `client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer`,
   `client_assertion=<the IMDS token>`, `scope=https://storage.azure.com/.default`.
7. Use the result as an ordinary bearer token.

Note the two different identifiers in steps 2 and 5. The federated credential is keyed on
**principalId**; the runtime token request uses **clientId**. Swapping them produces a
token request that fails without explaining why.

## Verification that actually catches failure

Receiving a token proves nothing. A token minted for the *source* tenant looks entirely
valid and fails only at the data plane.

- Decode the token and assert `tid` equals the target tenant. `Test-CrossTenantDrainToken.ps1`
  throws when it does not.
- After writing, list the object **from target-tenant context**. A write confirmed only from
  the source side has not been confirmed.

## Limits and prerequisites

- Creating the federated credential needs Application Administrator, Application Developer,
  Cloud Application Administrator, or ownership of the app.
- Provisioning the app and assigning RBAC needs rights in the target tenant. In a real
  migration these are usually different people in different organisations, so treat it as a
  scheduling dependency rather than a command to run.
- Maximum 20 federated identity credentials per application or per user-assigned identity.
- Identity is solved independently of networking. If both ends are private-endpoint only, the
  copying compute still needs network line of sight, implying cross-tenant VNet peering.
  Stage the test with a public endpoint first so an identity failure and a network failure
  cannot be confused.

## Measured

Moving a 1.219 GiB artifact between tenants ran at 0.1655 min/GiB, about 103 MiB/s, within
roughly four percent of the same-tenant transfer rate for the same payload class.
**Budget authorization setup, not throughput.** One data point, so no rate law.

## Dead ends, so nobody re-walks them

- **Transferring the subscription to the other tenant.** Not supported at all for CSP
  subscriptions. Where it is supported it permanently deletes all role assignments and custom
  roles, requires managed identities to be re-created, and requires Key Vault tenant IDs to be
  updated. It is an alternative to this approach, never a fallback partway through one.
  Source: `https://learn.microsoft.com/en-us/azure/role-based-access-control/transfer-subscription`
- **Azure Lighthouse** delegates access to a *retained* subscription. It moves nothing, so it
  does not help when the source is being deleted, but it is the right answer when the source
  survives and only the operators have moved.
- **Cross-Tenant Restore (preview)** covers Azure VM, Azure Files, SQL Server in Azure VM, and
  SAP HANA or ASE in Azure VM. It operates on Recovery Services vault recovery points, so any
  workload whose backups never land in a vault is out of scope, including Azure SQL Database
  and Managed Instance PaaS. "SQL Server in Azure VM" is not Azure SQL PaaS.

## Environment traps that cost real time

- **`Invoke-WebRequest` on binary payloads.** With the progress bar active it is
  pathologically slow: a transfer that takes 12 s with `curl.exe` ran over an hour without
  completing. Set `$ProgressPreference = 'SilentlyContinue'` or use `curl.exe`.
- **It presents as a hung VM, not a slow download.** The stalled call holds the run-command
  extension, so every retry returns `Conflict: Run command extension execution is in progress`.
  Clearing it required a VM restart. Check the extension state before assuming the script logic
  is wrong.
- **`az account set -s` switches tenant context** for `az ad` commands. For ARM calls prefer an
  explicit `--subscription`, because concurrent commands share the CLI's global context and
  will race.
