# Skill: BIRD-on-Azure BGP diagnostics via `az vm run-command` (no Bastion/SSH)

**Origin:** Niobe, 2026-09-29, `labs/sap-rise-scoped-peering-fwaas` S1 live validation.

## When to use this

Any lab where a Linux NVA runs BIRD (or likely FRR) to redistribute routes across an Azure VNet
peering (subnet-scoped or full), and Bastion/SSH is not deployed — VM access is via
`az vm run-command invoke --command-id RunShellScript` only.

## Constraint: one run-command per VM at a time

A second concurrent `run-command` invocation on the same VM fails immediately with:

```
ERROR: (Conflict) Run command extension execution is in progress. Please wait for completion before invoking a run command.
```

Sequence calls per-VM (wait for one to finish before starting the next on the same VM);
parallelize freely across *different* VMs.

## Core diagnostic sequence (BIRD)

Run each as a single `--scripts` string with `echo '===LABEL==='` separators so multi-command
output stays attributable in one captured file:

```powershell
az vm run-command invoke -g <rg> -n <vm> --command-id RunShellScript --scripts "birdc show protocols; echo '---ROUTES---'; birdc show route" -o json

az vm run-command invoke -g <rg> -n <vm> --command-id RunShellScript --scripts "birdc show protocols all" -o json

az vm run-command invoke -g <rg> -n <vm> --command-id RunShellScript --scripts "cat /etc/bird/bird.conf" -o json

az vm run-command invoke -g <rg> -n <vm> --command-id RunShellScript --scripts "birdc show route protocol <static_protocol_name> all; birdc show route export <bgp_peer_name>; birdc show route all" -o json

az vm run-command invoke -g <rg> -n <vm> --command-id RunShellScript --scripts "ip route show; ping -c 2 -W 2 <peered-subnet-ip>" -o json
```

- `birdc show protocols` gives session state (`Established` / `Idle` / `Active`) and the last
  error string (e.g. `"BGP Error: Hold timer expired"`, `"Socket: Connection reset by peer"`) —
  the fastest way to spot a flapping session.
- `birdc show protocols all` (no peer name arg needed — dumps everything) gives per-session route
  counts (`Routes: N imported, N exported, N preferred`) — use this to see whether a session
  is actually carrying anything even when it happens to be up.
- **Poll twice, a couple of minutes apart, before concluding a BGP session is stable.** A single
  snapshot can show "Established" while the session is actually flapping; two polls showing
  different sessions up/down in different combinations is the signature of a real flap, not a
  one-time convergence transient.

## Gotcha: recursive static routes over Azure VNet peering never resolve

If `bird.conf` has a static route like:

```
protocol static static_bgp {
    ipv4;
    route <remote-supernet> via <ip-in-a-peered-subnet>;
}
```

