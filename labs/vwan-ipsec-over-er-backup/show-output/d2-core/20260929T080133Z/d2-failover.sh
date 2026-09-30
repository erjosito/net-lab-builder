#!/usr/bin/env bash
set -euo pipefail

start=$(date +%s%3N)
echo "FAULT_UTC=$(date -u +%FT%TZ) START_MS=$start"

timeout 90 tcpdump -l -nn -i any \
  '(host 10.253.2.10 and host 10.241.0.4) and (icmp or tcp port 8080)' \
  >/home/jomore/d2-failover-packets.txt 2>&1 &
capture_pid=$!

(
  for _ in $(seq 1 60); do
    now=$(date +%s%3N)
    if ping -I 10.253.2.10 -c 1 -W 1 10.241.0.4 >/dev/null 2>&1; then
      ping_state=ok
    else
      ping_state=fail
    fi
    if curl --interface 10.253.2.10 --connect-timeout 1 --max-time 2 \
      -sSf http://10.241.0.4:8080/health >/dev/null 2>&1; then
      http_state=ok
    else
      http_state=fail
    fi
    echo "PROBE ms=$((now-start)) ping=$ping_state http=$http_state"
    sleep 1
  done
) >/home/jomore/d2-failover-probes.txt &
probe_pid=$!

vtysh -c conf -c 'router bgp 65050' \
  -c 'neighbor 10.240.0.12 shutdown' \
  -c 'neighbor 10.240.0.13 shutdown'
withdraw=$(date +%s%3N)
echo "PRIVATE_SHUT_MS=$((withdraw-start))"

for _ in $(seq 1 60); do
  if ip route show 10.241.0.0/24 | grep -q xfrm-pub; then
    selected=$(date +%s%3N)
    echo "PUBLIC_SELECTED_MS=$((selected-start)) CONVERGENCE_MS=$((selected-withdraw))"
    break
  fi
  sleep 1
done

echo ===BGP_SUMMARY===
vtysh -c 'show bgp ipv4 unicast summary'
echo ===AZURE_ROUTE===
vtysh -c 'show bgp ipv4 unicast 10.241.0.0/24'
echo ===KERNEL===
ip route show 10.241.0.0/24
echo ===SAS===
swanctl --list-sas | grep -E '^(pri|pub)[01]:|INSTALLED'
echo ===PAYLOAD===
ping -I 10.253.2.10 -c 5 -W 2 10.241.0.4
curl --interface 10.253.2.10 --connect-timeout 5 --max-time 10 \
  -sS -D - http://10.241.0.4:8080/health

wait "$probe_pid" || true
wait "$capture_pid" || true
echo ===PROBES===
cat /home/jomore/d2-failover-probes.txt
echo ===PACKETS===
cat /home/jomore/d2-failover-packets.txt
