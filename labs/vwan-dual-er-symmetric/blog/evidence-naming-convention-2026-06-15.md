# Evidence File Naming Convention

**Proposed by:** The Kid | **Date:** 2026-06-15 | **Applies to:** `vwan-dual-er-symmetric` (Design C onward)

Current `NN-{name}.txt` resets numbering per run folder and isn't greppable across topology stages.

---

## Scheme

**Folder level:** keep current `{topology}-{phase}-{date}/` unchanged — survives re-runs without conflict.

**File level:** `{tier}-{probe}-{NN}.{ext}`

- **tier** — `ctrl` (Azure control-plane) · `data` (data-plane) · `fw` (firewall log) · `gcp` (GCP-side) · `portal` (screenshot)
- **probe** — kebab-case ≤ 25 chars; use the canonical names below consistently across runs
- **NN** — `01`–`99` only when the same probe appears multiple times in one folder

**Canonical probe names:**

`ctrl-er1-advertised` · `ctrl-er1-learned` · `ctrl-hub1-effective-routes` · `ctrl-hub2-effective-routes` · `gcp-cr-status` · `gcp-cr-status-before-mechc` · `gcp-cr-status-after-mechc` · `data-spoke1-to-vmb-tcp` · `data-vm-spoke1-ss-syn-sent` · `fw-azfw1-kql` · `fw-azfw2-kql` · `portal-hub1-effective-routes`

---

## Migration

Apply from Design C asymmetric run onward. **Do NOT rename Design B files** — blog already references them by current names.

| Current | Future runs |
|---------|-------------|
| `03-er1-advertised.txt` | `ctrl-er1-advertised-01.txt` |
| `09-tcp-a-to-b-x5.txt` | `data-spoke1-to-vmb-tcp-01.txt` |
| `11-azfw1-kql-results.txt` | `fw-azfw1-kql-01.txt` |

---

## Greppability

```bash
find show-output/ -name "fw-azfw1-kql*.txt"   # AzFW1 logs across all runs
find show-output/ -name "gcp-cr-status*.txt"  # GCP CR snapshots (before/after Mech C)
```
