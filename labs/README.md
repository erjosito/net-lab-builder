# Labs

> Per-lab artifact folders. Every ephemeral Azure Networking lab built by this squad gets a subfolder here.

## Convention

Each lab lives at `labs/<lab-name>/` and contains:

| File / Folder           | Owner    | Purpose                                                                          |
|-------------------------|----------|----------------------------------------------------------------------------------|
| `README.md`             | Niobe    | Lab summary — MUST surface a `## Designs studied` section with one entry per design (recommended AND not recommended), each with status, verdict, and evidence link. See routing rule #30. |
| `lessons-learned.md`    | Niobe    | What worked, what didn't, gotchas, links to issues filed upstream                |
| `validation.md`         | Niobe    | Validation matrix — what was checked, expected vs actual, evidence link          |
| `show-output/`          | Niobe    | Sanitized CLI output (effective routes, BGP peerings, traceroutes, logs)         |
| `screenshots/`          | Niobe    | Azure portal screenshots (topology, route tables, metrics)                       |
| `diagrams/`             | Trinity  | Architecture diagrams (Mermaid, drawio, or PNG exports)                          |
| `deploy/`               | Tank     | Lab-specific deploy artifacts (parameter files, overrides, post-deploy scripts)  |
| `design.md`             | Trinity  | Authoritative network design — sections include Mechanism trade-offs, Resiliency analysis (F-table, M-table, Patch catalogue), per-design rationale. README cites design.md sections for verdict reasoning. |

## Naming

Use kebab-case, short, descriptive:

- `expressroute-megaport-bgp/`
- `vwan-hub-firewall/`
- `private-endpoint-cross-vnet/`
- `nva-bgp-failover/`

## Lifecycle

Labs are ephemeral by design. Lifecycle is owned by Morpheus (8 phases):

1. **Analyze** the requirement
2. **Design** 2–5 candidate scenarios
3. **Generate manifest** (region, SKUs, cost estimate)
4. **Approval gate** — user signs off on cost + topology (routing rule #12)
5. **Deploy** (Tank, via `src/` + `labs/<lab>/deploy/`)
6. **Execute scenarios** (Trinity + Niobe — run diagnostics, capture evidence)
7. **Generate report** (Niobe — `README.md`, `lessons-learned.md`, `validation.md`)
8. **Approval gate** — user signs off on teardown (routing rule #12)
9. **Cleanup** (Tank — strict ExpressRoute dependency order)

## Sanitization (before commit)

Niobe must redact:

- ExpressRoute service keys
- Megaport API secrets and VXC config secrets
- VM admin passwords
- Base64-encoded access keys
- Subscription IDs → `<SUBSCRIPTION_ID>`
- Tenant IDs → `<TENANT_ID>`

See `.squad/agents/niobe/charter.md` and `.squad/routing.md` (rules #10 and #11) for the full sanitization checklist.

## Where lab IaC lives

- **Shared, reusable IaC** → `src/{bicep,terraform,azure-cli,powershell}/` (owned by Tank)
- **Lab-specific overrides** → `labs/<lab>/deploy/` (parameter files, post-deploy hooks)
