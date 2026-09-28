# Sanitized foundation and blocker evidence

Captured on 2026-09-28. Identifiers, service keys, pairing keys, public IPs, credentials, tokens, PSKs, and GUIDs are intentionally omitted.

## Azure foundation

```text
vHub:
  provisioningState: Succeeded
  hubRoutingPreference: ASPath
  addressPrefix: 10.240.0.0/24

VPN gateway:
  provisioningState: Succeeded

ExpressRoute gateway:
  provisioningState: Succeeded

Workload vHub connection:
  provisioningState: Succeeded

ExpressRoute circuit:
  provisioningState: Succeeded
  circuitProvisioningState: Enabled
  serviceProviderProvisioningState: NotProvisioned
  tier: Standard
  family: MeteredData
  bandwidth: 50 Mbps
```

## GCP foundation

```text
CPE:
  status: RUNNING
  machineType: e2-small
  zone: europe-north2-c
  canIpForward: true
  internalIp: 10.250.0.10
  aliasRanges:
    - 10.250.254.240/32
    - 10.250.254.241/32
    - 10.250.254.242/32
    - 10.250.254.250/32

Startup smoke:
  startup service: inactive (successful completed oneshot)
  forwarding: 1
  strongswan: active
  frr: active
  required package checks: 3/3

Partner attachment:
  type: PARTNER
  state: PENDING_PARTNER
  adminEnabled: true
  edgeAvailabilityDomain: AVAILABILITY_DOMAIN_1

Cloud Router:
  ASN: 16550
  advertiseMode: CUSTOM
  advertisedRanges:
    - 10.250.0.10/32
```

## Capacity retries

```text
europe-north2-a / e2-small: resource capacity failure
europe-north2-b / e2-small: resource capacity failure
europe-north2-c / e2-small: deployed
e2-medium fallback: not used
```

## Megaport validation

Request type: non-billable network-design validation.

```text
location: Equinix Stockholm SK1
HTTP status: 400
message: Validation failed
detail: Missing markets: Sweden
```

No MCR or VXC order was submitted. Megaport commitment is `$0`.

## Terraform closure

```text
terraform fmt -check: pass
terraform validate: pass
terraform plan: no changes
destructive actions during metadata convergence: 0
destructive actions during stop-schedule deployment: 0
```
