#!/usr/bin/env bash
set -euo pipefail
action=${1:?action required}
# shellcheck disable=SC1091
source /etc/vwan-lab/network.env

case "$DESIGN" in
  D1) workload_targets="10.253.1.10" ;;
  D2) workload_targets="10.253.2.10" ;;
  D3) workload_targets="10.253.3.10, 10.253.3.138" ;;
  *) echo "unsupported design in network.env" >&2; exit 2 ;;
esac

peer_for_dev() {
  ip -4 route show dev "$1" | awk '$1 !~ /\// || $1 ~ /\/32$/ { print $1; exit }'
}

set_neighbor_state() {
  local peer=$1 state=$2
  if [[ -n "$peer" ]]; then
    if [[ "$state" == shutdown ]]; then
      vtysh -c conf -c 'router bgp 65050' -c "neighbor $peer shutdown"
    else
      vtysh -c conf -c 'router bgp 65050' -c "no neighbor $peer shutdown"
    fi
  fi
}

pri0=$(peer_for_dev xfrm-pri0)
pri1=$(peer_for_dev xfrm-pri1)
pub0=$(peer_for_dev xfrm-pub0)
pub1=$(peer_for_dev xfrm-pub1)

case "$action" in
  stop-pri0)
    swanctl --terminate --child pri0 || true
    set_neighbor_state "$pri0" shutdown
    ;;
  stop-private)
    swanctl --terminate --child pri0 || true
    swanctl --terminate --child pri1 || true
    set_neighbor_state "$pri0" shutdown
    set_neighbor_state "$pri1" shutdown
    ;;
  stop-public)
    swanctl --terminate --child pub0 || true
    swanctl --terminate --child pub1 || true
    set_neighbor_state "$pub0" shutdown
    set_neighbor_state "$pub1" shutdown
    ;;
  stop-bgp-pri0)
    set_neighbor_state "$pri0" shutdown
    ;;
  stop-bgp-private)
    set_neighbor_state "$pri0" shutdown
    set_neighbor_state "$pri1" shutdown
    ;;
  restore-bgp-pri0)
    set_neighbor_state "$pri0" no-shutdown
    ;;
  restore-bgp-private)
    set_neighbor_state "$pri0" no-shutdown
    set_neighbor_state "$pri1" no-shutdown
    ;;
  block-public)
    nft delete table inet vwan_public_fault 2>/dev/null || true
    nft -f - <<EOF
table inet vwan_public_fault {
  chain output {
    type filter hook output priority -20; policy accept;
    ip daddr { $PUB0_IKE, $PUB1_IKE } udp dport { 500, 4500 } counter drop
    ip daddr { $PUB0_IKE, $PUB1_IKE } ip protocol esp counter drop
  }
}
EOF
    ;;
  restore-public)
    nft delete table inet vwan_public_fault 2>/dev/null || true
    ;;
  drop-workload)
    nft delete table inet vwan_workload_fault 2>/dev/null || true
    nft -f - <<EOF
table inet vwan_workload_fault {
  set targets {
    type ipv4_addr
    elements = { $workload_targets }
  }
  chain input {
    type filter hook input priority -20; policy accept;
    ip saddr 10.241.0.4 ip daddr @targets icmp type echo-request counter drop
    ip saddr 10.241.0.4 ip daddr @targets tcp dport 8080 counter drop
  }
  chain output {
    type filter hook output priority -20; policy accept;
    ip saddr @targets ip daddr 10.241.0.4 icmp type echo-request counter drop
    ip saddr @targets ip daddr 10.241.0.4 tcp dport 8080 counter drop
  }
}
EOF
    ;;
  show-workload-drop)
    nft list table inet vwan_workload_fault
    ;;
  restore-workload)
    nft delete table inet vwan_workload_fault 2>/dev/null || true
    ;;
  d1-private)
    swanctl --terminate --child pub0 || true
    swanctl --terminate --child pub1 || true
    set_neighbor_state "$pub0" shutdown
    set_neighbor_state "$pub1" shutdown
    set_neighbor_state "$pri0" no-shutdown
    set_neighbor_state "$pri1" no-shutdown
    swanctl --initiate --child pri0
    swanctl --initiate --child pri1
    ;;
  d1-public)
    swanctl --terminate --child pri0 || true
    swanctl --terminate --child pri1 || true
    set_neighbor_state "$pri0" shutdown
    set_neighbor_state "$pri1" shutdown
    set_neighbor_state "$pub0" no-shutdown
    set_neighbor_state "$pub1" no-shutdown
    swanctl --initiate --child pub0
    swanctl --initiate --child pub1
    ;;
  stop-strongswan) systemctl stop strongswan ;;
  restore)
    nft delete table inet vwan_public_fault 2>/dev/null || true
    nft delete table inet vwan_workload_fault 2>/dev/null || true
    systemctl restart vwan-lab-network strongswan vwan-lab-ipsec frr
    if [[ "$DESIGN" == D1 && "$D1_PHASE" == private ]]; then
      "$0" d1-private
    elif [[ "$DESIGN" == D1 && "$D1_PHASE" == public ]]; then
      "$0" d1-public
    else
      set_neighbor_state "$pri0" no-shutdown
      set_neighbor_state "$pri1" no-shutdown
      set_neighbor_state "$pub0" no-shutdown
      set_neighbor_state "$pub1" no-shutdown
      swanctl --initiate --child pri0 || true
      swanctl --initiate --child pri1 || true
      swanctl --initiate --child pub0 || true
      swanctl --initiate --child pub1 || true
    fi
    ;;
  *) echo "unknown action" >&2; exit 2 ;;
esac
