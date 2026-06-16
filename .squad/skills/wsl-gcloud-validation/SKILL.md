---
name: "WSL gcloud validation"
description: "Validate gcloud CLI commands in documentation by running them against live GCP infrastructure via WSL. Discover actual resource names, identify syntax bugs, establish placeholder conventions, and fix docs with evidence trails."
domain: "testing, documentation, cross-platform-validation"
confidence: "high"
source: "earned (validated against Design B Phase 1 lab, 2026-06-15)"
tools:
  - name: "powershell (wsl wrapper)"
    description: "Execute WSL bash commands from PowerShell using `wsl -e bash -c '...'` or `wsl -- <command>`"
    when: "Calling gcloud from Windows PowerShell without entering WSL shell session"
---

## Context

Linux (and sometimes Windows) documentation for cloud CLIs are frequently ported from templates without validation against live infrastructure. This results in hardcoded placeholder literals that masquerade as real values, causing silent failures (empty command output instead of errors). Blog readers copy-paste these commands and get unexpected empty results, undermining trust.

**Pattern:** Placeholder `vpc-onprem` looks like a real resource name; readers substitute it in their own lab without realizing it's a template variable. The command silently returns 0 rows instead of failing loudly.

This skill teaches how to:
1. Discover actual resource names from live infrastructure
2. Test each gcloud command in documentation
3. Identify syntax bugs (deprecated subcommands, missing flags, wrong filters)
4. Establish a consistent, visually obvious placeholder convention
5. Fix docs with validation callouts for audit trail and blog reader confidence

## Patterns

### Step 0: WSL + gcloud sanity check

Before testing any commands, verify the environment is ready:

```powershell
# From PowerShell:
wsl --status
wsl -- gcloud --version
wsl -- gcloud config list
wsl -- gcloud auth list
```

