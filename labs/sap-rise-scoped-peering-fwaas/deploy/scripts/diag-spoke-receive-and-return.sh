#!/usr/bin/env bash
set -eu
echo "=== ip route get 172.40.100.4 ==="
ip route get 172.40.100.4
echo "=== ip route ==="
ip route
echo "=== tcpdump for CE and hub traffic ==="
timeout 20 tcpdump -ni any 'host 172.40.100.4 or host 10.40.1.4'
