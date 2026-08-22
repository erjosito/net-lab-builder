# afd-edge-actions-jwt-validation — Stage-1 Lab Card
Morpheus · 2026-08-17 · **LOCKED — Phase 4 deployment authorised by Jose Moreno 2026-08-17**

---

## Card Summary

Probe Azure Front Door **Edge Actions v1** as a JWT validation layer. One AFD Standard
profile fronts a tiny App Service API in `swedencentral`. An Entra ID
client-credentials flow issues tokens (two-app-registration model). Edge Actions attempt
JWKS-based signature/claim verification at the edge; origin re-validates for defence in
depth. The primary unknown is **which cryptographic runtime APIs are available inside an
Edge Action v1 execution**; the capability probe (S1) resolves that before JWT logic is
committed.

**IN scope:** AFD Standard · Edge Actions v1 · App Service Linux B1 · Entra ID two-app-registration client-credentials · Log Analytics (EdgeActionConsoleLog + AFD access logs) · nine scenarios.

**OUT scope (application data path):** Custom domain · PE/Private Link · WAF · App Gateway · workload VMs · multi-region origin · ExpressRoute · vWAN.

> A Key Vault and private management VM were added later as operational test
> infrastructure. They are not part of the AFD-to-origin application data path.

---

## Objective and Hypothesis

> **H₁ (primary):** Edge Actions v1 exposes sufficient cryptographic runtime (JWKS
> fetch + RS256/ES256 verify) to reject unsigned or invalid JWTs **before** the request
> reaches the origin. Origin re-validation provides defence in depth and is the
> enforcement backstop when Edge Action fails open.
>
> **H₀ (null):** No public crypto runtime API exists in Edge Actions v1. The capability
> probe returns errors or empty stubs; the implementation falls back to origin-only or
> header-forwarding patterns.
>
> **Outcome: H₀ confirmed (CONDITIONAL verdict).** Lab evidence (S1, 2026-08-17/18)
> established that `crypto.subtle`, `fetch`, and `atob` are absent from the Edge Action
> sandbox. Cryptographic JWT signature validation is outside the supported scope of
> Edge Actions public preview. Claims-only
> JWT parsing is the maximum supported Edge Action JWT behaviour. See "Confirmed scope
> boundary" section above.

The study produces a **documented capability verdict** (CONDITIONAL — confirmed, see above) plus
evidence of all nine scenarios under the claims-only architecture.

---

## ⚠️ Phase 0 Preflight

| Check | Status |
|-------|--------|
| VM SKU / capacity preflight | **N/A — no VM in this lab** |
| AFD Standard + Edge Actions v1 available / opt-in | Preflight at deploy time |
| App Service Linux B1 in swedencentral | Preflight at deploy time |
| `Microsoft.Cdn` provider registered | Preflight at deploy time |
| Entra `Application Administrator` role | Preflight at deploy time |

---

## Regions

| Role | Region |
|------|--------|
| AFD profile | Global (Microsoft managed) |
| App Service origin | **swedencentral** |
| Log Analytics workspace | swedencentral |
| Entra ID | Tenant's home directory (global) |

---

## Address Plan

No VNet is required. App Service uses public multi-tenant hosting. Origin hardening is
enforced via AFD service tag + `X-Azure-FDID` header validation at the app layer (not
NSG-based).

---

## Cost Shape (estimated, AFD Standard)

| Component | SKU | $/day est. |
|-----------|-----|-----------|
| AFD Standard profile | 1 profile | ~$0.75 |
| AFD data transfer (lab traffic only) | <1 GB/day | ~$0.08 |
| App Service Plan | B1 Linux (or Free tier) | ~$0.05 (Free $0) |
| Log Analytics | Pay-per-GB, <1 GB/day | ~$0.25 |
| Entra ID app registrations | Free tier | $0.00 |
| **Total** | | **~$1.10–1.15 /day** |

> Well within the $50/day guardrail (rule #7). No cost-gate exception required.
> Actual session cost for a 4–6 h run ≈ **$0.25–0.40**.

---

## Activation Units and Stop/Go Gates

| Unit | Description | Gate |
|------|-------------|------|
| **A0** | Deploy resource group, Log Analytics, AFD profile, App Service + app, diagnostic settings | None |
| **A1** | Register Entra ID apps (resource + client), assign app role, generate client secret (stored outside repo) | A0 complete |
| **A2** | Deploy capability-probe Edge Action; confirm console logs reachable | A1 complete |
| **S1-GATE** | **Capability verdict** — crypto APIs present? YES → continue A3. NO → pivot to teaching-only or origin-only design | A2 evidence |
| **A3** | Deploy JWT Edge Actions (missing-token, sig-verify, claim-check versions) | S1-GATE GO |
| **A4** | Deploy execution-filter Edge Action (controlled timeout / fail-open) | A3 complete |
| **A5** | Run scenarios S2–S9; collect evidence | A4 complete |

Cleanup is separately gated (Jose must explicitly approve before Tank deallocates).

---

## ⚠️ Confirmed scope boundary (2026-08-19)

Scope clarification (2026-08-19): cryptographic JWT signature validation is outside
the supported scope of Edge Actions public preview. Use origin or gateway validation for all
cryptographic JWT verification.

Lab evidence (S1 probe, 2026-08-17/18) independently corroborates: `crypto=undefined`,
`fetch=undefined`, `atob=undefined` in the Edge Action sandbox. Claims-only JWT parsing
(structural validity, expiry, audience, issuer, roles) is the maximum supported EA JWT behaviour
in this release. The origin is the mandatory cryptographic enforcement point.

---

## Lock Status

> **LOCKED.** Design is final. Phase 4 deployment authorised. No further scope changes
> permitted without a new lab card revision.

**Downstream handoff:**
- **Trinity** → `manifest.md` → `design.md` (Edge Action JS stubs, JWKS endpoint wiring, App Service code, Entra ID registration instructions, diagnostic query templates)
- **Tank** → `manifest.md` activation sequence (A0–A5) and CLI deploy commands
- **Niobe** → `manifest.md` scenario pass/fail criteria (S1–S9) and evidence collection plan
- **Oracle** → topology and flow diagrams (AFD → Edge Action → origin, Entra token flow)
