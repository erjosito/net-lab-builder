#!/usr/bin/env bash
set -euo pipefail

runtime=/run/vwan-lab/runtime.env
test -f "$runtime"
# shellcheck disable=SC1090
source "$runtime"
: "${PUB0_BGP:=}"
: "${PUB1_BGP:=}"
: "${D1_PHASE:=private}"

case "$DESIGN" in
  D1)
    local_private=10.250.254.242
    local_public=10.250.254.242
    advertised=10.253.1.0/24
    public_prepend=""
    d3_fallback=""
    public_bgp_enabled=true
    if [[ "$D1_PHASE" == private ]]; then
      private_start_action=start
      public_start_action=none
      private_neighbor_shutdown=false
      public_neighbor_shutdown=true
    elif [[ "$D1_PHASE" == public ]]; then
      private_start_action=none
      public_start_action=start
      private_neighbor_shutdown=true
      public_neighbor_shutdown=false
    else
      echo "D1_PHASE must be private or public" >&2
      exit 2
    fi
    ;;
  D2)
    local_private=10.250.254.240
    local_public=10.250.254.241
    advertised=10.253.2.0/24
    public_prepend="set as-path prepend 65050 65050 65050"
    d3_fallback=""
    public_bgp_enabled=true
    private_start_action=start
    public_start_action=start
    private_neighbor_shutdown=false
    public_neighbor_shutdown=false
    ;;
  D3)
    local_private=10.250.254.240
    local_public=10.250.254.241
    advertised="10.253.3.0/25 10.253.3.128/25"
    public_prepend=""
    d3_fallback=$'ip route 10.241.0.0/24 xfrm-pub0 250\nip route 10.241.0.0/24 xfrm-pub1 250'
    public_bgp_enabled=false
    private_start_action=start
    public_start_action=start
    private_neighbor_shutdown=false
    public_neighbor_shutdown=false
    ;;
  *) exit 2 ;;
esac

install -d -m 0700 /etc/swanctl/conf.d /opt/vwan-lab /var/log/vwan-lab
install -d -m 0700 /etc/vwan-lab

cat >/etc/vwan-lab/network.env <<EOF
DESIGN=$DESIGN
D1_PHASE=$D1_PHASE
PRI0_IKE=$PRI0_IKE
PRI1_IKE=$PRI1_IKE
PUB0_IKE=$PUB0_IKE
PUB1_IKE=$PUB1_IKE
PRI0_BGP=$PRI0_BGP
PRI1_BGP=$PRI1_BGP
PUB0_BGP=$PUB0_BGP
PUB1_BGP=$PUB1_BGP
EOF

cat >/etc/systemd/system/vwan-lab-ipsec.service <<'EOF'
[Unit]
Description=Load vWAN lab StrongSwan connections
After=vwan-lab-network.service strongswan.service
Requires=vwan-lab-network.service strongswan.service
Before=frr.service

[Service]
Type=oneshot
ExecStart=/usr/sbin/swanctl --load-all
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
chmod 0600 /etc/vwan-lab/network.env

cat >/usr/local/sbin/vwan-lab-network <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
source /etc/vwan-lab/network.env

for addr in 10.250.254.240 10.250.254.241 10.250.254.242 10.250.254.250; do
  ip address replace "$addr/32" dev lo
done

