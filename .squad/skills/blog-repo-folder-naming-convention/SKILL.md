# Skill — blog-repo-folder-naming-convention

**Owner:** Kid
**Applies to:** `github.com/erjosito/azure-networking-blog` (rolling blog repo) and any future per-lab standalone blog repos.
**Date added:** 2026-09-30

## Rule

Every post folder in `azure-networking-blog` (and equivalent per-lab blog repos) MUST use the naming pattern:

```
YYYY-MM-<slug>
```

- **`YYYY-MM`** — the year and month the post folder was first added to the repository. Use the earliest git-add date if backfilling a previously un-prefixed folder.
- **`<slug>`** — short, lowercase, hyphen-separated identifier that matches (or closely tracks) the source lab slug in `erjosito/net-lab-builder/labs/<slug>`.

Examples of compliant folders (confirmed 2026-09-30):

- `2026-05-expressroute-megaport-bgp`
- `2026-06-vwan-dual-er-symmetric`
- `2026-08-storage-endpoint-path-equivalence`
- `2026-08-dual-hub-vnra-udr-transit` (backfilled from `dual-hub-vnra-udr-transit`)
- `2026-09-vwan-ipsec-over-er-backup`
- `2026-09-vwan-rfc1918-routing-intent`
- `2026-09-sap-rise-scoped-peering-fwaas`

## Why

- Makes the post index chronologically sortable at a glance.
- Removes ambiguity when the source-lab slug and the blog-post folder name would otherwise be identical (readers can tell whether they are looking at the lab or the post from the path alone).
- Documented in the root `README.md` of `azure-networking-blog` under "Contributing / naming convention" as of PR #10 (2026-09-30).

## How to enforce

Before pushing a new post:

1. From `C:\Users\jomore\Repos\azure-networking-blog\`, confirm the target folder name starts with the current `YYYY-MM-` prefix.
2. Check every other top-level directory (`Get-ChildItem -Directory`) still matches the pattern. If a stray folder has crept in without the prefix, open a `chore/rename-*` PR to fix it (use `git mv`; earliest git-add date sets the `YYYY-MM`).
3. Update the root README post index to link the new folder path.
4. Do NOT rename Azure resource-group names or source-lab links inside the moved folder — those refer to real resources / the lab repo, not to the blog folder itself.

## Related

- Root README section: "Contributing / naming convention" (`azure-networking-blog/README.md`).
- Example enforcement PR: `erjosito/azure-networking-blog#10` (rename of `dual-hub-vnra-udr-transit`).
