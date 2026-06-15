# Network troubleshooting — Windows / PowerShell companion

Companion to [`troubleshooting-commands-linux.md`](./troubleshooting-commands-linux.md). Sections mirror. Same commands work — install `curl` + `jq` via winget, watch for PowerShell syntax traps.

---

## 0. Setup

```powershell
$env:RG = "rg-vwan-symm-103167"
$env:VHUB1 = "vhub-..."
$env:MP_KEY = "api-key"
$env:MP_SECRET = "api-secret"
$env:MP_API = "https://api.megaport.com"

# Prompt for secret without echo
$secret = Read-Host "Megaport Secret" -AsSecureString
$plainSecret = [System.Net.NetworkCredential]::new('', $secret).Password
```

---

## 0.5 Install utilities via winget

| Tool | Notes |
|---|---|
| **PowerShell 7+** | `winget install Microsoft.PowerShell` — Highly recommended. Most gotchas in this doc disappear on PS 7+. Run as `pwsh`. |
| **curl.exe** | Windows 10 1803+ / 11 ship it natively. Verify: `curl.exe --version`. Winget NOT needed unless your curl is very old. |
| **jq** | `winget install jqlang.jq` — verify: `jq --version` |
| **Git for Windows** | `winget install Git.Git` — provides bash, grep, awk at `Program Files\Git\bin` |
| **ripgrep** | `winget install BurntSushi.ripgrep.MSVC` — optional; faster than `Select-String` |

Restart PowerShell after install (or `. $PROFILE` in current session).

---

## 1. Which PowerShell are you running?

Check your version first:

```powershell
$PSVersionTable.PSVersion
```

- **PowerShell 7+ (modern, runs as `pwsh`):** No `curl` alias. `curl` resolves to `curl.exe` natively. Jump to §2 for the real gotchas.
- **Windows PowerShell 5.1 (pre-installed on Windows 10/11, runs as `powershell`):** Has a `curl` → `Invoke-WebRequest` alias. See §1.1.

**Recommendation:** Install PowerShell 7+ via `winget install Microsoft.PowerShell`. Most gotchas vanish on the modern version.

### 1.1 The curl/wget alias trap (Windows PowerShell 5.1 only)

If stuck on PS 5.1, `curl` resolves to `Invoke-WebRequest` (a PowerShell cmdlet). Symptoms: "parameter not found" errors on `-s`, `-X`, etc.

Diagnose: `Get-Command curl` → if `Alias`, trap applies.

Fixes (pick one):
- Type `curl.exe` always
- `Remove-Item Alias:curl -Force` in `$PROFILE`
- Upgrade to PS 7+

---

## 2. Bash → PowerShell command pitfalls

