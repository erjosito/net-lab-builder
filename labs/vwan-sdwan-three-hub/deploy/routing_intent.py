"""Task-owned secured-hub resources; private test traffic only, no Internet RI."""
import argparse
import time

import aspath_sweep as sweep
import control
import infra


POLICY = "policy-threehub"
PRIVATE_PREFIXES = infra.DC_PREFIXES + infra.SPOKE_PREFIXES


def secured_template():
    resources = [
        infra.resource("firewallPolicies", POLICY, {
            "sku": {"tier": "Standard"}, "threatIntelMode": "Off",
            "snat": {"privateRanges": ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]}
        }, "eu")
    ]
    rules = infra.resource("firewallPolicies/ruleCollectionGroups", POLICY + "/lab-private", {
        "priority": 100,
        "ruleCollections": [{
            "name": "allow-lab-private", "priority": 100,
            "ruleCollectionType": "FirewallPolicyFilterRuleCollection",
            "action": {"type": "Allow"},
            "rules": [{
                "name": "bidirectional-tcp-probes", "ruleType": "NetworkRule",
                "ipProtocols": ["TCP"],
                "sourceAddresses": PRIVATE_PREFIXES,
                "destinationAddresses": PRIVATE_PREFIXES,
                "destinationPorts": ["5201"]
            }, {
                "name": "bidirectional-icmp-probes", "ruleType": "NetworkRule",
                "ipProtocols": ["ICMP"],
                "sourceAddresses": PRIVATE_PREFIXES,
                "destinationAddresses": PRIVATE_PREFIXES,
                "destinationPorts": ["*"]
            }]
        }]
    }, depends=[infra.rid("firewallPolicies", POLICY)])
    resources.append(rules)
    for site in sweep.SITES:
        firewall = f"fw-{site}"
        resources.append(infra.resource("azureFirewalls", firewall, {
            "sku": {"name": "AZFW_Hub", "tier": "Standard"},
            "virtualHub": {"id": infra.rid("virtualHubs", f"hub-{site}")},
            "firewallPolicy": {"id": infra.rid("firewallPolicies", POLICY)},
            "hubIPAddresses": {"publicIPs": {"count": 1}}
        }, site, [infra.rid("firewallPolicies/ruleCollectionGroups", POLICY + "/lab-private")]))
        resources.append(infra.resource("virtualHubs/routingIntent", f"hub-{site}/private-traffic", {
            "routingPolicies": [{
                "name": "PrivateTraffic", "destinations": ["PrivateTraffic"],
                "nextHop": infra.rid("azureFirewalls", firewall)
            }]
        }, depends=[infra.rid("azureFirewalls", firewall)]))
    return infra.template(resources)


def assert_secured(hub, intent, firewall, firewall_id):
    if firewall.get("properties", {}).get("provisioningState") != "Succeeded":
        raise RuntimeError("Firewall not successfully provisioned")
    if hub.get("properties", {}).get("azureFirewall", {}).get("id", "").lower() != firewall_id.lower():
        raise RuntimeError("Hub does not reference its expected firewall")
    entries = intent.get("value", [])
    if len(entries) != 1:
        raise RuntimeError("Exactly one routing intent required")
    policies = entries[0].get("properties", {}).get("routingPolicies", [])
    if (len(policies) != 1 or policies[0].get("destinations") != ["PrivateTraffic"] or
            policies[0].get("nextHop", "").lower() != firewall_id.lower()):
        raise RuntimeError("Actual routing intent does not match private firewall policy")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lease", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    control.LEASE = control.RUNTIME / args.lease
    lease = control.guard(True)
    if lease.get("toolCallsUsed", 0) or lease.get("mutationsUsed", 0):
        raise RuntimeError("Fresh deployment lease required")
    sweep.SUB = control.account_id()
    sweep.OUT = control.ROOT.parent / "show-output" / args.out
    sweep.CURRENT = sweep.OUT
    if sweep.OUT.exists():
        raise RuntimeError("Fresh evidence directory required")
    deployment = "threehub-private-routing-intent"
    errors, observed = [], {}
    try:
        sweep.hub_metadata()
        template = control.RUNTIME / "routing-intent-template.json"
        control.save(template, secured_template())
        sweep.az(["deployment", "group", "validate", "-g", control.RG,
                  "--template-file", str(template)], "ri-validate")
        sweep.az(["deployment", "group", "create", "-g", control.RG, "--name", deployment,
                  "--template-file", str(template), "--no-wait"], "ri-submit", mutation=True)
        deadline = time.monotonic() + 2400
        while True:
            state = sweep.az(["deployment", "group", "show", "-g", control.RG,
                              "--name", deployment], f"ri-progress-{int(time.time())}")
            provisioning = state["properties"]["provisioningState"]
            print(f"ROUTING INTENT DEPLOYMENT {provisioning}", flush=True)
            if provisioning == "Succeeded":
                break
            if provisioning in ("Failed", "Canceled") or time.monotonic() >= deadline:
                raise RuntimeError(f"Deployment incomplete: {provisioning}")
            sweep.bounded_wait(60)
        sweep.RESTORING = True
        for site in sweep.SITES:
            hub = sweep.rest(sweep.network_url("virtualHubs", f"hub-{site}"), f"secured-hub-{site}")
            intent = sweep.rest(sweep.network_url("virtualHubs", f"hub-{site}/routingIntent"),
                                f"secured-intent-{site}")
            firewall = sweep.rest(sweep.network_url("azureFirewalls", f"fw-{site}"),
                                  f"secured-firewall-{site}")
            expected = (f"/subscriptions/{sweep.SUB}/resourceGroups/{control.RG}"
                        f"/providers/Microsoft.Network/azureFirewalls/fw-{site}")
            assert_secured(hub, intent, firewall, expected)
            observed[site] = dict(hub=hub, routingIntent=intent, firewall=firewall)
    except Exception as exc:
        errors.append(str(exc))
        print(f"ROUTING INTENT BLOCKED {exc}", flush=True)
    finally:
        lease = control.guard(False)
        complete = len(observed) == 3 and not errors
        verdict = "PASS" if complete else "BLOCKED"
        sweep.save("deployment-verdict.json", dict(
            timestampUtc=sweep.utc(), verdict=verdict, observed=observed, errors=errors,
            callsUsed=lease["toolCallsUsed"], mutationsUsed=lease.get("mutationsUsed", 0),
            children=[], retainedForTesting=complete, noRouteSelectionClaim=True))
        lease.update(state="completed" if complete else "blocked", verdict=verdict,
                     completedAtUtc=sweep.utc(), children=[], evidence=str(sweep.OUT))
        control.save(control.LEASE, lease)
        print(f"FINAL {verdict} three secured hubs={complete}", flush=True)
    if not complete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
