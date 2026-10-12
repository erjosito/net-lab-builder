#!/bin/bash
set -eu
date -u
echo '=== routes ==='
ip route
echo '=== rules ==='
ip rule
echo '=== NAT ==='
iptables-save -t nat
echo '=== forwarding ==='
sysctl net.ipv4.ip_forward net.ipv4.conf.all.rp_filter
echo '=== tools ==='
for tool in python3 mtr traceroute tcpdump; do
    command -v "$tool" || printf 'MISSING %s\n' "$tool"
done
echo '=== SSH listener ==='
ss -lnt '( sport = :22 )'
echo 'SNAPSHOT_COMPLETE'
