# Preflight Summary — foundry-agent-prompt-vs-hosted-networking
**Date:** 2026-08-20  
**Target RG:** `<rg-foundry>` (SwedenCentral)
**Template:** labs/foundry-agent-prompt-vs-hosted-networking/deploy/main.bicep  
**No Azure resources were created, modified, or deleted during preflight.**

## Gate Results

| # | Gate | Result | Key Finding |
|---|------|--------|-------------|
| 1 | Standard_B2ts_v2 SKU in SwedenCentral | **PASS** | Available zones 1/2/3, restrictions: [] |
| 2 | ARM template validate (live capacity gate) | **PASS** | exit 0, error: null |
| 3 | 10.1.0.0/16 address space overlap | **CONDITIONAL PASS** | hub1-vnet uses 10.1.0.0/16 in rg-dual-hub-vnra-udr-transit but NOT peered to vnet-foundry; current peering safe |
| 4 | Resource providers + DNS Resolver in SwedenCentral | **PASS** | Microsoft.Network + Microsoft.Compute Registered; dnsResolvers supports Sweden Central |
| 5 | Foundry account/vnet-foundry/AgentSubnet prerequisites | **PASS** | All present; CRITICAL fix applied (see below) |
| 6 | What-if: 0 Modify + 0 Delete on existing resources | **PASS** | 18 Create, 0 Modify, 0 Delete, 52 Ignore |
| 7 | Cost validation vs \/day guardrail | **PASS** | Estimates corrected (see below); ~12.56/day incremental, well within \ |

## Critical Findings and Fixes

### NSG Name Correction (Gate 5)
- **Finding:** AgentSubnet NSG is named net-foundry-AgentSubnet-nsg-swedencentral
  (auto-created by Microsoft.App/environments Container Apps service, not 
sg-agentsubnet as originally assumed)
- **Fix applied:** Updated deploy/parameters/lab.parameters.json and deploy/main.bicep param default
- **Impact:** Without this fix, deployment would succeed provisioning all T1 resources but fail patching AgentSubnet NSG rules

### Cost Correction (Gate 7)
DNS Private Resolver costs significantly more than initial Morpheus estimate:

| Resource | Manifest Est. | Actual (PAYG) |
|----------|--------------|---------------|
| vm-tools-echo (B2ts_v2) | \.18/day | **\.24/day** |
| vm-tools-ctrl (B2ts_v2) | \.18/day | **\.24/day** |
| DNS Private Resolver (2 endpoints) | \.36/day | **\.08/day** |
| **Lab incremental total** | **\.22/day** | **~\.56/day** |

Total with shared infra: ~\.86/day (still within \/day guardrail).  
**Recommendation:** Set deployDnsResolver=false to save \/day when DNS hierarchy testing is not needed.

### Address Space Warning (Gate 3)
hub1-vnet (10.1.0.0/16) exists in g-dual-hub-vnra-udr-transit. This VNet is NOT currently 
peered to net-foundry. Any future attempt to peer hub1-vnet → net-foundry would 
create an address space conflict with net-tools (both using 10.1.0.0/16).

## Deployment Gate Status
- **Jose said:** "Deployment approved"
- **Required exact phrase:** DEPLOY APPROVED
- **Status:** BLOCKED — phrase does not match. Deployment NOT executed.
- **To proceed:** Type exactly DEPLOY APPROVED when running deploy.ps1 -Apply

## Files in this directory
| File | Gate |
|------|------|
| gate1-sku.json | 1 |
| gate2-arm-validate.json | 2 |
| gate3-vnet-conflicts.json | 3 |
| gate4-providers.json | 4 |
| gate5-foundry-resources.json | 5 |
| gate6-whatif.txt | 6 |
| gate7-pricing.json | 7 |
| preflight-summary.md | All |
