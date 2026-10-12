#!/bin/bash
set -x
GW=$(ip route show default | awk '{print $3}')
echo "Default gateway: $GW"
echo "=== Adding manual route to 10.60.0.0/27 via real default gateway (bypassing the broken onlink bird route) ==="
sudo ip route add 10.60.0.0/27 via "$GW" dev eth0 2>&1 || echo "route add failed/exists"
ip route show | grep 10.60

echo "=== Ping spoke NVA (10.60.0.4) via real gateway route ==="
ping -c 4 -W 2 10.60.0.4

echo "=== cleanup: remove manual route ==="
sudo ip route del 10.60.0.0/27 via "$GW" dev eth0 2>&1
