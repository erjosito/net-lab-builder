# Lessons Learned: Disable Peering Route Propagation (`disablePeeringRoute`)

1. **`Microsoft.Network/AllowDisablePeeringRoutes` requires manual PG approval (`ApprovalRequired`):**
   - Although the public documentation states `Register-AzProviderFeature -FeatureName AllowDisablePeeringRoutes -ProviderNamespace Microsoft.Network` can take up to 15 minutes, inspecting the ARM feature registration object (`az feature registration show --provider-namespace Microsoft.Network --name AllowDisablePeeringRoutes`) reveals `"approvalType": "ApprovalRequired"`.
   - Until approved by the product team, attempting `az network route-table update --disable-peering-route All` fails with `Code: UnauthorizedClientApplication` (`Message: Unauthorized client application id DisablePeeringRoute is not supported.`).

2. **How to inspect `GatewaySubnet` effective routes via a probe NIC (`snet-hub-probe`):**
   - Azure does not expose `az network nic show-effective-route-table` for the internal NICs of a managed VPN Gateway (`vpngw-hub`).
   - Attaching the exact same route table (`rt-gw`) to a dedicated `/24` probe subnet (`snet-hub-probe`) with a lightweight VM (`vm-hub-probe`) gives an exact, deterministic view of the system `VNetPeering`, `VirtualNetworkGateway`, and `User` routes evaluated by `rt-gw`.

3. **Why `tcpdump` on a single-NIC Azure Linux NVA misses asymmetric forward bypass but sees return traffic:**
   - In Scenario S1 (`disablePeeringRoute = None` with only `10.0.0.0/8 -> 10.0.1.4` on `rt-gw`), `vpngw-hub` matches the more specific `/16` `VNetPeering` route (`10.1.0.0/16`) and forwards `172.16.1.4 -> 10.1.1.4` packets directly to `vm-spoke1`.
   - Using directional `iptables -A FORWARD` rules with `LOG` and `conntrack` on `vm-hub-nva` (`10.0.1.4`) cleanly separates `172.16.0.0/16 -> 10.0.0.0/8` (`0 packets` in S1) from `10.0.0.0/8 -> 172.16.0.0/16` (`8 packets` in S1 stateless; `11 packets` dropped as `ctstate INVALID` in S1 stateful).

4. **StrongSwan IKEv2 proposal matching with Azure `VpnGw1AZ` default policy:**
   - Strict `ike=aes256-sha256-modp2048!` with the exclamation mark (`!`) caused `NO_PROPOSAL_CHOSEN` against default `VpnGw1AZ` responder settings; allowing `ike=aes256-sha256-modp1024,aes256-sha1-modp1024,aes256-sha256-modp2048` and `esp=aes256-sha256,aes256-sha1,aes256gcm16` negotiated `AES_CBC_256/HMAC_SHA1_96/MODP_1024` (IKEv2) and `AES_GCM_16_256` (ESP) immediately.