for spec in pri0:410 pri1:411 pub0:420 pub1:421; do
  name=${spec%%:*}; id=${spec##*:}
  ip link del "xfrm-$name" 2>/dev/null || true
  ip link add "xfrm-$name" type xfrm dev ens4 if_id "$id"
  ip link set "xfrm-$name" up
done

ip route replace "$PRI0_IKE/32" via 10.250.0.1 dev ens4 metric 5
ip route replace "$PRI1_IKE/32" via 10.250.0.1 dev ens4 metric 5
ip route replace "$PUB0_IKE/32" via 10.250.0.1 dev ens4 metric 5
ip route replace "$PUB1_IKE/32" via 10.250.0.1 dev ens4 metric 5
ip route replace "$PRI0_BGP/32" dev xfrm-pri0
ip route replace "$PRI1_BGP/32" dev xfrm-pri1
if [[ "$DESIGN" != D3 ]]; then
  ip route replace "$PUB0_BGP/32" dev xfrm-pub0
  ip route replace "$PUB1_BGP/32" dev xfrm-pub1
fi
EOF
chmod 0700 /usr/local/sbin/vwan-lab-network

cat >/etc/systemd/system/vwan-lab-network.service <<'EOF'
[Unit]
Description=vWAN lab XFRM interfaces and endpoint routes
After=network-online.target
Wants=network-online.target
Before=strongswan.service frr.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/vwan-lab-network
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/strongswan.d/charon/90-vwan-lab.conf <<'EOF'
charon {
  install_routes = no
}
EOF

cat >/etc/swanctl/conf.d/vwan.conf <<EOF
connections {
  pri0 { version=2; local_addrs=10.250.0.10; remote_addrs=$PRI0_IKE; proposals=aes256-sha256-modp2048; local { auth=psk; id=10.250.0.10; }; remote { auth=psk; id=$PRI0_IKE; }; children { pri0 { local_ts=0.0.0.0/0; remote_ts=0.0.0.0/0; if_id_in=410; if_id_out=410; esp_proposals=aes256-sha256; start_action=$private_start_action; dpd_action=restart; } } }
  pri1 { version=2; local_addrs=10.250.0.10; remote_addrs=$PRI1_IKE; proposals=aes256-sha256-modp2048; local { auth=psk; id=10.250.0.10; }; remote { auth=psk; id=$PRI1_IKE; }; children { pri1 { local_ts=0.0.0.0/0; remote_ts=0.0.0.0/0; if_id_in=411; if_id_out=411; esp_proposals=aes256-sha256; start_action=$private_start_action; dpd_action=restart; } } }
  pub0 { version=2; local_addrs=10.250.0.10; remote_addrs=$PUB0_IKE; mobike=no; encap=yes; proposals=aes256-sha256-modp2048; local { auth=psk; id=$PUBLIC_CPE_IP; }; remote { auth=psk; id=$PUB0_IKE; }; children { pub0 { local_ts=0.0.0.0/0; remote_ts=0.0.0.0/0; if_id_in=420; if_id_out=420; esp_proposals=aes256-sha256; start_action=$public_start_action; dpd_action=restart; } } }
  pub1 { version=2; local_addrs=10.250.0.10; remote_addrs=$PUB1_IKE; mobike=no; encap=yes; proposals=aes256-sha256-modp2048; local { auth=psk; id=$PUBLIC_CPE_IP; }; remote { auth=psk; id=$PUB1_IKE; }; children { pub1 { local_ts=0.0.0.0/0; remote_ts=0.0.0.0/0; if_id_in=421; if_id_out=421; esp_proposals=aes256-sha256; start_action=$public_start_action; dpd_action=restart; } } }
}
secrets {
  ike-pri { id-1=10.250.0.10; secret="$PRIVATE_PSK"; }
  ike-pub { id-1=$PUBLIC_CPE_IP; secret="$PUBLIC_PSK"; }
}
EOF
chmod 0600 /etc/swanctl/conf.d/vwan.conf

public_neighbor_base=""
private_neighbor_instances=$(cat <<EOF
 neighbor $PRI0_BGP peer-group PRI
 neighbor $PRI1_BGP peer-group PRI
EOF
)
if $private_neighbor_shutdown; then
  private_neighbor_instances+=$'\n'" neighbor "$PRI0_BGP shutdown"
  private_neighbor_instances+=$'\n'" neighbor "$PRI1_BGP shutdown"
fi
public_neighbor_instances=""
public_address_family=""
public_policy=""
bgp_peer_elements="$PRI0_BGP, $PRI1_BGP"
if $public_bgp_enabled; then
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
  if $public_neighbor_shutdown; then
    public_neighbor_instances+=$'\n'" neighbor "$PUB0_BGP shutdown"
    public_neighbor_instances+=$'\n'" neighbor "$PUB1_BGP shutdown"
  fi
  public_address_family=$(cat <<EOF
  neighbor PUB route-map IMPORT-PUB in
  neighbor PUB prefix-list AZURE-IN in
  neighbor PUB prefix-list ACTIVE-OUT out
  neighbor PUB route-map EXPORT-PUB out
EOF
)
  public_policy=$(cat <<EOF
route-map IMPORT-PUB permit 10
 set local-preference 100
route-map EXPORT-PUB permit 10
 $public_prepend
EOF
)
  bgp_peer_elements="$bgp_peer_elements, $PUB0_BGP, $PUB1_BGP"
fi

cat >/etc/frr/frr.conf <<EOF
frr version 8.4
frr defaults traditional
hostname cpe-vwan-lab
service integrated-vtysh-config
ip route 10.240.0.0/24 Null0 254
ip route 10.241.0.0/24 Null0 254
$d3_fallback
$(for p in $advertised; do echo "ip route $p Null0"; done)
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
  network 10.253.1.0/24
  network 10.253.2.0/24
  network 10.253.3.0/25
  network 10.253.3.128/25
  neighbor PRI route-map IMPORT-PRI in
  neighbor PRI prefix-list AZURE-IN in
  neighbor PRI prefix-list ACTIVE-OUT out
$public_address_family
 exit-address-family
ip prefix-list AZURE-IN seq 10 permit 10.240.0.0/24
ip prefix-list AZURE-IN seq 20 permit 10.241.0.0/24
$(i=10; for p in $advertised; do echo "ip prefix-list ACTIVE-OUT seq $i permit $p"; i=$((i+10)); done)
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
    tcp dport 179 ip saddr != @bgp_peers drop
  }
}
EOF
nft delete table inet vwan_lab 2>/dev/null || true
nft -f /etc/nftables.d-vwan-lab.conf

systemctl daemon-reload
systemctl enable vwan-lab-network.service vwan-lab-ipsec.service
systemctl restart vwan-lab-network.service strongswan vwan-lab-ipsec.service frr
rm -f "$runtime"
logger -t vwan-lab "Applied $DESIGN configuration"
