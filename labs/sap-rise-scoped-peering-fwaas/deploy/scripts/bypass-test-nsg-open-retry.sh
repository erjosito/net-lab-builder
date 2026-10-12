#!/bin/bash
set -x
echo "=== Ping spoke NVA (10.60.0.4) with NSG now allowing this source subnet ==="
ping -c 4 -W 2 10.60.0.4

echo "=== Traceroute to spoke NVA (10.60.0.4) ==="
traceroute -n -w 2 -q 1 10.60.0.4

echo "=== Ping workload VM (10.60.1.4) - still not NSG-allowed, still no route expected ==="
ping -c 4 -W 2 10.60.1.4
