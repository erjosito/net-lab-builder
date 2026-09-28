#!/usr/bin/env bash
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y strongswan-swanctl charon-systemd frr frr-pythontools tcpdump jq curl nftables iproute2
cat >/etc/sysctl.d/90-cpe-forwarding.conf <<'EOF'
net.ipv4.ip_forward=1
net.ipv4.conf.all.rp_filter=0
net.ipv4.conf.default.rp_filter=0
EOF
sysctl --system
sed -i 's/bgpd=no/bgpd=yes/;s/staticd=no/staticd=yes/' /etc/frr/daemons
systemctl enable --now frr
systemctl enable --now strongswan
mkdir -p /opt/vwan-lab /var/log/vwan-lab
