#!/bin/bash
date -u
ping -n -c 3 -W 1 10.60.1.4
echo "PING_STATUS=$?"
timeout 4 bash -c 'exec 3<>/dev/tcp/10.60.1.4/22; head -c 100 <&3'
echo "TCP_STATUS=$?"
iptables -nvL FORWARD
echo LIVENESS_COMPLETE
