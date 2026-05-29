# Work Routing

How to decide who handles what.

## Routing Table

| Work Type | Route To | Examples |
|-----------|----------|----------|
| Lab requirements & architecture | Morpheus | Scope a new lab, pick topology pattern, decide region & SKU mix, write design block in `labs/<name>/README.md` |
| Azure networking design | Trinity | VNet / subnet layout, NSG / UDR / route tables, peering, VPN / ExpressRoute, Azure Firewall, Private Endpoints, App Gateway / Front Door, name resolution |
| Azure networking knowledge / vault stewardship | Trinity | Read Jose's `AzureNetworking` Obsidian vault before designing a lab; backfill findings, gotchas, anomalies, and API-drift observations into vault notes after Niobe validation completes (pre-cleanup gate). See Trinity's charter "Vault Stewardship" section. |
| IaC authoring & deploy | Tank | Bicep / Terraform modules in `src/`, Azure CLI / PowerShell deploy + teardown scripts, parameter files, `azd` wiring |
| Validation & diagnostics | Niobe | `az network …` show commands, effective routes/NSGs, NSG flow logs, Connection Monitor, traceroutes, log/metric queries, portal screenshots, lessons-learned capture |
| Lab documentation & diagrams | Oracle | Topology / control-plane / data-plane / cleanup diagrams in `labs/<name>/diagrams/`; mermaid (simple, renders natively in GitHub) or drawio (multi-cloud / branded icons); embeds in `README.md` |
| Cleanup / teardown | Tank | Resource group deletion, soft-deleted key vault purge, dangling public IP cleanup |
| Code review (IaC) | Trinity reviews Tank; Tank reviews Trinity-authored IaC | Cross-check before deploy |
| Scope & priorities | Morpheus | Which lab to build next, trade-offs, when a lab is "done enough" to destroy |
| Session logging | Scribe | Automatic — never needs routing |

## Issue Routing

| Label | Action | Who |
|-------|--------|-----|
| `squad` | Triage: analyze issue, assign `squad:{member}` label | Morpheus |
| `squad:morpheus` | Architecture / requirements / scope questions | Morpheus |
| `squad:trinity` | Networking design questions / topology bugs | Trinity |
| `squad:tank` | Deployment failures, IaC bugs, cleanup issues | Tank |
| `squad:niobe` | Diagnostic gaps, missing screenshots | Niobe |
| `squad:oracle` | Missing or stale diagrams, README readability, diagram-source bugs | Oracle |

### How Issue Assignment Works

1. When a GitHub issue gets the `squad` label, **Morpheus** triages it — analyzing content, assigning the right `squad:{member}` label, and commenting with triage notes.
2. When a `squad:{member}` label is applied, that member picks up the issue in their next session.
3. Members can reassign by removing their label and adding another member's label.
4. The `squad` label is the "inbox" — untriaged issues waiting for Morpheus.

## Rules

1. **Eager by default** — for a new lab, spawn Morpheus → then Trinity + Tank in parallel (design + scaffold IaC), then Niobe to draft validation plan.
2. **Scribe always runs** after substantial work, always as `mode: "background"`. Never blocks.
3. **Quick facts → coordinator answers directly.** Don't spawn an agent for "what region is the lab in?"
4. **When two agents could handle it**, pick the one whose domain is the primary concern. Networking design = Trinity even if it touches IaC. IaC quirks = Tank even if networking-shaped.
5. **"Team, ..." → fan-out.** Spawn all relevant agents in parallel as `mode: "background"`.
6. **Anticipate downstream work.** Whenever IaC lands, spawn Niobe to draft the validation/diagnostic command list against the deployed shape.
7. **Cost guardrail.** Any deployment proposal larger than ~$50/day should be flagged by the proposing agent and confirmed by Jose before Tank deploys.
8. **Ephemeral-first.** Every lab must ship a teardown path. No lab is "complete" without a working cleanup script. Tank owns this.
9. **Evidence-first.** No lab is "documented" without diagnostic output and portal screenshots in `labs/<name>/`. Niobe owns this.
10. **No hardcoded subscription IDs or tenant IDs — anywhere in the repo.** Not in Bicep `param` defaults, not in Terraform `variable` defaults, not in CLI/PS scripts, not in example commands in READMEs, not in `show-output/` captures. Resolution order in any script: (1) `--subscription` flag → (2) `$AZURE_SUBSCRIPTION_ID` env var → (3) caller's `az account show` context. Niobe redacts subscription IDs that leak in via Azure resource IDs (`/subscriptions/<guid>/...`) to `<SUBSCRIPTION_ID>` before output lands in `labs/<name>/`. Tank enforces at deploy time; Niobe enforces at write-up time; Trinity keeps design specs subscription-agnostic.
11. **No hardcoded secrets — anywhere, ever.** Megaport API key/secret live in the user's Key Vault and are fetched at runtime via `az keyvault secret show`. VM admin passwords (Windows) are prompted from Jose at deploy time — no defaults. ER service keys, storage account keys, SAS tokens, JWTs, and any base64-encoded credentials are stripped from artifacts before commit.
12. **Approval gates.** Two gates per lab, both owned by Morpheus: (a) before any deploy — present resources, regions, time + cost estimate; wait for explicit "yes". (b) before any cleanup — show what will be deleted (dry-run); wait for explicit "yes". Never skip either.
13. **VM SKU region research.** Morpheus runs `az vm list-skus --location <region> --resource-type virtualMachines` and filters out any SKU with `NotAvailableForSubscription` restrictions **before** locking the region in the manifest. B-series IS allowed for lab VMs (B1s / B2s preferred); only escalate to D-series when the test demonstrably needs sustained CPU / RAM. If the cheapest viable SKU in the chosen region is more expensive than B2s, check the next-cheapest region in the same geography first. See Morpheus charter "Region + VM SKU research" section for the exact probe.
14. **Diagram-first.** No lab is "documented" without diagrams in `labs/<name>/diagrams/`. Oracle owns this. Mermaid for simple shapes (renders natively in GitHub via ` ```mermaid ` fences), drawio for multi-cloud / branded-icon topology. Default catalogue for ER + Megaport labs: topology, control-plane, data-plane, cleanup chain. Oracle's first dispatch happens in parallel with Niobe's validation — diagrams don't block on validation completing, only on Tank's deploy completing.
15. **Vault is single source of truth for Azure networking knowledge.** Trinity owns read+write into Jose's `AzureNetworking` Obsidian vault (`C:\Users\jomore\OneDrive - Microsoft\ObsidianVaults\AzureNetworking\`). Before designing, Trinity indexes the vault. Before cleanup (Phase 3.4), Trinity backfills lab findings into the vault — non-optional, blocks cleanup. The vault is **read-only** for all other squad members; any vault-touch by Morpheus / Tank / Niobe / Oracle / Scribe / Ralph must be requested through Trinity. The vault's own `AGENTS.md` defines the page schema (YAML frontmatter, `Labs/YYYY-MM-<LabName>.md` naming, wikilinks) — Trinity follows it without exception. Forbidden GUIDs (subscription `<subscription-guid>`, tenant `<tenant-guid>`) never appear in vault notes; Trinity sanitization-checks every touched file before declaring done.
