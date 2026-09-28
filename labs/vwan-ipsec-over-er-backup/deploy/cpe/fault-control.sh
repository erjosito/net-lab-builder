#!/usr/bin/env bash
set -euo pipefail
action=${1:?action required}

peer_for_dev() {
  ip -4 route show dev "$1" | awk 'NR == 1 { print $1; exit }'
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
  stop-strongswan) systemctl stop strongswan ;;
  restore)
    systemctl restart vwan-lab-network strongswan frr
    set_neighbor_state "$pri0" no-shutdown
    set_neighbor_state "$pri1" no-shutdown
    set_neighbor_state "$pub0" no-shutdown
    set_neighbor_state "$pub1" no-shutdown
    swanctl --load-all
    swanctl --initiate --child pri0 || true
    swanctl --initiate --child pri1 || true
    swanctl --initiate --child pub0 || true
    swanctl --initiate --child pub1 || true
    ;;
  *) echo "unknown action" >&2; exit 2 ;;
esac
