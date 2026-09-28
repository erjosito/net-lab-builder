# Custom APIPA TCP/179 response analysis

**Question:** Does Azure answer CPE-initiated TCP/179 connections addressed to custom APIPA peers `169.254.22.2/.3` even while Azure independently initiates BGP from defaults `10.240.0.12/.13`?

**Answer:** No. The existing bounded-window capture contains a CPE SYN and one retransmission to each custom APIPA peer. It contains no SYN-ACK or RST sourced from either custom peer. During the same interval, Azure repeatedly initiated TCP/179 from its default addresses toward CPE APIPA `169.254.22.1`.

| Custom peer | Expected interface | CPE SYN | Azure SYN-ACK | Azure RST | Retransmission | Simultaneous Azure-originated SYN |
|---|---|---|---|---|---|---|
| `169.254.22.2` | `xfrm-pub0` | Yes: `19:45:18.737169`, seq `433883428` | No | No | One at `19:45:50.993019`, same seq, +32.255850s | Yes: `10.240.0.13`, 12 SYNs; nearest at +1.429336s |
| `169.254.22.3` | `xfrm-pub1` | Yes: `19:45:18.737064`, seq `3469601763` | No | No | One at `19:45:50.993087`, same seq, +32.256023s | Yes: `10.240.0.12`, 12 SYNs; nearest at +2.451954s |

Timestamps are from the CPE tcpdump clock, which aligned with the UTC command window.

## FRR state

At the end of the same bounded window, FRR reported both custom neighbors in `Connect`, with zero messages received or sent:

```text
169.254.22.2    4  65515  0  0  0  0  0  never  Connect  0
169.254.22.3    4  65515  0  0  0  0  0  never  Connect  0
```

FRR neighbor event/debug logging was not enabled or collected by the reviewed bounded-window command. Because the CPE was rolled back immediately afterward and another retry is prohibited, those historical daemon events cannot be recovered. This is an explicit evidence gap, not evidence that no FRR events occurred.

## Evidence and limitations

- Packet source: `20260928T194504391Z-assertion-assertion.stdout.txt`
- FRR summary: `20260928T194504623Z-assertion-assertion.stdout.txt`
- Reproducible offline analysis: `20260928T201130436Z-assertion-assertion.*`
- Analyzer: `scripts/Analyze-ApipaTcp179Capture.ps1`

The packet command captured TCP/179 with flags, sequence and acknowledgement values on all four XFRM interfaces for the original 60-second window. Its four concurrent tcpdump processes wrote to a shared stdout stream without a per-packet interface prefix. Custom-peer interface attribution therefore uses the route evidence captured in the same assertion: `.2` via `xfrm-pub0` and `.3` via `xfrm-pub1`.

No convergence time, provider state, CPE state or Azure state was changed to answer this question.
