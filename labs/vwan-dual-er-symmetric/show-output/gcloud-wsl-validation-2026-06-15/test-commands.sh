#!/bin/bash

# §8.4 — Learned routes per peer with AS path
echo "=== §8.4 — Learned routes per peer with AS path ==="
gcloud compute routers get-status router-vwan-symm-a --region=europe-west3 --format=json | \
  jq -r '.result.bgpPeerStatus[] | .name as $peer | .learnedRoutes[]? | [$peer, .destRange, .routeType, .nextHopIp, (.asPath | @json // "-")] | @tsv'

echo ""
echo "=== §8.5 — BGP peer status ==="
# §8.5 — BGP peer status (up/down, uptime, counters)
gcloud compute routers get-status router-vwan-symm-a --region=europe-west3 --format=json | \
  jq -r '.result.bgpPeerStatus[] | [.name, .ipAddress, (.peerIpAddress // "-"), .status, .state, (.uptime // "-"), (.numLearnedRoutes|tostring)] | @tsv'

echo ""
echo "=== §8.6 — Routes advertised to a specific peer ==="
# §8.6 — Routes advertised to a specific peer
PEER_NAME=$(gcloud compute routers get-status router-vwan-symm-a --region=europe-west3 --format=json | jq -r '.result.bgpPeerStatus[0].name')
gcloud compute routers get-status router-vwan-symm-a --region=europe-west3 --format=json | \
  jq -r --arg peer "$PEER_NAME" '.result.bgpPeerStatus[] | select(.name==$peer) | .advertisedRoutes[]? | [.destRange, (.asPath | @json // "-")] | @tsv'

echo ""
echo "=== §9.1 — List Interconnect attachments ==="
# §9.1 — List Interconnect attachments
gcloud compute interconnects attachments list --format="table(name, region, type, edgeAvailabilityDomain, state, pairingKey)"

echo ""
echo "=== §9.2 — One attachment in detail ==="
# §9.2 — One attachment in detail
gcloud compute interconnects attachments describe att-vwan-symm-a --region=europe-west3 --format=json | \
  jq '{name, state, type, bandwidth, pairingKey, vlanTag8021q, cloudRouterIpAddress, customerRouterIpAddress, partnerAsn}'

echo ""
echo "=== §9.3 — Effective VPC routes (fixed placeholder) ==="
# §9.3 — Effective VPC routes (with CORRECT VPC name)
gcloud compute routes list --filter="network:vpc-vwan-symm-a-103167" --format="table(name, destRange, nextHopIp, nextHopGateway.basename(), nextHopVpnTunnel.basename(), priority)" | head -20

echo ""
echo "=== §9.4 — Firewalls applied to a VM ==="
# §9.4 — Firewalls applied to a VM
gcloud compute instances get-effective-firewalls vm-vwan-symm-a --zone=europe-west3-a --format=json | jq '.firewallPolicys[0:2]'

echo ""
echo "=== VPC routing mode check ==="
# Verify routing mode
gcloud compute networks describe vpc-vwan-symm-a-103167 --format='value(routingConfig.routingMode)'
