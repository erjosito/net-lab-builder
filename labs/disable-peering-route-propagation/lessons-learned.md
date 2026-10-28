# Lessons Learned: Disable Peering Route Propagation (`disablePeeringRoute`)

1. **`Microsoft.Network/AllowDisablePeeringRoutes` requires manual PG approval (`ApprovalRequired`):**
   - Although the public documentation states `Register-AzProviderFeature -FeatureName AllowDisablePeeringRoutes -ProviderNamespace Microsoft.Network` can take up to 15 minutes, inspecting the ARM feature registration object (`az feature registration show --provider-namespace Microsoft.Network --name AllowDisablePeeringRoutes`) reveals `"approvalType": "ApprovalRequired"`.
   - Until approved by the product team, attempting `az network route-table update --disable-peering-route All` fails with `Code: UnauthorizedClientApplication` (`Message: Unauthorized client application id DisablePeeringRoute is not supported.`).

2. **How to inspect `GatewaySubnet` effective routes via a shared route table (`snet-hub-probe`):**
   - Azure does not expose `az network nic show-effective-route-table` for the internal NICs of a managed VPN or ExpressRoute Gateway (`vpngw-hub`, `ergw-hub`).
   - Attaching the exact same route table (`rt-gw`) to the hub SD-WAN / probe subnet (`snet-hub-probe`, `nic-vm-hub-probe`) gives an exact, deterministic view of the system `VNetPeering`, `VirtualNetworkGateway`, and `User` routes evaluated by `rt-gw`.

3. **Why a single `10.0.0.0/8` summary route on `rt-gw` fails across all 3 hybrid paths (S2S VPN, SD-WAN, ExpressRoute) without `disablePeeringRoute = All`:**
   - With `rt-gw` holding only `10.0.0.0/8 -> 10.0.1.4` and `disablePeeringRoute = None`, all 10 `/16` `VNetPeering` routes (`10.1.0.0/16` .. `10.10.0.0/16`) remain `Active` and win by Longest Prefix Match over `10.0.0.0/8`.
   - Consequently, packets arriving via S2S VPN (`vpngw-hub`), ExpressRoute (`ergw-hub`), or the Hub SD-WAN appliance (`vm-hub-probe` in `snet-hub-probe`) are all routed directly to `vm-spoke1` (`10.1.1.4`), bypassing `vm-hub-nva` (`10.0.1.4`) on the forward path while return packets from `vm-spoke1` traverse `vm-hub-nva` (`0` forward packets vs `8` return packets per flow).

4. **Megaport VXC API schema (`PUT /v3/product/vxc/{uid}`) for injecting static routes into MCR BGP:**
   - When updating an existing MCR VXC via `PUT /v3/product/vxc/{uid}`, the Megaport v3 API expects `"aEndConfig"` (not `"aEndPartnerConfig"`, which is only used in `POST /v3/networkdesign/buy`) and `"exportWhitelist": <prefixListId>` inside `bgpConnections`.
   - Adding a secondary interface IP (`172.18.1.1/30`) to `interfaces[0].ipAddresses` on the MCR VXC makes next-hop `172.18.1.2` resolvable for a static route (`172.18.0.0/16 -> 172.18.1.2`) in `ipRoutes`, which the MCR automatically redistributes into eBGP (`path: 65030 ?`) toward Azure MSEE and `ergw-hub`.

5. **NSG outbound rules for customer-managed SD-WAN NVAs in Azure:**
   - Unlike prefixes learned by an Azure `VirtualNetworkGateway` (which Azure automatically adds to the `VirtualNetwork` service tag), remote on-premises prefixes behind a customer Linux SD-WAN VM (`172.17.0.0/16` behind `vm-hub-probe`) are **not** included in the `VirtualNetwork` service tag.
   - When `vm-hub-probe` forwards packets from `172.17.1.4` (not `VirtualNetwork`) to `10.1.1.4` (`VirtualNetwork`), the packet does not match `AllowVnetOutBound` (`VirtualNetwork -> VirtualNetwork`) or `AllowInternetOutBound` (`* -> Internet`). An explicit outbound RFC1918 allow rule (`AllowRFC1918Out`) is required on the NSG.

6. **StrongSwan IKEv2 proposal matching and responder settings:**
   - Against Azure `VpnGw1AZ`, allowing `ike=aes256-sha256-modp1024,aes256-sha1-modp1024,aes256-sha256-modp2048` and `esp=aes256-sha256,aes256-sha1,aes256gcm16` avoids `NO_PROPOSAL_CHOSEN`.
   - Between two Linux StrongSwan XFRM appliances (`vm-hub-probe` <-> `vm-onprem-sdwan`), configure `start_action = trap|start` on the initiator (`vm-hub-probe`) and `start_action = none` on the responder (`vm-onprem-sdwan`) to prevent duplicate overlapping Child SAs, and set `krt_prefsrc = 172.17.1.4;` in BIRD's `kernel` protocol export filter so locally originated traffic from the on-premises appliance uses its LAN IP rather than `169.254.20.2`.
