#!/bin/bash
set -x
echo "=== Installing traceroute/mtr ==="
sudo apt-get update -qq >/dev/null 2>&1
sudo apt-get install -y -qq traceroute mtr-tiny >/dev/null 2>&1

echo "=== ip route show (kernel table) ==="
ip route show

echo "=== Ping spoke NVA (10.60.0.4, peered subnet) ==="
ping -c 4 -W 2 10.60.0.4

echo "=== Traceroute to spoke NVA (10.60.0.4) ==="
traceroute -n -w 2 -q 1 10.60.0.4

echo "=== Ping workload VM (10.60.1.4, NOT in peered subnet - bypass attempt) ==="
ping -c 4 -W 2 10.60.1.4

echo "=== Traceroute to workload VM (10.60.1.4) - bypass attempt ==="
traceroute -n -w 2 -q 1 10.60.1.4

echo "=== ip route get 10.60.1.4 ==="
ip route get 10.60.1.4

echo "=== ip route get 10.60.0.4 ==="
ip route get 10.60.0.4
