#!/usr/bin/env bash
set -eu
echo "=== ip route get 10.60.0.4 ==="
ip route get 10.60.0.4
echo "=== ping -c 3 10.60.0.4 ==="
ping -c 3 10.60.0.4
echo "=== tcpdump while forwarding CE-originated traffic ==="
timeout 20 tcpdump -ni any 'host 172.40.100.4 or host 10.60.0.4'
