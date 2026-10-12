#!/bin/bash
set -x
echo "=== CONTROL: Ping workload VM (10.60.1.4) from legitimate peered subnet (snet-hub-nva), via spoke NVA transit ==="
ping -c 4 -W 2 10.60.1.4

echo "=== CONTROL: ip route get 10.60.1.4 ==="
ip route get 10.60.1.4

echo "=== CONTROL: traceroute to 10.60.1.4 ==="
which traceroute >/dev/null 2>&1 || (sudo apt-get update -qq >/dev/null 2>&1; sudo apt-get install -y -qq traceroute >/dev/null 2>&1)
traceroute -n -w 2 -q 1 10.60.1.4
