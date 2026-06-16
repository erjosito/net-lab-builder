#!/bin/bash

# §8.4 — Learned routes per peer with AS path
echo "=== SECTION 8.4 — Learned routes per peer with AS path ==="
gcloud compute routers get-status router-vwan-symm-a --region=europe-west3 --format=json | jq -r '.result.bgpPeerStatus[] | .name as $peer | .learnedRoutes[]? | [$peer, .destRange, .routeType, .nextHopIp, (.asPath | @json // "-")] | @tsv' 2>&1

echo ""
echo "=== SECTION 8.5 — BGP peer status ==="
gcloud compute routers get-status router-vwan-symm-a --region=europe-west3 --format=json | jq -r '.result.bgpPeerStatus[] | [.name, .ipAddress, (.peerIpAddress // "-"), .status, .state, (.uptime // "-"), (.numLearnedRoutes|tostring)] | @tsv' 2>&1

echo ""
echo "=== SECTION 8.6 — Routes advertised to a specific peer ==="
PEER_NAME=$(gcloud compute routers get-status router-vwan-symm-a --region=europe-west3 --format=json | jq -r '.result.bgpPeerStatus[0].name')
echo "Peer: $PEER_NAME"
gcloud compute routers get-status router-vwan-symm-a --region=europe-west3 --format=json | jq -r --arg peer "$PEER_NAME" '.result.bgpPeerStatus[] | select(.name==$peer) | .advertisedRoutes[]? | [.destRange, (.asPath | @json // "-")] | @tsv' 2>&1

echo ""
echo "=== SECTION 9.2 — One attachment in detail ==="
gcloud compute interconnects attachments describe att-vwan-symm-a --region=europe-west3 --format=json | jq '{name, state, type, bandwidth, pairingKey, vlanTag8021q, cloudRouterIpAddress, customerRouterIpAddress, partnerAsn}' 2>&1

echo ""
echo "=== SECTION 9.3 — Effective VPC routes (FIXED: vpc-vwan-symm-a-103167 not vpc-onprem) ==="
gcloud compute routes list --filter="network:vpc-vwan-symm-a-103167" --format="table(name, destRange, nextHopIp, nextHopGateway.basename(), priority)" 2>&1 | head -10

echo ""
echo "=== VPC routing mode ==="
gcloud compute networks describe vpc-vwan-symm-a-103167 --format='value(routingConfig.routingMode)'