**Stop conditions:**
- WSL not installed → request user install via `wsl --install`
- gcloud not available in WSL → request install path
- Not authenticated to correct project → request user run `wsl -- gcloud auth login` (interactive, can't be automated)
- Wrong project → `wsl -- gcloud config set project <PROJECT_ID>` and continue

### Step 1: Live resource discovery

**Never trust the briefing; run discovery commands first.** Use read-only gcloud commands to capture actual resource names, regions, IPs:

```bash
wsl -- gcloud compute networks list
wsl -- gcloud compute networks subnets list --filter="network:<VPC_NAME>"
wsl -- gcloud compute routers list
wsl -- gcloud compute interconnects attachments list
wsl -- gcloud compute instances list
wsl -- gcloud compute routes list
```

**Capture output** to a discovery file with an explicit placeholder-mapping table:

```
Discovered resources:
  VPC: vpc-vwan-symm-a-103167 (not vpc-onprem)
  Router A: router-vwan-symm-a (eu-w3, ASN 16550)
  Router B: cr-vwan-symm-onprem-b (eu-w4, ASN 16550)
  ...
  
Placeholder mapping:
  <YOUR_VPC> → vpc-vwan-symm-a-103167
  <YOUR_ROUTER_A> → router-vwan-symm-a
  <YOUR_ROUTER_B> → cr-vwan-symm-onprem-b
  ...
```

### Step 2: Command-by-command testing

For each gcloud command in the doc:

1. **Substitute placeholders** with discovered real values
2. **Run from WSL** via `wsl -e bash -c '...'` or `wsl -- <command>`
3. **Capture output** to evidence files (numbered sequentially: 01-router-describe.txt, 02-router-status.txt, etc.)
4. **Record outcome:**
   - 🟢 Works as-is (only placeholders needed substitution)
   - 🟡 Works with fix (syntax bug, deprecated flag, etc.) — note the required fix
   - 🔴 Fails — capture error, hypothesize root cause

### Step 3: PowerShell quoting gotcha

When running gcloud commands with complex bash quoting from PowerShell, **avoid inline scripts with nested quotes**. Instead:

```powershell
# ❌ AVOID (PowerShell escaping conflicts with bash quoting):
wsl -e bash -c 'gcloud compute routers get-status router-a --format=json | jq ".result.bgpPeerStatus[] | select(.ipAddress == \"169.254.150.121\") | {peer: .ipAddress, state: .state, learned: .learnedRoutes[] }"'

# ✅ PREFER (single commands without jq):
wsl -e bash -c 'gcloud compute routers get-status router-a --format=json'

# ✅ OR (write script to file first):
@'
gcloud compute routers get-status router-a --format=json | \
  jq ".result.bgpPeerStatus[] | select(.ipAddress == \"169.254.150.121\") | {peer: .ipAddress, state: .state, learned: .learnedRoutes[]}"
'@ | Out-File -FilePath script.sh -Encoding UTF8
wsl -e bash script.sh
```

**Why:** PowerShell's quoting rules (`'...'`, `"..."`, backticks) conflict with bash's quoting. Single commands avoid the conflict; scripts written to files sidestep PowerShell parsing entirely.

### Step 4: Placeholder convention

Choose a convention that is **visually impossible to miss** during copy-paste:

**Chosen convention: `<YOUR_...>` (angle brackets + ALL-CAPS)**

Examples:
- `<YOUR_VPC>`
- `<YOUR_BGP_PEER_NAME>`
- `<YOUR_ATTACHMENT_NAME>`
- `<YOUR_ROUTER_A>`

**Rationale:**
- Angle brackets make the token stand out in any editor
- ALL-CAPS is harder to accidentally type correctly (less likely to be copy-pasted as-is)
- Aligns with pedagogical priority: blog readers will copy-paste these commands; placeholders must be unmissable

**Document the convention** in the doc's Conventions section. Example:

```markdown
## Conventions

All placeholder values are marked with angle brackets and uppercase: `<YOUR_VPC>`, `<YOUR_ROUTER_A>`, etc. 
Replace these with your actual resource names before running any command.

For quick substitution, define environment variables:
  export VPC=vpc-vwan-symm-a-103167
  export ROUTER_A=router-vwan-symm-a
  ... then use --filter="network:$VPC" instead of --filter="network:<YOUR_VPC>"
```

### Step 5: Doc updates with validation callouts

**A. Replace hardcoded literals with placeholder tokens** throughout the doc. Example:

```markdown
# ❌ BEFORE (Joe copy-pastes this and gets 0 rows):
gcloud compute routes list --filter="network:vpc-onprem"

# ✅ AFTER (Joe sees the placeholder, substitutes his VPC, and gets results):
gcloud compute routes list --filter="network:<YOUR_VPC>"
```

**B. Add HTML comment validation callouts** immediately after each tested command:

```markdown
<!-- Validated 2026-06-15 WSL: works against gcp-vwan-symm-103167 / vpc-vwan-symm-a-103167 (output: 01-discovery.txt) -->
```

For commands that required fixes:

```markdown
<!-- Validated 2026-06-15 WSL: needs fix — original used `get-effective-firewalls` which doesn't exist in gcloud 552.0.0. Replaced with `firewall-rules list --filter="network:<YOUR_VPC>"` (output: 03-firewall-rules.txt) -->
```

**Why:** Validation callouts create an audit trail for the blog reader — they can see exactly which version of gcloud was tested and which output confirms the command works.

### Step 6: Evidence and decision documentation

**Create evidence files:**
- `00-discovery.txt` — discovered resource names + placeholder mapping
- `01-validation-results.txt` — detailed test results with actual command outputs
- `README.md` — summary for team (what tested, how many work, how many fixed, next steps)

**Create decision-inbox note:**
- `.squad/decisions/inbox/niobe-gcloud-<date>.md`
- Document: convention chosen, critical bugs found, implications for re-porting to Windows, cross-links to evidence

## Examples

**Example 1: Discovering the vpc-onprem bug**

```bash
# Step 1: Discover real VPC
wsl -- gcloud compute networks list --format="table(name, autoCreateSubnets)"
# NAME                          AUTO_CREATE_SUBNETWORKS
# vpc-vwan-symm-a-103167        False

# Step 2: Try original hardcoded command
wsl -- gcloud compute routes list --filter="network:vpc-onprem"
# Listed 0 items.  ← silent failure!

# Step 3: Try with real VPC
wsl -- gcloud compute routes list --filter="network:vpc-vwan-symm-a-103167"
# NAME                                    NETWORK                    DEST_RANGE           NEXT_HOP_IP  PRIORITY
# default-route-00e47e32e0c4d61a          vpc-vwan-symm-a-103167    0.0.0.0/0                        1000
# route-a-10-50-2-0                       vpc-vwan-symm-a-103167    10.50.2.0/24         169.254.150.121  1000
# ...  ← now returns results!
```

**Example 2: Fixing deprecated command**

```bash
# ❌ BEFORE: gcloud compute instances get-effective-firewalls <instance>
wsl -- gcloud compute instances get-effective-firewalls vm-a
# ERROR: (gcloud.compute.instances.get-effective-firewalls) unrecognized commands for group `gcloud.compute.instances`

# ✅ AFTER: gcloud compute firewall-rules list --filter="network:<YOUR_VPC>"
wsl -- gcloud compute firewall-rules list --filter="network:vpc-vwan-symm-a-103167" --format="table(name, direction, sourceRanges[].list():label=SOURCE_RANGES, targetTags[].list():label=TARGET_TAGS, allowed[].map().firewall_rule().list():label=ALLOW)"
# NAME                                    DIRECTION  SOURCE_RANGES         TARGET_TAGS  ALLOW
# default-allow-egress                    EGRESS     0.0.0.0/0                          all
# default-allow-icmp                      INGRESS    0.0.0.0/0                          icmp
# ...
```

**Example 3: Validation callout in doc**

```markdown
### 9.3 — List routes for a specific VPC

To see all routes associated with a VPC (both system-generated and custom):

```bash
gcloud compute routes list \
  --filter="network:<YOUR_VPC>" \
  --format="table(name, destRange, nextHopIp, nextHopGateway.basename(), nextHopVpnTunnel.basename(), priority)"
```

<!-- Validated 2026-06-15 WSL: critical bug fixed — original used hardcoded 'vpc-onprem' which matches no lab resource. Real VPC: vpc-vwan-symm-a-103167. Command returns 3 routes for this lab. (output: 01-validation-results.txt) -->
```

## Anti-Patterns

❌ **Don't trust the briefing.** Always run discovery commands first. The brief said `vpc-onprem`; the actual VPC was `vpc-vwan-symm-a-103167`. Trust the live `gcloud` output, not the design doc.

❌ **Don't hardcode placeholder literals.** `vpc-onprem` looks like a real value and tricks copy-paste readers. Use a visually obvious token like `<YOUR_VPC>` instead.

❌ **Don't assume empty command output means success.** `gcloud compute routers get-status ... | jq '.result.bgpPeerStatus[].learnedRoutes[]'` returning nothing *could* mean no routes learned yet (correct) or it could mean the query is wrong. Always verify with other commands (e.g., `gcloud compute routers list` confirms router exists).

❌ **Don't use inline bash with complex quoting from PowerShell.** The escaping conflicts are painful. Write to file or use single-command invocations instead.

❌ **Don't commit code without validation callouts.** Blog readers need to know which gcloud version was tested and where the evidence lives. Include the `<!-- Validated ... -->` comment.

❌ **Don't validate only one direction.** If testing a BGP command, verify it works for both routers (or both peers, both directions). A "works for Router A" validation is incomplete.
