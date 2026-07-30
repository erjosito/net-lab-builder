# SKILL: vWAN NVA XFRM Interface Restore After Deallocation

**Author:** Niobe  
**Created:** 2026-07-30T17:15:00+02:00  
**Applies to:** Labs using Ubuntu NVAs with strongSwan xfrm interfaces connecting to Azure vWAN VPN Gateways

---

## Purpose

After an Azure VM is deallocated (stopped/started or dealloc/start), XFRM interfaces
(`xfrm41`, `xfrm42`) and IPsec tunnels are NOT automatically restored. strongSwan
swanctl.conf connections are not loaded. BGP sessions (BIRD) will not establish.

This skill provides the tested 6-step restore procedure and the vm_run_command invocation
pattern to execute it safely.

---

## Prerequisites

- VM is running (verified with `az vm list -g <rg> --show-details -o table`)
- You know the hub VPN Gateway BGP peer IP addresses (from `az network vpn-gateway show`)
- swanctl.conf is on disk at `/etc/swanctl/swanctl.conf` with connections vng0/vng1 + children s2s0/s2s1
- BIRD is configured with BGP neighbors at 192.168.x.12 and 192.168.x.13

---

## Hub VPN Gateway BGP Peer IPs (routemap-test-rg lab)

| Hub | VPN GW | Instance0 (xfrm41) | Instance1 (xfrm42) |
|-----|--------|---------------------|---------------------|
| hub-eu1 | vpngw-eu1 | 192.168.2.12 | 192.168.2.13 |
| hub-eu2 | vpngw-eu2 | 192.168.4.12 | 192.168.4.13 |

Query: `az network vpn-gateway show -g <rg> -n vpngw-eu1 --query bgpSettings.bgpPeeringAddresses[].defaultBgpIpAddresses`

---

## Restore Procedure (6 steps)

```bash
# Step 1-2: Recreate XFRM interfaces (if_id must match swanctl.conf if_id_in/if_id_out)
ip link add xfrm41 type xfrm dev eth0 if_id 41 2>/dev/null
ip link set xfrm41 up
ip link add xfrm42 type xfrm dev eth0 if_id 42 2>/dev/null
ip link set xfrm42 up

# Step 3: Add routes to hub VPN GW BGP peer IPs through XFRM interfaces
ip route add <hub-Instance0-bgp-ip>/32 dev xfrm41 2>/dev/null
ip route add <hub-Instance1-bgp-ip>/32 dev xfrm42 2>/dev/null

# Step 4: Load strongSwan connections from swanctl.conf
swanctl --load-all

# Step 5: Initiate IKE/IPsec sessions (start_action=trap does NOT auto-initiate)
swanctl --initiate --child s2s0 --ike vng0 --timeout 30
swanctl --initiate --child s2s1 --ike vng1 --timeout 30

# Step 6: Wait for BGP convergence
sleep 75
birdc show protocols  # verify: vpngw0 Established, vpngw1 Established
```

---

## vm_run_command Invocation Pattern (safe single-line)

Use semicolon-separated single line to avoid stuck-extension risk:

```powershell
$RG = "routemap-test-rg"
$BGP0 = "192.168.4.12"   # hub Instance0 BGP IP
$BGP1 = "192.168.4.13"   # hub Instance1 BGP IP

$script = "ip link add xfrm41 type xfrm dev eth0 if_id 41 2>/dev/null; ip link set xfrm41 up; ip link add xfrm42 type xfrm dev eth0 if_id 42 2>/dev/null; ip link set xfrm42 up; ip route add $BGP0/32 dev xfrm41 2>/dev/null; ip route add $BGP1/32 dev xfrm42 2>/dev/null; swanctl --load-all 2>&1; echo XFRM_READY"

az vm run-command invoke -g $RG -n nva2 --command-id RunShellScript --scripts $script -o json 2>&1 `
  | ConvertFrom-Json | Select-Object -ExpandProperty value | ForEach-Object { $_.message }

# Then initiate tunnels:
$script2 = "swanctl --initiate --child s2s0 --ike vng0 --timeout 30 2>&1; swanctl --initiate --child s2s1 --ike vng1 --timeout 30 2>&1; echo INITIATE_DONE"
az vm run-command invoke -g $RG -n nva2 --command-id RunShellScript --scripts $script2 -o json 2>&1 `
  | ConvertFrom-Json | Select-Object -ExpandProperty value | ForEach-Object { $_.message }
```

---

## Verification

After ~75s, verify BGP is established:

```powershell
$script3 = 'birdc show protocols; echo ---; birdc show route count'
az vm run-command invoke -g $RG -n nva2 --command-id RunShellScript --scripts $script3 -o json 2>&1 `
  | ConvertFrom-Json | Select-Object -ExpandProperty value | ForEach-Object { $_.message }
```

Expected output:
```
vpngw0   BGP   master   up   HH:MM:SS   Established
vpngw1   BGP   master   up   HH:MM:SS   Established
```

---

## When to Use

- Before any Niobe gate measurement where NVA VMs were previously deallocated
- After `az vm start` on nva1 or nva2 in any lab using this XFRM/strongSwan topology
- After unexpected VM restarts (Azure platform maintenance events)

---

## Failure Mode: Stuck run-command extension

If `az vm run-command invoke` returns `Conflict/409` ("execution in progress"):
- The VM's RunCommandLinux extension agent is stuck from a previous operation
- `az vm run-command create` (newer persistent API) may also hang
- Resolution: `az vm redeploy -g <rg> -n <vm>` or `az vm delete + recreate`
- The stuck state persists across VM deallocation/restart (extension agent state is on disk)

**Do NOT submit complex multiline scripts** (bash heredocs, grep with pipes, 2>/dev/null in
complex chains) via PowerShell az vm run-command. Always use semicolon-separated single-line
commands. Test with `echo VM_ALIVE` before any longer script.

---

## Timing Reference (tested, nva2, routemap-test-rg)

| Operation | Duration |
|-----------|----------|
| VM start (deallocated → running) | ~90 seconds |
| XFRM interface creation + swanctl load | ~15 seconds |
| IPsec tunnel establishment (both) | ~15 seconds (per swanctl output) |
| BGP convergence (Idle → Established) | ~75 seconds |
| **Total: deallocated → BGP Established** | **~3 minutes** |

---

*Niobe — Lab Validator & Diagnostics*  
*Tested: 2026-07-30T17:10:00+02:00 on nva2 (hub-eu2, westeurope)*
