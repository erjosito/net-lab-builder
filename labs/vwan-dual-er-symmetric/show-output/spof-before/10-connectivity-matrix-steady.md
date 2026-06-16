# Steady-State Connectivity Matrix — Phase B captures

**Captured:** 2026-06-15T19:24:55+02:00  
**Method:** `az vm run-command invoke --command-id RunShellScript` with `ping -c 4 -W 2 <dst>`  
**GCP VM A IP:** `10.50.1.2` (VPC-A, europe-west3)  
**GCP VM B IP:** `10.50.2.2` (VPC-B, europe-west4)  

## Results

| Source VM | Source IP | Destination | Dst IP | Result | Avg RTT | TTL | Path notes |
|---|---|---|---|---|---|---|---|
| vm-spoke1 (hub1, swedencentral) | `10.11.0.4` | GCP VM A (VPC-A) | `10.50.1.2` | ✅ 0% loss | 85 ms | 59 | Hub1→ER1→MCR1→VPC-A (same-region, shorter path) |
| vm-spoke1 (hub1, swedencentral) | `10.11.0.4` | GCP VM B (VPC-B) | `10.50.2.2` | ✅ 0% loss | 149 ms | 58 | Hub1→Hub2 (vWAN link)→ER2→MCR2→VPC-B (cross-region, extra hop) |
| vm-spoke3 (hub2, northeurope) | `10.21.0.4` | GCP VM A (VPC-A) | `10.50.1.2` | ✅ 0% loss | 118 ms | 58 | Hub2→Hub1 (vWAN link)→ER1→MCR1→VPC-A (cross-region, extra hop) |
| vm-spoke3 (hub2, northeurope) | `10.21.0.4` | GCP VM B (VPC-B) | `10.50.2.2` | ✅ 0% loss | 66 ms | 59 | Hub2→ER2→MCR2→VPC-B (same-region, shorter path) |

## RTT interpretation

- **Same-region paths** (spoke1→VPC-A, spoke3→VPC-B): avg 75–85 ms, TTL=59. One fewer network hop than cross-region; Hub→ER→MCR→GCP all in proximate geographies.
- **Cross-region paths** (spoke1→VPC-B, spoke3→VPC-A): avg 115–150 ms, TTL=58. Extra hub-to-hub vWAN backbone transit adds ~1 hop (TTL diff) and ~35–65 ms latency.

## SPOF implication

All traffic to `10.50.1.0/24` (GCP VPC-A) routes through MCR1 regardless of source hub.  
- spoke1→VPC-A: Hub1→ER1→MCR1→VPC-A (direct)  
- spoke3→VPC-A: Hub2→Hub1 link→ER1→MCR1→VPC-A (indirect via hub-to-hub)  

**If MCR1 fails, BOTH rows targeting VPC-A (10.50.1.0/24) become unreachable — there is no alternate path.**

## Raw ping output (verbatim)

```
# spoke1 → GCP VM A (10.50.1.2)
64 bytes from 10.50.1.2: icmp_seq=1 ttl=59 time=86.4 ms
64 bytes from 10.50.1.2: icmp_seq=2 ttl=59 time=84.2 ms
64 bytes from 10.50.1.2: icmp_seq=3 ttl=59 time=85.5 ms
64 bytes from 10.50.1.2: icmp_seq=4 ttl=59 time=84.6 ms
4 packets transmitted, 4 received, 0% packet loss
rtt min/avg/max/mdev = 84.194/85.144/86.374/0.846 ms

# spoke1 → GCP VM B (10.50.2.2)
64 bytes from 10.50.2.2: icmp_seq=1 ttl=58 time=100 ms
64 bytes from 10.50.2.2: icmp_seq=2 ttl=58 time=126 ms
64 bytes from 10.50.2.2: icmp_seq=3 ttl=58 time=273 ms
64 bytes from 10.50.2.2: icmp_seq=4 ttl=58 time=98.1 ms
4 packets transmitted, 4 received, 0% packet loss
rtt min/avg/max/mdev = 98.133/149.247/273.201/72.377 ms

# spoke3 → GCP VM A (10.50.1.2)
64 bytes from 10.50.1.2: icmp_seq=1 ttl=58 time=125 ms
64 bytes from 10.50.1.2: icmp_seq=2 ttl=58 time=114 ms
64 bytes from 10.50.1.2: icmp_seq=3 ttl=58 time=115 ms
64 bytes from 10.50.1.2: icmp_seq=4 ttl=58 time=117 ms
4 packets transmitted, 4 received, 0% packet loss
rtt min/avg/max/mdev = 114.204/117.896/125.279/4.367 ms

# spoke3 → GCP VM B (10.50.2.2)
64 bytes from 10.50.2.2: icmp_seq=1 ttl=59 time=63.8 ms
64 bytes from 10.50.2.2: icmp_seq=2 ttl=59 time=61.7 ms
64 bytes from 10.50.2.2: icmp_seq=3 ttl=59 time=68.4 ms
64 bytes from 10.50.2.2: icmp_seq=4 ttl=59 time=69.1 ms
4 packets transmitted, 4 received, 0% packet loss
rtt min/avg/max/mdev = 61.747/65.771/69.059/3.076 ms
```

Note: `traceroute` not installed on lab VMs (Ubuntu minimal image). TTL analysis substituted for hop-by-hop path reconstruction.
