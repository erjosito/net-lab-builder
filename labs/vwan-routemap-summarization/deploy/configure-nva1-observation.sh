#!/usr/bin/env bash
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y strongswan strongswan-swanctl charon-systemd bird2 iproute2 tcpdump net-tools jq
cat >/etc/sysctl.d/99-nva.conf <<'EOF'
net.ipv4.ip_forward=1
net.ipv4.conf.all.accept_redirects=0
net.ipv4.conf.all.send_redirects=0
net.ipv4.conf.default.rp_filter=0
net.ipv4.conf.all.rp_filter=0
net.ipv4.conf.eth0.rp_filter=0
EOF
sysctl -p /etc/sysctl.d/99-nva.conf
sed -i 's/^#\?Port .*/Port 2222/' /etc/ssh/sshd_config || true
grep -q '^Port 2222' /etc/ssh/sshd_config || echo 'Port 2222' >> /etc/ssh/sshd_config
systemctl restart ssh || systemctl restart sshd || true
mkdir -p /etc/swanctl/conf.d
cat >/etc/swanctl/swanctl.conf <<'EOF'
include conf.d/*.conf
EOF
cat >/etc/swanctl/conf.d/azure-vwan.conf <<EOF
connections {
    vng0 {
        version = 2
        local_addrs = 10.100.0.4
        remote_addrs = 4.166.91.209
        proposals = aes256-sha256-modp2048
        local {
            auth = psk
            id = 20.240.241.93
        }
        remote {
            auth = psk
            id = 4.166.91.209
        }
        children {
            s2s0 {
                local_ts = 0.0.0.0/0
                remote_ts = 0.0.0.0/0
                esp_proposals = aes256-sha256-modp2048
                mode = tunnel
                start_action = trap
                close_action = trap
                dpd_action = restart
                if_id_in = 41
                if_id_out = 41
            }
        }
        dpd_delay = 10s
        rekey_time = 28800s
    }
    vng1 {
        version = 2
        local_addrs = 10.100.0.4
        remote_addrs = 4.166.187.142
        proposals = aes256-sha256-modp2048
        local {
            auth = psk
            id = 20.240.241.93
        }
        remote {
            auth = psk
            id = 4.166.187.142
        }
        children {
            s2s1 {
                local_ts = 0.0.0.0/0
                remote_ts = 0.0.0.0/0
                esp_proposals = aes256-sha256-modp2048
                mode = tunnel
                start_action = trap
                close_action = trap
                dpd_action = restart
                if_id_in = 42
                if_id_out = 42
            }
        }
        dpd_delay = 10s
        rekey_time = 28800s
    }
}
secrets {
    ike-0 {
        id-local = 20.240.241.93
        id-remote = 4.166.91.209
        secret = "<VPN_PSK_REDACTED>"
    }
    ike-1 {
        id-local = 20.240.241.93
        id-remote = 4.166.187.142
        secret = "<VPN_PSK_REDACTED>"
    }
}
EOF
chmod 600 /etc/swanctl/conf.d/azure-vwan.conf
cat >/etc/bird/bird.conf <<EOF
log syslog all;
router id 10.100.0.4;
protocol device {
    scan time 10;
}
protocol direct {
    ipv4;
    interface "eth0", "xfrm41", "xfrm42";
}
protocol kernel {
    ipv4 {
        import all;
        export all;
    };
    learn;
    scan time 15;
}
protocol static static_bgp {
    ipv4;
    route 10.99.0.0/24 via 10.100.0.4;
}
template bgp azure_vwan {
    local 10.100.0.4 as 65001;
    multihop 2;
    ipv4 {
        import all;
        export where proto = "static_bgp";
    };
    graceful restart on;
    connect retry time 10;
    hold time 60;
    keepalive time 20;
}
protocol bgp vpngw0 from azure_vwan {
    neighbor 192.168.0.14 as 65515;
}
protocol bgp vpngw1 from azure_vwan {
    neighbor 192.168.0.15 as 65515;
}
EOF
systemctl stop strongswan-starter 2>/dev/null || true
systemctl enable strongswan 2>/dev/null || systemctl enable strongswan-starter 2>/dev/null || true
systemctl restart strongswan 2>/dev/null || systemctl restart strongswan-starter 2>/dev/null || true
ip link del xfrm41 2>/dev/null || true
ip link del xfrm42 2>/dev/null || true
ip link add xfrm41 type xfrm dev eth0 if_id 41
ip link add xfrm42 type xfrm dev eth0 if_id 42
ip link set xfrm41 up
ip link set xfrm42 up
ip route replace 192.168.0.14/32 dev xfrm41 src 10.100.0.4
ip route replace 192.168.0.15/32 dev xfrm42 src 10.100.0.4
swanctl --load-all
swanctl --initiate --child s2s0 --ike vng0 --timeout 30 || true
swanctl --initiate --child s2s1 --ike vng1 --timeout 30 || true
systemctl restart bird
sleep 20
echo '=== swanctl --list-sas ==='
swanctl --list-sas || true
echo '=== ip route peers ==='
ip route get 192.168.0.14 || true
ip route get 192.168.0.15 || true
echo '=== birdc show protocols ==='
birdc show protocols || true
echo '=== birdc show route ==='
birdc show route || true
