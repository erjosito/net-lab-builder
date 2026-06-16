# WSL gcloud validation — 2026-06-15

**Validator:** Niobe (test/validation engineer)  
**Environment:** WSL (Ubuntu 24.04) on Windows, gcloud CLI v552.0.0  
**Project:** `gcp-vwan-symm-103167` (Design B Phase 1, post-tank-3 deploy)  
**Lab resources:** vpc-vwan-symm-a-103167, router-vwan-symm-a (eu-w3), cr-vwan-symm-onprem-b (eu-w4)

## Summary

- **Commands tested:** 11 gcloud commands from §8 (Cloud Router) and §9 (Interconnect + VPC routes)
- **🟢 Works as-is:** 8 commands (only placeholders needed)
- **🟡 Works with fix:** 2 commands (placeholder standardization)
- **🔴 Fails/Deprecated:** 1 command (`get-effective-firewalls` subcommand doesn't exist; replaced)
- **Critical bug fixed:** §9.3 hardcoded `vpc-onprem` → `<YOUR_VPC>` placeholder

## Validation results

| § | Command (short) | Status | Evidence file | Notes |
|---|---|---|---|---|
| 8.1 | `routers list --filter=region` | 🟢 | 00-discovery.txt, 01-validation-results.txt | Lists 2 routers in Design B; GLOBAL routing confirmed |
| 8.2 | `routers describe` (config + peers) | 🟢 | 01-validation-results.txt | Router A config: ASN 16550, advertises 10.50.1-2.0/24 |
| 8.3 | `routers get-status` (best routes) | 🟢 | 01-validation-results.txt | 2 dynamic routes via 169.254.159.194 |
| 8.4 | `routers get-status \| jq` (learned routes) | 🟢 | 01-validation-results.txt | Empty output is correct (no learned routes yet) |
| 8.5 | `routers get-status` (BGP peer status) | 🟢 | 01-validation-results.txt | Peer UP, Established, 8 routes known |
| 8.6 | `routers get-status` (routes advertised to peer) | 🟡 | 01-validation-results.txt | Works; placeholder `<peer-name>` standardized to `<YOUR_BGP_PEER_NAME>` |
| 9.1 | `interconnects attachments list` | 🟢 | 01-validation-results.txt | 2 ACTIVE attachments (A + B-new) |
| 9.2 | `interconnects attachments describe` | 🟡 | 01-validation-results.txt | Works; placeholder `<att-name>` → `<YOUR_ATTACHMENT_NAME>` |
| 9.3 | `routes list --filter=network` | 🔴→🟢 | **01-validation-results.txt** | **CRITICAL FIX:** Hardcoded `vpc-onprem` replaced with `<YOUR_VPC>`. Original returned 0 rows; fixed returns 3 VPC routes (default IGW + 2 subnets) |
| 9.4 | `instances get-effective-firewalls` | 🔴 | 01-validation-results.txt | **DEPRECATED:** Subcommand doesn't exist in gcloud 552.0.0. Replaced with `firewall-rules list --filter=network`. New command works, returns 1 rule (allow IAP). |
| 9-gotcha | `networks describe` (routing mode) | 🟢 | 01-validation-results.txt | GLOBAL routing confirmed required for cross-region propagation |

## Placeholder convention adopted

Document uses **`<YOUR_...>` convention** (e.g., `<YOUR_VPC>`, `<YOUR_BGP_PEER_NAME>`, `<YOUR_ATTACHMENT_NAME>`):
- Angle brackets make placeholders visually obvious during copy-paste
- ALL-CAPS style prevents accidental use of literal names
- Consistent and pedagogically clear for blog readers

Pre-defined environment variables (`$ROUTER_A`, `$REGION_A`) are documented in the Conventions section.

## Linux doc changes applied

**File:** `docs/troubleshooting-commands-linux.md`

1. **Lines 9–33:** Enhanced Conventions section with explicit placeholder convention documentation
2. **Line 164:** Changed `<peer-name>` → `<YOUR_BGP_PEER_NAME>` (standardization)
3. **Line 179:** Changed `<att-name>` → `<YOUR_ATTACHMENT_NAME>` (standardization)
4. **Line 180:** **CRITICAL FIX** — Changed hardcoded `vpc-onprem` → `<YOUR_VPC>`
5. **Line 181:** Replaced deprecated `get-effective-firewalls` with `firewall-rules list --filter="network:<YOUR_VPC>"`
6. **Line 183:** Updated Gotcha example to use `<YOUR_VPC>` placeholder

## Validation callouts added to doc

Each tested command now includes an HTML comment validation callout:
```html
<!-- Validated 2026-06-15 WSL: works (evidence: 01-validation-results.txt) -->
```
or
```html
<!-- Validated 2026-06-15 WSL: critical fix — hardcoded vpc-onprem replaced with <YOUR_VPC> (evidence: 01-validation-results.txt) -->
```

## Evidence files in this folder

- **00-discovery.txt** — Complete GCP resource inventory with real names and placeholder mapping (from Step 1)
- **01-validation-results.txt** — Comprehensive test results for all 11 commands with outputs and bugs found
- **README.md** — This file

## Next steps for team

**niobe-3 (Windows re-port instance)** can now proceed:
- All fixed commands have been validated on Linux/WSL
- Placeholder convention is locked: `<YOUR_...>`
- Ready to re-port these commands to `docs/troubleshooting-commands-windows.md`
- No scope creep: only fix tested, validated commands

**Decision-inbox note:** See `.squad/decisions/inbox/niobe-gcloud-wsl-validation-2026-06-15.md` for team-facing summary of findings and convention choice.

---

**Validation date:** 2026-06-15  
**WSL version:** Ubuntu 24.04 on Windows  
**gcloud version:** 552.0.0
