# Looking-Glass Re-Test — 2026-06-15

**Lab:** vwan-dual-er-symmetric (lab #2)  
**Tested by:** Niobe  
**Date:** 2026-06-15  
**Purpose:** Verify whether the Megaport MCR looking-glass endpoint (`/v2/product/mcr2/{uid}/diagnostics/routes/bgp`) is still broken, as previously confirmed in lab #1 (2026-05).

---

## What We Found

### Auth result
- **Endpoint:** `POST https://api.megaport.com/v2/login`
- **Method:** `Content-Type: application/x-www-form-urlencoded`, `username=<api-key>&password=<api-secret>`
- **HTTP status:** `401 Unauthorized`
- **Body:** `"Invalid email or password. Your account will be locked after 10 failed login attempts."`
- **Attempts made:** 3 (all returned 401; no lockout triggered — well within the 10-attempt limit)

### Looking-glass result
- **MCR1** (`megaport_mcr.mcr1`): **NOT REACHED** — blocked by auth failure
- **MCR2** (`megaport_mcr.mcr2`): **NOT REACHED** — same auth failure

### VXC fallback result
- **gcp_a VXC**: **NOT REACHED** — same auth failure

---

## Verdict

**New failure mode.** In lab #1 (2026-05), Megaport API auth succeeded but the looking-glass endpoint returned `"no endpoint"` / empty body. In lab #2 (2026-06), authentication itself fails with HTTP 401 before the looking-glass endpoint can even be reached. The credentials stored in `platform-secrets-1138` (secrets `megaport-api-key` + `megaport-api-secret`) are rejected by `POST /v2/login` with `Content-Type: application/x-www-form-urlencoded`.

Possible causes (for coordinator to follow up):
1. The Megaport API keys in KV have been rotated or expired since deploy-time.
2. The credential format has changed (the Megaport Terraform provider may authenticate differently from the raw API login endpoint).
3. The credentials are correct but the Megaport account requires a different auth flow (e.g., a new OAuth2 endpoint).

---

## KV ACL Hygiene

| Step | Result |
|------|--------|
| Default action before lift | `Deny` |
| Lift (Allow) | Success |
| Secrets fetched | `megaport-api-key` (26 chars), `megaport-api-secret` (51 chars) |
| Restore to Deny | Success |
| Final confirmed state | `Deny` ✓ |

---

## Files

| File | Contents |
|------|----------|
| `01-mcr1-looking-glass.txt` | Auth failure response; MCR1 looking-glass not reached |
| `02-mcr2-looking-glass.txt` | Auth failure response; MCR2 looking-glass not reached |
| `03-vxc-fallback-gcp-a.txt` | Auth failure response; VXC fallback not reached |
