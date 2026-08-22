# Smoke Check Results — foundry-agent-prompt-vs-hosted-networking T1 Deployment
**Deployment date:** 2026-08-20  
**Correlation ID (final):** c0476ec1  
**ARM deployment name:** deploy-tools-c0476ec1  
**ARM elapsed:** 2m14s (VM-only redeploy); 3m50s (initial full deploy)  
**Total wall time (Gate B → smoke):** ~59 minutes (including 2 script patch iterations, initial deploy, BOM fix redeploy, cloud-init wait)

## Deploy Timeline
| Time (UTC+2) | Event |
|---|---|
| 12:26:44 | Jose provided DEPLOY APPROVED (Gate B open) |
| 12:56:27 | First deploy attempt started |
| 12:57:xx | Fail: az CLI warning on stderr triggered ErrorActionPreference=Stop |
| 13:00:05 | Second attempt started (--only-show-errors added to az commands) |
| 13:00:05 | Fail: az bicep build warning same issue |
| 13:00:23 | Third attempt started (all 5 az commands patched) |
| 13:08:34 | First ARM deployment completed (18 Create, 0 Modify) |
| ~13:10 | Cloud-init status: done in 30s (BOM issue - YAML skipped by cloud-init) |
| 13:36:32 | Redeploy with BOM-fixed cloud-init (VMs deleted and recreated) |
| 13:42:43 | ARM redeployment complete (2m14s, 2 VMs only) |
| 13:48:09 | Cloud-init: status done, all 3 services active |
| 13:50:xx | Smoke checks: PASS |

## Resources Created (18 ARM resources)
| Resource | Type | Status | IP/Notes |
|---|---|---|---|
| vnet-tools | VirtualNetwork | Succeeded | 10.1.0.0/16 |
| EchoSubnet | Subnet | Succeeded | 10.1.100.0/24 |
| CtrlSubnet | Subnet | Succeeded | 10.1.200.0/24 |
| nsg-tools | NSG | Succeeded | 5 custom rules |
| peer-to-vnet-tools (on vnet-foundry) | VNetPeering | Connected/FullyInSync | |
| peer-to-vnet-foundry (on vnet-tools) | VNetPeering | Connected/FullyInSync | |
| nic-vm-tools-echo | NetworkInterface | Succeeded | 10.1.100.4 static |
| vm-tools-echo | VirtualMachine | Succeeded | B2ts_v2 Ubuntu 22.04 |
| nic-vm-tools-ctrl | NetworkInterface | Succeeded | 10.1.200.4 static |
| vm-tools-ctrl | VirtualMachine | Succeeded | B2ts_v2 Ubuntu 22.04 |
| dns-resolver-foundry | DnsResolver | Succeeded | vnet-foundry scoped |
| ep-inbound | InboundEndpoint | Succeeded | 192.168.3.4 (DNSInboundSubnet) |
| ep-outbound | OutboundEndpoint | Succeeded | DNSOutboundSubnet |
| ruleset-tools-lab | DnsForwardingRuleset | Succeeded | |
| rule-tools-lab | ForwardingRule | Succeeded | tools.lab → 10.1.100.4:53 |
| link-vnet-foundry | VNetLink | Succeeded | vnet-foundry linked |
| allow-out-aad (AgentSubnet NSG rule) | SecurityRule | Succeeded | prio 126 → AzureActiveDirectory |
| allow-out-ctrl-subnet (AgentSubnet NSG rule) | SecurityRule | Succeeded | prio 120 → 10.1.200.0/24 |
| allow-out-echo-subnet (AgentSubnet NSG rule) | SecurityRule | Succeeded | prio 110 → 10.1.100.0/24 |
| allow-out-mcr (AgentSubnet NSG rule) | SecurityRule | Succeeded | prio 125 → MicrosoftContainerRegistry |

## Smoke Check Results
| Check | Result | Detail |
|---|---|---|
| vm-tools-echo cloud-init | PASS | status: done; nginx/echo-http/dnsmasq active |
| HTTP echo (echo VM) | PASS | {"label":"echo","server_ip":"10.1.100.4","request_url":"http://10.1.100.4/api/echo?msg=smoke",...} |
| HTTPS echo (echo VM) | PASS | Self-signed cert; {"label":"echo","request_url":"https://10.1.100.4/api/echo?msg=smoke-https",...} |
| dnsmasq listening | PASS | 10.1.100.4:53 (UDP) |
| DNS echo.tools.lab | PASS | → 10.1.100.4 |
| DNS ctrl.tools.lab | PASS | → 10.1.200.4 |
| vm-tools-ctrl cloud-init | PASS | status: done; nginx/echo-http active |
| HTTP echo (ctrl VM) | PASS | {"label":"ctrl","server_ip":"10.1.200.4","request_url":"http://10.1.200.4/api/echo?msg=smoke-ctrl",...} |
| VNet peering (foundry→tools) | PASS | Connected, FullyInSync |
| VNet peering (tools→foundry) | PASS | Connected, FullyInSync |
| AgentSubnet NSG rules (4) | PASS | MCR/AAD/echo-subnet/ctrl-subnet outbound allow |
| DNS Resolver provisioning | PASS | dns-resolver-foundry: Succeeded |
| Cross-subnet ping ctrl→echo | EXPECTED FAIL | nsg-tools deny-in-all; only foundry→tools HTTP allowed (by design) |
| vm-diag curl/dig | SKIPPED | vm-diag is deallocated |

## Issues Encountered and Resolved
1. **az CLI stderr + ErrorActionPreference=Stop**: deploy.ps1 terminated on az bicep build and az deployment group validate because Bicep upgrade notice went to stderr. Fixed: added --only-show-errors to all 5 az deployment commands.
2. **UTF-8 BOM in cloud-init YAML**: Both echo-vm.yaml and ctrl-vm.yaml were saved with UTF-8 BOM by apply_patch tool. Cloud-init saw \ufeff#cloud-config (not #cloud-config) and skipped the entire config. Fixed: stripped BOM from both files using [System.IO.File]::ReadAllBytes + WriteAllBytes. Deleted VMs and redeployed.

## Outstanding / Not Tested
- vm-diag curl to http://10.1.100.4 (Foundry VNet → tools VNet; vm-diag deallocated)
- DNS Private Resolver forwarding path end-to-end (Foundry container → resolver → dnsmasq → echo)
- Hosted agent scenario (Wave 6) requires Jose to trigger Foundry agent runs
[Subscription IDs, tenant IDs, SSH keys not present in this file]
