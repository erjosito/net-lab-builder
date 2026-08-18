# show-output — Evidence Layout
Niobe · 2026-08-17

Files in this directory are named `<NNN>-<scenario>-<description>.txt` where NNN is a
sequential zero-padded integer. One file per command. Raw CLI and KQL output only.

## Sanitization requirement

All files here must pass `tests/Confirm-Sanitization.ps1` before commit:
- No raw subscription IDs (GUID format matching known sub)
- No raw tenant IDs
- No full JWTs (three-part base64url)
- No `Authorization: Bearer <token>` strings
- No `client_secret` values

## Layout (to be populated post-deployment)

```
001-preflight-afd-profile.txt         ← az afd profile show output
002-preflight-appservice-health.txt   ← curl /health via AFD
003-s1-capability-probe-request.txt   ← curl /debug/request headers
004-s1-capability-probe-kql.txt       ← EdgeActionConsoleLog KQL result
005-s2-missing-token.txt              ← curl /protected no auth header
006-s3-valid-token-protected.txt      ← curl /protected valid token (token redacted)
007-s3-valid-token-admin.txt          ← curl /admin valid token (token redacted)
008-s4-expired-token.txt              ← curl /protected expired token (token redacted)
009-s5-wrong-audience.txt             ← curl /protected wrong-aud token
010-s6-tampered-sig.txt               ← curl /protected tampered token (token redacted)
011-s7-rbac-admin-403.txt             ← curl /admin no-role token → 403
012-s7-rbac-protected-200.txt         ← curl /protected no-role token → 200
013-s8-direct-bypass.txt              ← curl azurewebsites.net direct → 403
014-s9-failopen-edgeonly.txt          ← curl /edge-only X-Test-Fail:1 → 200
015-s9-failopen-protected.txt         ← curl /protected X-Test-Fail:1 → 401/403
016-s9-afd-accesslog-kql.txt          ← edgeActionsStatusCode=503 KQL result
```

Files are created by `tests/Invoke-Validation.ps1`. Do not create manually.
