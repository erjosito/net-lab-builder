# evidence — Scenario Evidence Files
Niobe · 2026-08-17

One `.md` file per scenario, populated by `tests/Invoke-Validation.ps1` after a live run.

## Files expected post-deployment

| File | Scenario |
|------|----------|
| `S1-capability-probe.md` | S1 — Capability Probe (GATE) |
| `S2-missing-token.md` | S2 — Missing Token → 401 |
| `S3-valid-token.md` | S3 — Valid Token → 200 |
| `S4-expired-token.md` | S4 — Expired Token → 401 |
| `S5-wrong-audience.md` | S5 — Wrong Audience → 401 |
| `S6-tampered-sig.md` | S6 — Tampered Signature → 401 |
| `S7-rbac.md` | S7 — Role Check → 403/200 |
| `S8-direct-bypass.md` | S8 — Direct Bypass → 403 |
| `S9-fail-open.md` | S9 — Fail-Open / DID (pivotal) |

## Sanitization guarantee

All files here are checked by `tests/Confirm-Sanitization.ps1`. No raw subscription IDs,
tenant IDs, JWTs, or client secrets are permitted. Evidence with any such pattern will
be blocked from commit.