⚠️ **Most common copy-paste failure:** The **backslash line-continuation** (`\` at end of line from bash scripts). PowerShell treats `\` as a literal character (path separator), NOT line continuation. Command parses as one long invalid line. Use backtick (`` ` ``) instead — but backticks are fragile (trailing whitespace breaks them). **Preferred: one-line the entire command.** *(Source: Jose live-test 2026-06-15, lab #2)*

```powershell
# ❌ Backslash doesn't work in PowerShell (bash-only)
curl.exe -s -X POST \
  "$apiUrl/v2/login" \
  -d "username=$user&password=$pass"

# ✅ Backtick works (PowerShell line continuation)
curl.exe -s -X POST `
  "$apiUrl/v2/login" `
  -d "username=$user&password=$pass"

# ✅ Preferred: one-line (no fragile backticks)
curl.exe -s -X POST "$apiUrl/v2/login" -d "username=$user&password=$pass"
```

Other pitfalls:

| Bash | PowerShell | Fix |
|---|---|---|
| `$VAR` (env var reference) | PS treats `$VAR` as a local variable, NOT an env var. If undefined → empty string → curl sends `username=&password=` → 401 | Use `$env:VAR` for env vars. Or: `$MP_USER = $env:MP_USER` first. **This is the #2 trap.** |
| `export VAR=foo` | Not a PS command | `$env:VAR = "foo"` (process scope) or `[System.Environment]::SetEnvironmentVariable('VAR','foo','User')` (persist) |
| `` `subshell` `` | PS escape char, not substitution | Use `$(command)` instead |
| `<<EOF...EOF` heredoc | Syntax error | PS here-string: `$body = @"..."@` then `-d $body` |
| `&` in quoted string | If double-quoted, call operator; if unquoted, background job. E.g., `-d "x=1&y=2"` tries to run `y=2` as a command | Use single quotes: `-d 'x=1&y=2'` |
| `2>&1` | Works identically ✅ |
| `cmd \| tee file` | Works but flush differs | `cmd \| Out-File file` (or `\| Tee-Object file`) |
| `find . -name X` | PS has no `find` | `Get-ChildItem -Recurse -Filter X` |

---

## 3. Identical sections from main doc

**§1–6 (Azure vWAN, ER, VPN, AzFW, NIC), §8–9 (gcloud):** Use main doc as-is. Substitute `curl` → `curl.exe` and single-quote any `-d` bodies with `&`. Example:

```powershell
# From main doc, Windows-adapted
curl.exe -s "https://management.azure.com/subscriptions/$env:SUB_ID/providers/Microsoft.Network/virtualWans?api-version=2023-02-01" -H "Authorization: Bearer $(az account get-access-token --query accessToken -o tsv)" | jq '.value[] | select(.properties.virtualWanType == "Standard")'
```

---

## 4. Megaport HTTP API (§7 main doc)

**Primary: curl.exe + jq**

```powershell
# Login
curl.exe -s -X POST "$env:MP_API/v2/login" -H "Content-Type: application/x-www-form-urlencoded" -d "username=$env:MP_KEY&password=$plainSecret" | jq -r '.data.session'

# List MCRs
curl.exe -s "$env:MP_API/v2/products" -H "X-Auth-Token: $env:MP_TOKEN" | jq '.data[] | select(.productType == "MCR2") | [.productUid, .productName]'

# VXC BGP (Azure: csp_connection; GCP: aEnd.partnerConfig)
curl.exe -s "$env:MP_API/v2/product/<VXC_UID>" -H "X-Auth-Token: $env:MP_TOKEN" | jq '.data.resources.csp_connection[0].interfaces[0].bgpConnections'
```

**Alt: PowerShell-native (irm) — for readers skipping curl/jq install.** See §7 for function wrappers using irm.

---

## 5. JSON parsing without jq

**Alternative to `jq` for readers skipping installs:**

| Goal | ConvertFrom-Json |
|---|---|
| vHub routes + AS-path | `az network vhub get-effective-routes ... -o json \| ConvertFrom-Json \| Select-Object -ExpandProperty value \| Format-Table @{N='prefix'; E={$_.addressPrefixes[0]}}, asPath` |
| ER circuit peerings | `az network express-route list -o json \| ConvertFrom-Json \| Where-Object name -eq '<ERCKT1>' \| Select-Object -ExpandProperty peerings \| Format-Table name, peeringType` |

---

## 6. Windows VM diagnostics

| Task | PowerShell |
|---|---|
| Routes | `Get-NetRoute -PolicyStore ActiveStore \| Where-Object NextHop -ne '0.0.0.0' \| Format-Table DestinationPrefix, NextHop, InterfaceAlias -AutoSize` |
| IPs | `Get-NetIPAddress -AddressFamily IPv4 \| Format-Table IPAddress, PrefixLength, InterfaceAlias` |
| Traceroute | `Test-NetConnection <ip> -TraceRoute` |
| DNS | `Resolve-DnsName <name> -Type A \| Format-Table Name, IPAddress, TTL` |
| TCP conns | `Get-NetTCPConnection -State Established \| Format-Table LocalAddress, LocalPort, RemoteAddress, RemotePort` |
| Packets (admin) | `pktmon start --capture --comp nics --pkt-size 0` |

---

## 7. PowerShell function wrappers

```powershell
function vhub-eff { param([string] $RG, [string] $Hub)
  $id = az network vhub route-table show -g $RG --vhub-name $Hub -n defaultRouteTable --query id -o tsv
  az network vhub get-effective-routes -g $RG -n $Hub --resource-type RouteTable --resource-id $id -o json | ConvertFrom-Json | Select-Object -ExpandProperty value | Format-Table addressPrefixes, asPath }

function mp-vxc-bgp { param([string] $VxcUid)
  curl.exe -s "$env:MP_API/v2/product/$VxcUid" -H "X-Auth-Token: $env:MP_TOKEN" | jq '.data.resources.csp_connection[0].interfaces[0].bgpConnections' }

function er-routes { param([string] $Circuit, [string] $RG)
  az network express-route route-table summary -g $RG -n $Circuit --peering-type AzurePrivatePeering -o json | ConvertFrom-Json | Select-Object -ExpandProperty value | Format-Table @{N='prefix'; E={$_[0].network}} }
```

---

## 8. PowerShell gotchas

- **curl alias:** Use `curl.exe`. Permanent: `Remove-Item Alias:curl -Force` in `$PROFILE`.
- **`&` in body:** Single-quote: `-d 'x=1&y=2'`.
- **Codes:** `Invoke-WebRequest` captures; `Invoke-RestMethod` throws (use `-SkipHttpErrorCheck`).
- **Admin:** pktmon, `Get-NetTCPConnection -IncludeAllProcesses` need elevation.

---

## 9. Contribution rules

Cross-lab, append not rewrite, cite sources, table format, no secrets, update index.
