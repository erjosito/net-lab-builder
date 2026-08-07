#!/bin/bash
echo "=== bird.conf ==="
cat /etc/bird/bird.conf
echo ""
echo "=== BIRD protocols ==="
birdc show protocols
echo ""
echo "=== BIRD route count ==="
birdc show route count
echo ""
echo "=== Kernel routes ==="
ip route show