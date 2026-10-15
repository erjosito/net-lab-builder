# MSDN endpoint deployment — 2026-10-15 UTC

**PASS: infrastructure only; restored/deallocated. No traffic or billing conclusion.**

- Authorized separate $4 endpoint, not a draw on the $8 A/B/P core.
- Native Ubuntu-24.04 `/usr/bin/az`; explicit subscription on every invocation.
  Account and token tenant/subscription pinned before each mutation. WSL and
  Windows identities are distinct; final read-only Windows comparison passed.
- Alternative direct ARM resourceSkus catalog: one page, Sweden Central.
  Compute/Network already registered. B1ls excluded (0.5 GiB); B1s passes
  minimum 1 GiB, catalog restrictions and public retail $0.0108/hour ceiling.
- New owned RG created **08:20:59Z**. ARM validation passed **08:21:04Z**.
  Actual deployment/allocation succeeded **08:22:16Z**, not merely catalog proof.
- One nonzonal Standard_B1s Ubuntu 22.04 Gen2 VM, 30 GiB StandardSSD_LRS
  disk, NIC, NSG, Standard static IPv4 PIP, VNet/subnet. All six resources
  independently reported provisioning Succeeded and exact ownership tags.
  No zones, peering, NAT/LB, extensions, paid logs or bootstrap downloads.
- All inbound denied at priority 100; subnet defaultOutboundAccess=false.
  No traffic harness, listener, public SSH rule or billing calls.
- **PowerState/deallocated verified 08:22:55.566625Z**. Cleanup preview passed:
  exact recorded inventory, no foreign/unrecorded resources. Nothing deleted.
- Four mutation commands: group create, ARM validate, ARM deploy, deallocate.
  Deployment lease completed; owned child commands exited, no background jobs.
- Ignored evidence: `private\msdn-inventory.private.json` (identities, timestamps,
  resource details/tags/power), `msdn-gate.private.json`,
  `msdn-capacity.private.json`, `msdn-b1s-price.private.json` and
  `msdn-windows-unchanged.private.json`. No tokens were exported to Windows.

**Retained disk/PIP remain billable.** Hard lifetime deadline:
**2026-10-18 08:20:59Z**; max 12 allocated hours, reserved future traffic max
10 GiB, no traffic run under this lease. Deletion needs explicit separate
approval, exact private run confirmation and a fresh authorized cleanup lease.
