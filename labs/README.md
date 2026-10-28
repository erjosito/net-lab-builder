# Labs

> Per-lab artifact folders. Every ephemeral Azure Networking lab gets a subfolder here.

The default is one accountable lead following the root `AGENTS.md` and
`.squad/live-lab-policy.md`. The lead owns all artifacts below. Squad role names
are optional specialist mappings, not mandatory dispatches or write restrictions.

## Convention

Each lab lives at `labs/<lab-name>/` and contains:

| File / Folder           | Optional Squad role | Purpose                                                                          |
|-------------------------|----------|----------------------------------------------------------------------------------|
| `README.md`             | Niobe    | Lab summary — MUST surface a `## Designs studied` section with one entry per design (recommended AND not recommended), each with status, verdict, and evidence link. |
| `lessons-learned.md`    | Niobe    | What worked, what didn't, gotchas, links to issues filed upstream                |
| `validation.md`         | Niobe    | Validation matrix — what was checked, expected vs actual, evidence link          |
| `show-output/`          | Niobe    | Sanitized CLI output (effective routes, BGP peerings, traceroutes, logs)         |
| `screenshots/`          | Niobe    | Azure portal screenshots (topology, route tables, metrics)                       |
| `diagrams/`             | Oracle   | Architecture diagrams (Mermaid, drawio, or PNG exports)                          |
| `deploy/`               | Tank     | Lab-specific deploy artifacts (parameter files, overrides, post-deploy scripts)  |
| `design.md`             | Trinity  | Authoritative network design — sections include Mechanism trade-offs, Resiliency analysis (F-table, M-table, Patch catalogue), per-design rationale. README cites design.md sections for verdict reasoning. |

## Naming

Use kebab-case, short, descriptive:

- `expressroute-megaport-bgp/`
- `vwan-hub-firewall/`
- `private-endpoint-cross-vnet/`
- `nva-bgp-failover/`

## Lifecycle

Labs are ephemeral by design. The lead owns the lifecycle end-to-end; explicitly
requested Squad sessions may delegate using the specialist mappings above.

1. **Analyze** the requirement
2. **Design** 2–5 candidate scenarios
3. **Generate manifest** (region, SKUs, cost estimate)
4. **Authorization** — honor existing task approval; otherwise obtain approval
   for resources, cost, and topology before deploying
5. **Deploy** via `src/` + `labs/<lab>/deploy/`
6. **Execute scenarios** — implement, validate traffic/path assertions, return
   verdicts with decisive evidence, and verify bounded restore under the same
   lead/scenario budget; optional independent review is read-only
7. **Cleanup** — preview and verify ownership, then automatically delete only
   task-created resources under standing authorization, unless instructed to
   retain them; preserve reused resources and follow provider dependency order
8. **Finish offline** — `README.md`, `lessons-learned.md`, `validation.md`, and
   diagrams from stable evidence; publication is opt-in

Preserve decisive sanitized evidence before teardown. Presentation, vault
backfill, and blog requests must not delay verdict, restore, or cleanup.

## Sanitization (before commit)

The lead (Niobe when delegated in Squad mode) must redact:

- ExpressRoute service keys
- Megaport API secrets and VXC config secrets
- VM admin passwords
- Base64-encoded access keys
- Subscription IDs → `<SUBSCRIPTION_ID>`
- Tenant IDs → `<TENANT_ID>`

See `.squad/agents/niobe/charter.md` and `.squad/routing.md` (rules #10 and #11) for the full sanitization checklist.

## Where lab IaC lives

- **Shared, reusable IaC** → `src/{bicep,terraform,azure-cli,powershell}/`
- **Lab-specific overrides** → `labs/<lab>/deploy/` (parameter files, post-deploy hooks)
