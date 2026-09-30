#!/usr/bin/env bash
set -euo pipefail

action=${1:?apply or restore}
backup=/opt/vwan-lab/d2-core-backup-20260929T080133Z

capture_state() {
  echo "===UTC=$(date -u +%FT%TZ)==="
  echo ===ADDR===
  ip -4 addr show lo
  echo ===ROUTES===
  ip -4 route
  echo ===SAS===
  swanctl --list-sas
  echo ===BGP===
  vtysh -c 'show bgp ipv4 unicast summary'
  echo ===BGP_D2_PREFIX===
  vtysh -c 'show bgp ipv4 unicast 10.253.2.0/24'
  echo ===BGP_AZURE_PREFIX===
  vtysh -c 'show bgp ipv4 unicast 10.241.0.0/24'
  echo ===KERNEL_AZURE_PREFIX===
  ip -4 route show 10.241.0.0/24
}

case "$action" in
  apply)
    install -d -m 0700 "$backup"
    cp -a /etc/frr/frr.conf "$backup/frr.conf"
    cp -a /etc/nftables.d-vwan-lab.conf "$backup/nftables.d-vwan-lab.conf"
    ip -4 route >"$backup/routes.txt"

    ip route del 169.254.21.1/32 2>/dev/null || true
    ip route del 169.254.22.1/32 2>/dev/null || true
    ip route replace 10.240.0.12/32 dev xfrm-pri0 src 10.250.254.240
    ip route replace 10.240.0.13/32 dev xfrm-pri1 src 10.250.254.240
    ip route replace 169.254.21.5/32 dev xfrm-pub0 src 169.254.21.6
    ip route replace 169.254.22.5/32 dev xfrm-pub1 src 169.254.21.6

    sed -i \
      -e 's/neighbor 169\.254\.21\.1 peer-group PRI/neighbor 10.240.0.12 peer-group PRI/' \
      -e 's/neighbor 169\.254\.22\.1 peer-group PRI/neighbor 10.240.0.13 peer-group PRI/' \
      /etc/frr/frr.conf

    cat >/etc/nftables.d-vwan-lab.conf <<'EOF'
table inet vwan_lab {
  set ike_endpoints {
    type ipv4_addr
    elements = { 10.240.0.4, 10.240.0.5, 74.158.47.254, 74.158.80.26 }
  }
  set bgp_peers {
    type ipv4_addr
    elements = { 10.240.0.12, 10.240.0.13, 169.254.21.5, 169.254.22.5 }
  }
  chain input {
    type filter hook input priority -10; policy accept;
    iifname { "xfrm-pub0", "xfrm-pub1" } ip saddr { 10.240.0.12, 10.240.0.13 } tcp dport 179 counter drop
    udp dport { 500, 4500 } ip saddr != @ike_endpoints drop
    ip protocol esp ip saddr != @ike_endpoints drop
    tcp dport 179 ip saddr != @bgp_peers drop
  }
}
EOF
    nft delete table inet vwan_lab 2>/dev/null || true
    nft -f /etc/nftables.d-vwan-lab.conf

    timeout 150 tcpdump -l -nn -tttt -i any \
      'tcp port 179 and (host 169.254.21.5 or host 169.254.22.5)' \
      >"$backup/public-bgp-capture.txt" 2>&1 &
    capture_pid=$!
    systemctl restart frr
    for _ in $(seq 1 30); do
      established=$(vtysh -c 'show bgp ipv4 unicast summary' | awk '$1 ~ /^(10\.240\.0\.12|10\.240\.0\.13|169\.254\.21\.5|169\.254\.22\.5)$/ && $10 ~ /^[0-9]+$/ {n++} END {print n+0}')
      [[ "$established" -eq 4 ]] && break
      sleep 5
    done
    wait "$capture_pid" || true
    capture_state
    echo ===PUBLIC_BGP_CAPTURE===
    cat "$backup/public-bgp-capture.txt"
    ;;
  restore)
    test -d "$backup"
    cp -a "$backup/frr.conf" /etc/frr/frr.conf
    cp -a "$backup/nftables.d-vwan-lab.conf" /etc/nftables.d-vwan-lab.conf
    ip route del 10.240.0.12/32 2>/dev/null || true
    ip route del 10.240.0.13/32 2>/dev/null || true
    ip route replace 169.254.21.1/32 dev xfrm-pri0 src 10.250.254.240
    ip route replace 169.254.22.1/32 dev xfrm-pri1 src 10.250.254.240
    ip route replace 169.254.21.5/32 dev xfrm-pub0 src 169.254.21.6
    ip route replace 169.254.22.5/32 dev xfrm-pub1 src 169.254.21.6
    nft delete table inet vwan_lab 2>/dev/null || true
    nft -f /etc/nftables.d-vwan-lab.conf
    systemctl restart frr
    capture_state
    ;;
  *)
    exit 2
    ;;
esac
