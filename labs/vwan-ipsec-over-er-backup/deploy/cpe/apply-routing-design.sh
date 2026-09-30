#!/usr/bin/env bash
set -euo pipefail

design=${1:-}
d1_phase=${2:-private}
case "$design" in
  D1|D2|D3) ;;
  *) echo "Usage: $0 D1|D2|D3 [private|public]" >&2; exit 2 ;;
esac
if [[ "$design" == D1 && "$d1_phase" != private && "$d1_phase" != public ]]; then
  echo "D1 phase must be private or public." >&2
  exit 2
fi

source /etc/vwan-lab/network.env

established_sas() {
  swanctl --list-sas 2>/dev/null |
    sed -nE 's/^(pri0|pri1|pub0|pub1):.*ESTABLISHED.*/\1/p' |
    sort -u
}

expected_sas=$'pri0\npri1\npub0\npub1'
before_sas=$(established_sas)
if [[ "$before_sas" != "$expected_sas" ]]; then
  echo "Refusing routing change: all four IPsec SAs must already be established." >&2
  printf 'Established SAs:\n%s\n' "$before_sas" >&2
  exit 65
fi

for addr in \
  10.250.254.240 10.250.254.241 10.250.254.242 10.250.254.250 \
  169.254.21.6 10.253.1.10 10.253.2.10 10.253.3.10 10.253.3.138; do
  ip address del "$addr/32" dev lo 2>/dev/null || true
done
ip address add 10.250.254.250/32 dev lo
case "$design" in
  D1)
    ip address add 10.250.254.242/32 dev lo
    ip address add 10.253.1.10/32 dev lo
    ;;
  D2)
    ip address add 10.250.254.240/32 dev lo
    ip address add 169.254.21.6/32 dev lo
    ip address add 10.253.2.10/32 dev lo
    ;;
  D3)
    ip address add 10.250.254.240/32 dev lo
    ip address add 10.253.3.10/32 dev lo
    ip address add 10.253.3.138/32 dev lo
    ;;
esac

for peer in "$PRI0_BGP" "$PRI1_BGP" "$PUB0_BGP" "$PUB1_BGP"; do
  ip route del "$peer/32" 2>/dev/null || true
done

public_neighbor_base=""
public_neighbor_instances=""
public_address_family=""
public_policy=""
d3_fallback=""
public_default_peer_drop=""

case "$design" in
  D1)
    local_private=10.250.254.242
    advertised="10.253.1.0/24"
    bgp_peer_elements="$PRI1_BGP"
    if [[ "$d1_phase" == private ]]; then
      ip route replace "$PRI1_BGP/32" dev xfrm-pri1 src "$local_private"
    else
      ip route replace "$PRI1_BGP/32" dev xfrm-pub1 src "$local_private"
    fi
    private_neighbor_instances=" neighbor $PRI1_BGP peer-group PRI"
    ;;
  D2)
    local_private=10.250.254.240
    local_public=169.254.21.6
    advertised="10.253.2.0/24"
    bgp_peer_elements="$PRI0_BGP, $PRI1_BGP, $PUB0_BGP, $PUB1_BGP"
    ip route replace "$PRI0_BGP/32" dev xfrm-pri0 src "$local_private"
    ip route replace "$PRI1_BGP/32" dev xfrm-pri1 src "$local_private"
    ip route replace "$PUB0_BGP/32" dev xfrm-pub0 src "$local_public"
    ip route replace "$PUB1_BGP/32" dev xfrm-pub1 src "$local_public"
    private_neighbor_instances=$(cat <<EOF
 neighbor $PRI0_BGP peer-group PRI
 neighbor $PRI1_BGP peer-group PRI
EOF
)
    public_neighbor_base=$(cat <<EOF
 neighbor PUB peer-group
 neighbor PUB remote-as 65515
 neighbor PUB ebgp-multihop 2
 neighbor PUB update-source $local_public
EOF
)
    public_neighbor_instances=$(cat <<EOF
 neighbor $PUB0_BGP peer-group PUB
 neighbor $PUB1_BGP peer-group PUB
EOF
)
    public_address_family=$(cat <<'EOF'
  neighbor PUB route-map IMPORT-PUB in
  neighbor PUB prefix-list AZURE-IN in
  neighbor PUB prefix-list ACTIVE-OUT out
  neighbor PUB route-map EXPORT-PUB out
EOF
)
    public_policy=$(cat <<'EOF'
route-map IMPORT-PUB permit 10
 set local-preference 100
route-map EXPORT-PUB permit 10
 set as-path prepend 65050 65050 65050
EOF
)
    public_default_peer_drop="iifname { \"xfrm-pub0\", \"xfrm-pub1\" } ip saddr { $PRI0_BGP, $PRI1_BGP } tcp dport 179 drop"
    ;;
  D3)
    local_private=10.250.254.240
    advertised="10.253.3.0/25 10.253.3.128/25"
    bgp_peer_elements="$PRI0_BGP, $PRI1_BGP"
    ip route replace "$PRI0_BGP/32" dev xfrm-pri0 src "$local_private"
    ip route replace "$PRI1_BGP/32" dev xfrm-pri1 src "$local_private"
    private_neighbor_instances=$(cat <<EOF
 neighbor $PRI0_BGP peer-group PRI
 neighbor $PRI1_BGP peer-group PRI
EOF
)
    d3_fallback=$'ip route 10.241.0.0/24 xfrm-pub0 250\nip route 10.241.0.0/24 xfrm-pub1 250'
    ;;
