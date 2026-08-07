# Capture 00 — Subscription/RG context (read-only)

**Captured by:** Tank · 2026-08-05T16:00:43+02:00
**Purpose:** Confirm the shared live resource group and its tags before any Poland-only deletion
preview. No mutating command was run.
**Sanitization:** Subscription ID and tenant ID redacted to `<SUBSCRIPTION_ID>` / `<TENANT_ID>`.

## Command 1
```bash
az account show --query "{name:name, id:id, tenantId:tenantId}" -o json
```
### Output (sanitized)
```json
{
  "name": "<REDACTED_SUBSCRIPTION_NAME>",
  "id": "<SUBSCRIPTION_ID>",
  "tenantId": "<TENANT_ID>"
}
```

## Command 2
```bash
az group show -n rg-dual-hub-hubless-region-ars-lab3d001 --query "{name:name, location:location, tags:tags}" -o json
```
### Output (sanitized)
```json
{
  "name": "rg-dual-hub-hubless-region-ars-lab3d001",
  "location": "swedencentral",
  "tags": {
    "approval_time": "2026-08-03T15:39:35+02:00",
    "approved_by": "jose",
    "correlation_id": "lab3d001",
    "ephemeral": "true",
    "lab": "true",
    "lab_name": "dual-hub-hubless-region-ars",
    "owner": "jose"
  }
}
```

**Finding:** RG matches deploy-log.md / manifest.md exactly. No mutating flags used.
