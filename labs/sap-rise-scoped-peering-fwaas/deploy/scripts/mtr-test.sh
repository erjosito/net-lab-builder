#!/bin/bash
set -x
GW=$(ip route show default | awk '{print $3}')
sudo ip route add 10.60.0.0/27 via "$GW" dev eth0 2>&1 || echo "route add failed/exists"
echo "=== mtr to 10.60.0.4 (report mode, 5 cycles) ==="
sudo mtr -r -c 5 -n 10.60.0.4
echo "=== traceroute to 10.60.0.4 ==="
traceroute -n -w 2 -q 1 10.60.0.4
sudo ip route del 10.60.0.0/27 via "$GW" dev eth0 2>&1
