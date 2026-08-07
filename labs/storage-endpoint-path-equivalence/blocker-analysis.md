# Blocker analysis — Storage endpoint path equivalence

**Date:** 2026-08-05
**Live state:** Deployed, tests blocked, no cleanup performed

## Root cause

The control is an inherited **Azure Policy with `modify` effect**, not Defender for Storage remediation.

| Evidence | Finding |
|---|---|
| Policy assignment | `MCAPSGovDeployPolicies` / “MCAPSGov Deploy and Modify Policies,” management-group scope, enforcement mode `Default` |
| Policy definition | `StorageAccount_PublicNetwork_Modify` / “SFI - Disable public network access on Storage accounts (excluding NSP configured resources)” |
| Policy operation | If a Storage account has `publicNetworkAccess` other than `Disabled` or `SecuredByPerimeter`, `addOrReplace` it with `Disabled` |
| Compliance | All three deployed Storage accounts are compliant with the modifying policy; no applicable exemption exists |
| Timing | Accounts were created at approximately 16:04:54Z. Policy compliance recorded the public-network modification by 16:29:50Z. A user write at 16:40Z still left the account disabled. |
| Defender timing | `DefenderForStorageSecurityOperator` wrote at 16:43:47Z–16:43:51Z, later than policy enforcement |
| Defender delta | Resource Change History shows that write added the Defender data-scanner resource-access rule. It did **not** change `publicNetworkAccess`. Subsequent Event Grid and Defender-setting writes are consistent with Defender for Storage onboarding. |

This corrects the earlier attribution in `09-public-access-enforcement.json`: that event is real, but it is not the public-access enforcement mechanism.

The policy definition also recognizes an exclusion tag. Applying that tag locally would bypass an organizational control and is **not recommended or authorized**.

## Current deployed state

- VM is running; Private Endpoint connection is approved.
- Target and decoy Storage public network access is `Disabled`.
- Service endpoint is off; service-endpoint policy is detached; private DNS is unlinked.
- Test blobs were not uploaded.
- The target account currently has a resource-level Defender for Storage override disabled, while the other accounts inherit the enabled subscription plan. This is separate from the public-access policy and should not be changed without security/cost approval.
- Resources continue to accrue the approved estimated cost of approximately US$0.15–0.30/hour.

## Can the hypothesis still be tested?

Yes, but not under the current policy evaluation.

### Option A — formal, time-bound policy exemption (recommended)

Have the organizational security/policy owner create a narrowly scoped exemption for `StorageAccount_PublicNetwork_Modify` on the **target and decoy accounts only**, with a short expiry. Then:

1. Restore the approved state with `publicNetworkAccess=Enabled`.
2. Use `defaultAction=Allow` only for the public control and its benchmark windows.
3. Use `defaultAction=Deny` plus the target VNet rule for the service-endpoint correctness stage.
4. Keep shared-key access and anonymous Blob access disabled; retain OAuth/RBAC, the restrictive NSG, and private containers.
5. Restore `publicNetworkAccess=Disabled` and remove/expire the exemptions immediately after validation.

This preserves the approved experiment and adds no Azure resource type. Incremental Azure cost is only the existing lab runtime: roughly US$1.20–3.60 for another 8–12 hours, plus low-volume Storage and logging charges. Allow 20–40 minutes to reconverge/upload after the exemption, 1–2 hours for correctness, and 6–10 hours for the predeclared performance run.

### Option B — target-only exemption and reduced test

Exempt only the target account and run public/service/private correctness plus performance. This tests the core path-equivalence hypothesis but drops the decoy endpoint-policy negative control. It is a material change to the approved evidence plan and still needs approval.

### Option C — Network Security Perimeter

The policy permits `publicNetworkAccess=SecuredByPerimeter`. This is supported, but it is not a drop-in correction: in enforced mode, perimeter access rules become the top-level gate and Storage “allowed networks” rules are bypassed. That changes the service-endpoint authorization experiment and adds a new security architecture. Do not apply without redesign and approval.

### Option D — another PaaS service

Azure SQL, Key Vault, or another service could support public/service/private endpoint comparisons, but each requires new resources, new authorization/telemetry semantics, and confirmation against the same governance baseline. This changes cost and hypothesis scope and is not approved.

## Recommendation and decision request

Do not modify tags, policy, Defender settings, or Storage networking locally.

**Requested approval:** authorize the team to seek a security-owner-created, time-bound (maximum 12 hours) policy exemption for the target and decoy accounts, approve temporary public endpoint exposure under the controls above, and approve restoration of the target account to the subscription-level Defender for Storage configuration. No new billable resources are requested.

Until that approval and exemption exist, S1–S3 and the performance comparison remain blocked. Private-endpoint-only testing would not answer the approved hypothesis.