esac

cat >/etc/frr/frr.conf <<EOF
frr version 8.4
frr defaults traditional
hostname cpe-vwan-lab
service integrated-vtysh-config
ip route 10.240.0.0/24 Null0 254
ip route 10.241.0.0/24 Null0 254
$d3_fallback
$(for prefix in $advertised; do echo "ip route $prefix Null0"; done)
router bgp 65050
 bgp router-id 10.250.254.250
 no bgp ebgp-requires-policy
 maximum-paths 2
 neighbor PRI peer-group
 neighbor PRI remote-as 65515
 neighbor PRI ebgp-multihop 2
 neighbor PRI update-source $local_private
$public_neighbor_base
$private_neighbor_instances
$public_neighbor_instances
 address-family ipv4 unicast
$(for prefix in $advertised; do echo "  network $prefix"; done)
  neighbor PRI route-map IMPORT-PRI in
  neighbor PRI prefix-list AZURE-IN in
  neighbor PRI prefix-list ACTIVE-OUT out
$public_address_family
 exit-address-family
ip prefix-list AZURE-IN seq 10 permit 10.240.0.0/24
ip prefix-list AZURE-IN seq 20 permit 10.241.0.0/24
$(i=10; for prefix in $advertised; do echo "ip prefix-list ACTIVE-OUT seq $i permit $prefix"; i=$((i+10)); done)
route-map IMPORT-PRI permit 10
 set local-preference 200
$public_policy
EOF

cat >/etc/nftables.d-vwan-lab.conf <<EOF
table inet vwan_lab {
  set ike_endpoints {
    type ipv4_addr
    elements = { $PRI0_IKE, $PRI1_IKE, $PUB0_IKE, $PUB1_IKE }
  }
  set bgp_peers {
    type ipv4_addr
    elements = { $bgp_peer_elements }
  }
  chain input {
    type filter hook input priority -10; policy accept;
    udp dport { 500, 4500 } ip saddr != @ike_endpoints drop
    ip protocol esp ip saddr != @ike_endpoints drop
    $public_default_peer_drop
    tcp dport 179 ip saddr != @bgp_peers drop
  }
}
EOF
nft delete table inet vwan_lab 2>/dev/null || true
nft -f /etc/nftables.d-vwan-lab.conf
systemctl restart frr
systemctl is-active --quiet frr

after_sas=$(established_sas)
if [[ "$after_sas" != "$expected_sas" ]]; then
  echo "IPsec changed during routing-only transition." >&2
  printf 'Established SAs after change:\n%s\n' "$after_sas" >&2
  exit 66
fi

logger -t vwan-lab "Applied routing-only $design configuration (D1 phase: $d1_phase); IPsec unchanged"
printf 'ROUTING_DESIGN=%s\nD1_PHASE=%s\nIPSEC_UNCHANGED=true\n' "$design" "$d1_phase"