this is a **recursive next-hop** static route. BIRD requires a route to the "via" IP inside its
OWN routing table before it will install (and therefore export) the static route. Azure's VNet
peering fabric (subnet-scoped or full) delivers packets to a peered subnet transparently at the
hypervisor/SDN layer — **it never injects a corresponding route into the guest OS kernel routing
table.** Since BIRD's `kernel1 { learn; }` protocol only imports what `ip route show` inside the
guest actually shows, the recursive resolution silently fails and the static route never
materializes — **even though the data plane can reach the IP fine** (confirm with a direct `ping`
alongside `ip route show` — the mismatch between "ping succeeds" and "no route in `ip route
show`/`birdc show route all`" is the tell).

**How to confirm this is the cause, in order:**
1. `birdc show route protocol <static_protocol_name> all` → returns nothing (zero routes).
2. `ip route show` inside the VM → no entry for the peered subnet.
3. `az network nic show-effective-route-table -g <rg> -n <nic>` → DOES show a `VNetPeering`
   system route for that same subnet (proves the Azure fabric side is fine).
4. `ping -c 2 <ip-in-peered-subnet>` from inside the VM → succeeds (proves data-plane reachability
   despite the missing kernel/BIRD route).

**Fix (confirmed and applied — Trinity, 2026-09-29, sap-rise-scoped-peering-fwaas S1 re-fix):** replace
the bare recursive `via` with an `onlink` static route bound to the interface the peered subnet is
actually reachable through:

```
protocol static static_bgp {
    ipv4;
    route <remote-supernet> via <ip-in-a-peered-subnet> dev "<iface>" onlink;
}
```

`onlink` tells BIRD to treat the next hop as directly reachable on the named interface without
resolving it against the RIB — this matches exactly what Azure's peering fabric guarantees (the
peered subnet is reachable off this NIC) without needing a kernel-table entry Azure never
provides. This is now the **standard fix pattern**, not one of two options: use it for any BIRD
static route on an Azure NVA whose next hop sits across a VNet/subnet peering. (A cloud-init
`ip route add ... dev <iface>` host route is an alternative that also works, but the in-`bird.conf`
`onlink` route is simpler — one file, no extra cloud-init dependency — and is the one validated
end-to-end in this lab.)

## Gotcha: `export none` copy-drift on a peer that should advertise

When a `bird.conf` has multiple BGP protocol blocks (e.g. one per peer — ARS sessions, an on-prem
CE session), it's easy for one block to retain an `export none` (or a filter meant for a
different, import-only peer) via copy-paste from a template, while the design's actual intent is
for that peer to receive the same routes as the others. Sessions can establish cleanly
(`Established`, no errors) while this bug is present — **a healthy session state proves nothing
about whether the intended routes are actually being advertised.** Always check the concrete
result, not just session state:

```
birdc show route export <peer-protocol-name>
```

If this is empty for a peer that the design says should receive the redistributed route, check
that peer's `export` filter against the design's stated advertisement intent (not just against
whether the peer's own session establishes).

## Gotcha: `protocol kernel { export all; }` + Azure Route Server = self-inflicted guest routing-table poisoning

If a BIRD-speaking NVA peers with **Azure Route Server (ARS)** and its `bird.conf` has:

```
protocol kernel {
    ipv4 {
        import all;
        export all;    # <-- danger: pushes BIRD's whole RIB into the OS kernel table
    };
    learn;
}
```

...and at least one BGP protocol block importing from ARS uses `import all;` (directly or via a
shared template), this combination can silently break return connectivity to **one specific ARS
peer IP while the other ARS peer IP (in the same subnet) keeps working fine** — with a flap
pattern where exactly one BGP session out of several stays Established at a time, rotating.

**Why this happens:** Azure Route Server advertises the VNet's own local address space (including
its own `RouteServerSubnet`) back to every BGP peer **by default** — this is documented, expected
ARS behavior, not a misconfiguration on the ARS side. If the NVA peers with *two* ARS instances
(the normal HA pair), both instances send an overlapping/identical route set back to the NVA, each
with its own IP as next-hop. BIRD's best-path selection keeps only one winning route per prefix.
`export all` on the kernel protocol then installs *that one winning route* into the real Linux
kernel routing table — silently overwriting the correct, Azure-fabric-derived reachability for the
*other* ARS peer's IP, even though both peer IPs sit in the same subnet and are otherwise covered
by the same Azure `VnetLocal` system route.

**Symptom signature (how to recognize this specifically, vs. other flap causes):**
- `birdc show protocols`, polled a few minutes apart: exactly one session Established at a time,
  rotating among peers — not all sessions failing together (rules out NSG/network-wide outage).
- The failing peer's error is `"No route to host"` (BIRD's own outbound attempt fails at the
  kernel level, not a remote rejection).
- A `tcpdump -i eth0 tcp port 179` on the NVA during a confirmed-down window shows inbound SYNs
  arriving from the down peer with **zero replies from the NVA — not even a RST**. Total one-sided
  silence like this is the kernel-level "no route" tell (contrast with a NSG block, which would
  never let the SYN reach the guest's socket stack in the first place — the SYN capture proves the
  packet *did* arrive; the missing reply proves the kernel couldn't route the answer back out).
- `az network nic show-effective-route-table` on the NVA's NIC shows the correct, unbroken Azure
  fabric route for the affected subnet the whole time — the platform side is never wrong; the
  guest's own kernel table is the only place that can explain the asymmetry.

**Fix:** change the kernel protocol's export direction to `none` — the NVA almost never needs
BIRD to write anything into its own OS forwarding table; `import` (read-only, needed for `onlink`
static-route resolution — see the recursive-nexthop gotcha above) is enough:

```
protocol kernel {
    ipv4 {
        import all;
        export none;
    };
    learn;
}
```

If a design genuinely does need BIRD to install specific self-originated routes into the kernel
(rare for a pure route-redistribution NVA), scope the export narrowly, e.g.
`export where proto = "static_bgp";`, instead of `export all;` — never let externally-learned
BGP routes from an ARS session flow through to the kernel FIB.

**Verification (pass bar, not a single good poll):** after applying, confirm `ip route show` on
the NVA no longer contains any ARS-peer-subnet-origin entries, then poll `birdc show protocols`
at least 3-4 times over 10+ minutes and require **all BGP sessions Established simultaneously on
every poll** — a poll showing only one session up (even if it rotates which one) is still a fail.

## Gotcha: BGP flap correlated with a burstable/CPU-credit VM SKU running BIRD

If a BIRD-speaking NVA is deployed on a burstable, CPU-credit-based size (e.g. `Standard_B2s_v2`,
`B2als_v2`) — often a capacity-fallback substitution, not the original design choice — and its
BGP sessions flap with `"Hold timer expired"` in an alternating pattern across multiple sessions
(not all going down together, and not a one-time convergence blip when polled twice a few minutes
apart), consider whether the VM is CPU-credit-throttled. A BIRD process endlessly retrying a
never-resolving route recalculation (e.g. the recursive-nexthop gotcha above, before it's fixed)
is one plausible way to generate that sustained CPU pressure on an otherwise idle-looking NVA.
Fixing the underlying route-resolution issue first is cheaper than resizing the VM and should be
tried before assuming a SKU-level fix is needed. If the flap persists after the BIRD config is
otherwise correct, check CPU-credit exhaustion (Azure Monitor VM insights, or
`cat /sys/fs/cgroup/cpu.stat` via run-command) before escalating to a non-burstable SKU — and as
cheap, zero-cost insurance regardless of cause, widen `hold time`/`keepalive time` (e.g. 60/20 →
180/60) on a burstable-SKU NVA's BGP protocols.

## Gotcha: BGP hold/keepalive timers fixed on only one side of a `bird.conf`-to-`bird.conf` peer

If two separate VMs each run their own BIRD instance and peer directly with each other (as opposed
to one side being a managed PaaS BGP speaker like Azure Route Server), a timer fix applied to only
one side's protocol block is a **silent, delayed-onset defect** — not a config error BIRD will
ever flag at load or `configure` time.

**Why it's silent:** BGP negotiates the OPEN message's hold time as the **lower of the two sides'
offered values**. If side A is fixed to `hold time 180; keepalive time 60;` but side B is still at
the old `hold time 60; keepalive time 20;`, the session negotiates to A's 60s value from B — while
A itself now only sends a keepalive every 60s. That leaves B's 60-second hold clock with zero
margin against A's 60-second keepalive cadence: B's own hold timer will eventually race A's
keepalive and lose, tearing the session down, even though both sides' configs are individually
"valid" BIRD syntax and the session establishes cleanly every time before flapping again.

**How to tell which side is actually expiring its own timer (not just which side "goes down
first" — both logs show the state change at the same instant):** BIRD's own log grammar
distinguishes the two roles:
- `<peer>: Error: Hold timer expired` = **this box's own hold timer expired locally** — it is the
  one initiating the teardown by sending the NOTIFICATION.
- `<peer>: Received: Hold timer expired` = this box **received** a NOTIFICATION from the peer
  carrying that error code — it is not the side whose timer actually expired.

Pull `journalctl -u bird` from **both** VMs for the same flap window and compare which one logs
`Error:` vs `Received:` at the matching timestamp. The side logging `Error:` has the stale/lower
timer config; fix that side to match. A simultaneous `tcpdump -i eth0 tcp port 179` on both VMs
during a confirmed down→up→down cycle corroborates this: the side with the stale timer will show
normal keepalive traffic at its own (shorter) cadence right up to a clean, self-initiated FIN at
the exact millisecond its hold timer expires — not silence, not a RST, just a timer race it was
always going to lose.

**Fix and prevention:** align both sides to the same `hold time`/`keepalive time` values (matching
values are the simplest and safest choice for a lab; if asymmetric-but-safe values are ever
needed, the wider side's `hold time` must still exceed the tighter side's `keepalive time` by a
comfortable multiple, not sit at the same number). Treat any BGP-to-BGP peer realized as two
independent `bird.conf` files (as opposed to one config plus a managed PaaS peer like ARS) as a
**two-file change unit** for timers, ASNs, addressing, or `multihop` — document this explicitly in
the lab's design doc next to the config, since there is no shared source of truth to enforce it
otherwise, and BIRD gives no warning when only one side is updated.

## Azure CLI syntax corrections (frequently mis-guessed from generic skeletons)

- `az network routeserver peering list-learned-routes` / `list-advertised-routes` take
  **`--name`** (peering name) — NOT `--peering-name`.
- `az network vnet-gateway list-advertised-routes` requires **`--peer <peerIP>`** (the actual
  MSEE/circuit BGP peer IP address) — there is no `--peer-group-name` parameter.
- ExpressRoute Gateway BGP state (learned/advertised routes, peer status) is read through the
  standard **`az network vnet-gateway ...`** command group, not a separate
  `express-route gateway` subcommand group, unless the lab specifically deployed an
  ExpressRoute-managed vWAN gateway (`az network express-route gateway` is for that different
  resource type).
