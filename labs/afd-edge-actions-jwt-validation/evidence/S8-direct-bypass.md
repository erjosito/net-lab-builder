# S8 — Direct Origin Bypass Evidence
Niobe · 2026-08-18 · **VERDICT: PASS**

## Test

Direct HTTP requests to `https://app-edge-jwt-lab.azurewebsites.net` (bypassing AFD entirely).

## Results

| Path | HTTP Status | Response | X-Azure-Ref |
|------|-------------|----------|-------------|
| `/health` (direct) | **403** | `<!DOCTYPE html>... Web App - Unavailable` (App Service access restriction page) | absent (not through AFD) |
| `/protected` (direct) | **403** | same | absent |

## Analysis

App Service Access Restrictions are active:
- Rule 100: `AzureFrontDoor.Backend + X-FD-HealthProbe=1` → Allow
- Rule 200: `AzureFrontDoor.Backend + X-Azure-FDID=549954ba-<FDID_TRUNCATED>` → Allow
- Implicit deny-all

A direct caller:
1. Does NOT come from the `AzureFrontDoor.Backend` IP range
2. Does NOT carry `X-Azure-FDID`

Both conditions on rule 200 fail → request denied.

Health probe path (rule 100) also fails — the direct caller doesn't carry `X-FD-HealthProbe: 1` sent only by AFD's internal health probe mechanism.

## Security conclusion

Origin hardening is effective. **No critical finding NIOBE-CRIT-002.** Direct bypass is blocked.

Note: App Service echoes "Ip Forbidden" for IP-based deny. This means the access restriction is evaluated at the App Service front-end tier, confirming the ARM-native enforcement (not application code).

## References

- `manifest.md §4.4` — access restriction two-rule pattern
- `design.md §0 (C1, C2)` — corrections
- `deploy/deploy-log.md` — access restrictions configured via ARM REST PATCH (CLI blocked duplicate ServiceTag)
- `show-output/003-HTTP-requests-evidence.txt` — raw HTTP results
