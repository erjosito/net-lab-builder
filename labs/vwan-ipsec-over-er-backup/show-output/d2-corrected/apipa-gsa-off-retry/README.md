# APIPA correction retry after local GSA disablement

**Correlation:** `apipa-gsa-off-retry-20260928-01`

**Result:** failed the same Azure BGP-source acceptance condition and rolled back once. No further retry or fault validation is authorized.

## Baseline

- Local WSL execution returned `WSL_OK`, resolved `management.azure.com`, and did not emit the Global Secure Access DNS-tunneling warning seen during the first attempt.
- Azure VPN gateway, public/private sites and connection mappings matched the prior rolled-back state.
- Four IKEv2/ESP SAs were established.
- ExpressRoute provider state was `Provisioned`, private peering was `Succeeded`, GCP Partner BGP was Up, and all Megaport products were live.
- The authenticated Terraform baseline reported no changes.

## Clean repeat

The repeat used only the previously successful operation forms:

1. add `169.254.22.2` and `.3` to the gateway without removing existing custom addresses;
2. update the complete parent VPN Site body so the public CPE peer is `169.254.22.1`;
3. update the public connection to select `.22.2/.3` while retaining the existing PSK;
4. apply the reviewed CPE APIPA loopback, source-specific XFRM routes, FRR neighbors and filter changes without restarting StrongSwan.

All four SAs remained established through every mutation.

## Acceptance result

After the single 60-second convergence window:

```text
10.240.0.12     Established, 2 prefixes received
10.240.0.13     Established, 2 prefixes received
169.254.22.2    Connect, 0 messages received
169.254.22.3    Connect, 0 messages received
```

The four route lookups were correct, and the vWAN site/connection/gateway objects persisted the intended APIPA values. Concurrent captures on `xfrm-pri0`, `xfrm-pri1`, `xfrm-pub0`, and `xfrm-pub1` nevertheless showed public TCP/179 sourced from Azure defaults `10.240.0.12/.13` toward CPE APIPA `169.254.22.1`. No Azure BGP traffic sourced from `169.254.22.2/.3` was observed.

This met the explicit rollback condition.

### Mandatory TCP/179 response question

Offline analysis of the existing bounded capture confirms that the CPE initiated TCP/179 to both custom peers:

- `.22.2`: initial SYN plus one same-sequence retransmission 32.255850 seconds later;
- `.22.3`: initial SYN plus one same-sequence retransmission 32.256023 seconds later.

Neither custom peer returned a SYN-ACK or RST. During the same window, Azure repeatedly initiated TCP/179 from `.13` on the `.22.2` path and `.12` on the `.22.3` path. See `acceptance/tcp179-apipa-response-analysis.md`.

The reviewed capture included TCP flags and sequence/acknowledgement values, but the bounded command did not enable or collect FRR event/debug logs. Those historical daemon events are unrecoverable after rollback without an unauthorized retry; this is recorded as an explicit evidence gap.

## Rollback and closure

- Restored the original public connection mappings and regular-private site peer.
- Restored the original CPE loopback, XFRM routes, FRR neighbors and nftables state.
- Removed only the two retry-added gateway custom addresses.
- Verified four established SAs and the original CPE routes/neighbors.
- Verified ER provider `Provisioned`, Azure private peering `Succeeded`, and GCP Partner BGP Up.
- A full authenticated Terraform plan reported no changes.

## GSA assessment

Disabling local Global Secure Access changed the local WSL symptom: the prior DNS-tunneling warning disappeared and name resolution succeeded. It did **not** change the observed API/CLI operation success or session outcome:

- the same corrected Azure REST `PUT` operations succeeded without authentication or transport errors;
- the gateway update succeeded but took 57m36s, longer than the first attempt; rollback took 14m15s;
- Azure still initiated public BGP from defaults `.12/.13`, while the custom sessions did not establish, exactly matching the first attempt.

The evidence therefore does not support GSA as the cause. It also does not establish a platform limitation: the configuration/API association is unresolved pending Trinity review. See `api-association-review.md` for API-version coverage, ordering and evidence gaps.
