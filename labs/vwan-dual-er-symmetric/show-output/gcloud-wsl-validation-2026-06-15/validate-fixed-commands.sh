#!/bin/bash

export YOUR_VPC="vpc-vwan-symm-a-103167"
export ROUTER_A="router-vwan-symm-a"
export REGION_A="europe-west3"
export YOUR_ATTACHMENT_NAME="att-vwan-symm-a"
export YOUR_BGP_PEER_NAME="auto-ia-bgp-att-vwan-symm-a-748c416bf214189"

echo "=================================================================================="
echo "Testing FIXED gcloud commands from sections 8-9"
echo "=================================================================================="
echo ""

echo "§8.1: List routers"
gcloud compute routers list --filter="region:$REGION_A" --format="table(name, region, network.basename(), bgp.asn)"
echo ""

echo "§8.2: Router config"
gcloud compute routers describe $ROUTER_A --region=$REGION_A --format=json | jq "{name, asn:.bgp.asn, advertiseMode:.bgp.advertiseMode, advertisedRanges:.bgp.advertisedIpRanges, peers:[.bgpPeers[].name]}"
echo ""

echo "§8.3: Best routes"
gcloud compute routers get-status $ROUTER_A --region=$REGION_A --format=json | jq -r ".result.bestRoutesForRouter[] | [.destRange, .routeType, .nextHopIp, (.priority|tostring)] | @tsv"
echo ""

echo "§8.4: Learned routes per peer (AS path)"
gcloud compute routers get-status $ROUTER_A --region=$REGION_A --format=json | jq -r ".result.bgpPeerStatus[] | .name as \$peer | .learnedRoutes[]? | [\$peer, .destRange, .routeType, .nextHopIp, (.asPath | @json // \"-\")] | @tsv"
echo "(Empty output is normal if no learned routes yet)"
echo ""

echo "§8.5: BGP peer status"
gcloud compute routers get-status $ROUTER_A --region=$REGION_A --format=json | jq -r ".result.bgpPeerStatus[] | [.name, .ipAddress, (.peerIpAddress // \"-\"), .status, .state, (.uptime // \"-\"), (.numLearnedRoutes|tostring)] | @tsv"
echo ""

echo "§8.6: Routes advertised to peer"
gcloud compute routers get-status $ROUTER_A --region=$REGION_A --format=json | jq -r ".result.bgpPeerStatus[] | select(.name==\"$YOUR_BGP_PEER_NAME\") | .advertisedRoutes[]? | [.destRange, (.asPath | @json // \"-\")] | @tsv"
echo ""

echo "§9.1: List attachments"
gcloud compute interconnects attachments list --format="table(name, region, type, edgeAvailabilityDomain, state, pairingKey)"
echo ""

echo "§9.2: One attachment in detail"
gcloud compute interconnects attachments describe $YOUR_ATTACHMENT_NAME --region=$REGION_A --format=json | jq "{name, state, type, bandwidth, pairingKey, vlanTag8021q, cloudRouterIpAddress, customerRouterIpAddress, partnerAsn}"
echo ""

echo "§9.3: Effective VPC routes (FIXED!)"
gcloud compute routes list --filter="network:$YOUR_VPC" --format="table(name, destRange, nextHopIp, nextHopGateway.basename(), nextHopVpnTunnel.basename(), priority)"
echo ""

echo "§9.4: Firewalls on VPC (FIXED - now lists firewall rules)"
gcloud compute firewall-rules list --filter="network:$YOUR_VPC" --format="table(name, direction, priority, sourceRanges[0], targetTags[0], allowed[0].map().firewall_rule())"
echo ""

echo "§9 Gotcha: Check VPC routing mode"
gcloud compute networks describe $YOUR_VPC --format="value(routingConfig.routingMode)"
echo ""
