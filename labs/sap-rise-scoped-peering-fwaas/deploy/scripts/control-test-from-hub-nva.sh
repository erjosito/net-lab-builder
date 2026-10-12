#!/bin/bash
set -x
echo "=== ip route show (kernel table) ==="
ip route show

echo "=== CONTROL: Ping spoke NVA (10.60.0.4) from the legitimate peered subnet (snet-hub-nva) ==="
ping -c 4 -W 2 10.60.0.4

echo "=== CONTROL: ip route get 10.60.0.4 ==="
ip route get 10.60.0.4
