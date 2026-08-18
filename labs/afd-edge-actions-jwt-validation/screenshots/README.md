# screenshots — Evidence Layout
Niobe · 2026-08-17

Portal screenshots are best-effort. CLI/KQL evidence in `show-output/` and `evidence/`
is authoritative for pass/fail determinations.

## Sanitization

Screenshots are images and are not scanned by the text sanitizer. However:
- Do not include any browser tab, address bar, or portal UI element that displays a raw
  subscription ID, tenant ID, or client secret in visible text.
- Crop or blur any such elements before saving.
- File names must not contain GUIDs.

## Naming convention

```
<scenario>-<description>-<timestamp>.png
```

Example:
```
s1-edge-action-console-log-portal.png
s3-afd-access-log-200-valid-token.png
s8-appservice-access-restriction-403.png
s9-afd-accesslog-503-edgeaction-status.png
```

## Expected screenshots (to be populated post-deployment)

| File | What to capture |
|------|----------------|
| `s1-capability-probe-kql-result.png` | Log Analytics KQL result showing PROBE lines |
| `s1-edge-action-list.png` | AFD portal → Edge Actions tab showing ea-capability-probe deployed |
| `s3-afd-access-log-200.png` | AFD access log showing 200 for valid token request |
| `s6-sig-fail-kql.png` | EdgeActionConsoleLog showing SIG_FAIL for tampered token |
| `s8-access-restriction-rules.png` | App Service → Networking → Access Restrictions showing rule 100 + 200 |
| `s9-afd-accesslog-503.png` | AFD access log showing edgeActionsStatusCode=503 |
