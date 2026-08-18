# S1 Capability Probe — Evidence (BLOCKED)
Status: **BLOCKED** — Edge Action attachment failed due to REST API validation gap
Date: 2026-08-18

## What Was Attempted

1. Created `eacapabilityprobe` Edge Action (Microsoft.Cdn/EdgeActions, SKU Standard/Standard, location global)
2. Created version v1 (deploymentType=zip, code=base64(handler.js zip), isDefaultVersion=True)
3. Created version v2 (deploymentType=file, code=base64(js), isDefaultVersion=False)
4. Created AFD rule set `rsedgeprobe` on `afd-edge-jwt-lab` profile
5. Created rule `ruleprovedebug` with EdgeAction action (invocationPoint=ClientRequest)
6. Rule consistently fails with: `"Validation failed: The edge action's default version is not in a successful state"`

## Root Cause

The `validationStatus` field on both versions remains `""` (empty string).
The backend requires `validationStatus` to be in a "successful state" before attachment.
Code validation is NOT triggered by any REST API call — only by the portal or VS Code extension UI.

## Activity Log Evidence

```
Microsoft.Cdn/edgeActions/addAttachment/action  Failed  2026-08-18T06:03:48Z
{"error":{"code":"400","message":"Validation failed: The edge action's default version 
is not in a successful state. Ensure the default version has been successfully deployed 
and validated before proceeding."}}
```

## S1 Verdict

**BLOCKED** — Cannot collect `EdgeActionConsoleLog` without successful attachment.
S1-GATE verdict deferred pending manual portal completion of EA validation.

## Recommended Resolution

1. Open Azure Portal → search "Edge Actions"
2. Select `eacapabilityprobe` in `rg-afd-edge-jwt-lab`
3. Go to Settings → Versions → select v1
4. Click "Download code" to verify content, then re-upload via UI
5. Wait up to 10 min for validation to complete (watch validationStatus)
6. Once validated, the existing rule `ruleprovedebug` should succeed on next retry OR:
   - Navigate to AFD profile → Front Door Manager → Routes → rt-api → Manage Edge Actions → Attach

## API Learnings for deploy script

- EdgeAction SKU must be `{"name":"Standard","tier":"Standard"}`
- Location must be `global`
- Name must be alphanumeric only (no hyphens)
- Version code upload: `deploymentType=zip`, body property `code` = base64(zip)
- AFD Rules Engine action: `name=EdgeAction`, `typeName=DeliveryRuleEdgeActionParameters`, `invocationPoint=ClientRequest`
- Attachment requires `validationStatus=Succeeded` — only triggered via portal
