"""Render completed BGP-only HRP reset controls without assuming reset success."""
import argparse
import json
import pathlib

import b2b_report as report
import design_b2b as b2b
import design_comparison as comparison
import design_hrp_bgp_reset as reset

CASES = tuple((preference + ", " + order,
               "hrp-reset-" + preference.lower() + "-" + order +
               ("-retry" if preference == "VpnGateway" and order == "japan-first" else "") +
               "-20261019", "after-reset")
              for preference in ("ExpressRoute", "VpnGateway")
              for order in reset.ORDERS)
HEADING = "## B1 after resetting all six Azure-facing BGP sessions"


def read(folder, name):
    return json.loads((report.OUTPUT / folder / name).read_text(encoding="utf-8"))


def validate():
    baseline = read("hrp-reset-baseline-20261019", "baseline-verdict.json")["result"]
    independent = read("hrp-reset-independent-retry-20261019", "baseline-verdict.json")
    power = read("hrp-reset-final-verify-power-stop-20261019", "power-verdict.json")
    recovery = read("hrp-reset-timeout-recovery-20261019", "recovery-verdict.json")
    if recovery["verdict"] != "PASS" or not recovery["restored"]:
        raise RuntimeError("Timed-out attempt must have separate recovery proof")
    if independent["verdict"] != "PASS" or power["verdict"] != "PASS" or not power["restored"]:
        raise RuntimeError("Independent original-state and power closure required")
    if len(power["actual"]) != 10 or any(v["powerState"] != "VM deallocated" for v in power["actual"]):
        raise RuntimeError("Original ten-VM deallocated inventory not restored")
    if independent["result"]["firewalls"]["rows"] != baseline["firewalls"]["rows"]:
        raise RuntimeError("Independent original firewall winners differ")
    for case in CASES:
        verdict = read(case[1], "reset-verdict.json")
        if verdict["verdict"] != "PASS" or not verdict["restored"] or verdict["errors"] or any(verdict["pending"].values()):
            raise RuntimeError("Complete measured reset and exact restore required: " + case[0])
        data = report.load(case)
        report.acceptance(data["traffic"])
        if not data["firewalls"]["stable"] or data["firewalls"]["minimumSnapshotSpacingSeconds"] < 120:
            raise RuntimeError("Paired stable firewall winners required")
        for site in b2b.snapshot.ALL_SITES:
            if not comparison.source_unchanged(baseline["sources"][site], data["sources"][site]):
                raise RuntimeError("BIRD configuration/metadata changed")
        transport = read(case[1], "bgp-reset/transport-invariants.json")
        if transport["verdict"] != "PASS":
            raise RuntimeError("Transport invariants did not pass")
        reset.assert_transport_unchanged(transport["before"], transport["after"])
        down = read(case[1], "bgp-reset/disable-all-sessions.json")
        if any(p["state"] != "down" for site in down.values()
               for name, p in site["after"]["rows"].items() if name.startswith("azure_")):
            raise RuntimeError("All six Azure sessions were not confirmed down")
        files = sorted((report.OUTPUT / case[1] / "bgp-reset").glob("all-down-winners-*.json"))
        if not files or json.loads(files[-1].read_text()) != []:
            raise RuntimeError("All DC-prefix withdrawals not confirmed")
        for address in ("10.10.0.10", "10.20.0.10", "10.30.0.10"):
            route = report.effective_match(data["workload"]["effectiveRoutes"], address)
            if route["nextHopType"] != "VirtualAppliance" or route["nextHopIpAddress"] != ["10.130.0.4"]:
                raise RuntimeError("Japan workload steering correction not present")


def winner_table():
    lines = ["| HRP / re-enable order | Before reset: EU / US Japan paths | After: EU Japan winner | After: US Japan winner | TCP / 24 | ICMP / 24 |",
             "|---|---|---|---|---|---|"]
    for case in CASES:
        data = report.load(case)
        winners = b2b.reselection.japan_winners(data)
        values = [f"`{winners[s]['asPath']}` ({winners[s]['nextHopType']})" for s in ("eu", "us")]
        before = b2b.reselection.japan_winners(read(case[1], "HRP-only/scenario-result.json"))
        initial = " / ".join(f"`{before[s]['asPath']}`" for s in ("eu", "us"))
        traffic = report.acceptance(data["traffic"])
        lines.append(f"| [{case[0]}]({report.link(case, 'scenario-result.json')}) | {initial} | " +
                     " | ".join(values) + f" | {traffic['tcpPass']} | {traffic['icmpPass']} |")
    return "\n".join(lines)


def outcome():
    statements = []
    for preference in ("ExpressRoute", "VpnGateway"):
        cases = [case for case in CASES if case[0].startswith(preference + ",")]
        data = [report.load(case) for case in cases]
        local = [b2b.reselection.local_japan(value) for value in data]
        before_local = [b2b.reselection.local_japan(
            report.load((case[0], case[1], "HRP-only"))) for case in cases]
        same = sorted(json.dumps(row, sort_keys=True) for row in data[0]["firewalls"]["rows"]) == sorted(
            json.dumps(row, sort_keys=True) for row in data[1]["firewalls"]["rows"])
        traffic = [report.acceptance(value["traffic"])["verdict"] == "PASS" for value in data]
        if all(local) and same:
            if all(before_local):
                text = ("both HRP-only states already selected the expected local Japan paths before "
                        "the reset. Both reset orders preserved local selection and produced identical "
                        "stable DC-prefix firewall winners in these two lab trials. These results do "
                        "not establish that a reset is required. This is not a universal Azure guarantee")
            else:
                text = ("both tested re-enable orders produced the expected local Japan winner and identical "
                        "stable DC-prefix firewall winners. For these two lab trials, the HRP change followed "
                        "by a complete Azure-facing BGP reset was reproducible. This supports an operational "
                        "reset caveat for the tested conditions, not a universal Azure guarantee")
        elif all(local):
            text = ("both orders selected the expected local Japan paths, but other DC-prefix firewall "
                    "winners differed. The reset did not make the complete measured routing state "
                    "independent of advertisement order")
        else:
            text = ("a complete reset did not consistently produce the expected local Japan winner. "
                    "The re-enable order and resulting winners are shown above; simply adding "
                    "'restart all BGP sessions after changing HRP' is not a sufficient deterministic recipe")
        text += (". Both corrected-workload captures pass all 24 TCP and ICMP directions."
                 if all(traffic) else
                 ". At least one corrected-workload capture still has forwarding failures, so a "
                 "control-plane reset caveat alone does not establish end-to-end B1 success.")
        statements.append("**" + preference + ":** " + text)
    return "\n\n".join(statements)


def section():
    lines = [
        HEADING,
        "This follow-up tests the operational hypothesis that B1 only needs a BGP reset after "
        "an HRP update. It does **not** restart the BIRD daemon, mesh BGP sessions, strongSwan "
        "or WireGuard. Each router runs two Azure-facing BIRD protocols, `azure_0` and `azure_1`: "
        "six adjacencies in total across EU, US and Japan.",
        "Each of four independent controls starts from the same original BIRD policy: three extra "
        "nonlocal EU/US prepends and no extra Japan prepends. All hub branch flags are enabled. "
        "A three-spoke UDR on the Japan workload subnet is applied consistently, so the previously "
        "identified workload-steering omission does not confound these captures.",
        "1. Apply ASPath HRP to every hub and capture the remote Japan winner as the initial history.\n"
        "2. Apply ExpressRoute or VPN HRP and capture the result **before** resetting BGP.\n"
        "3. Disable both Azure-facing protocols on all three routers. Confirm that all six are "
        "down and that every DC-prefix route has withdrawn from the hub firewall views.\n"
        "4. Re-enable all six, deliberately testing two orders: **Japan first**, then EU/US; "
        "or **EU/US first**, then Japan. Each site's two sessions must establish before the next "
        "site is enabled. Capture the first-advertiser route state too.\n"
        "5. Capture full firewall/NVA tables, two stable firewall samples at least 120 seconds "
        "apart, and the 24 sourced DC/Azure TCP/ICMP directions with router packet observations.",
        "The intermediate ASPath-seed and HRP-only captures collect routes, not traffic. "
        "The 24/24 post-reset measurements therefore establish the combined corrected-workload "
        "B1 state; they do not isolate the reset as the cause of every improvement over the "
        "older forwarding captures.",
        "The ordering variation matters: a nominally simultaneous restart cannot guarantee "
        "simultaneous BGP establishment or route arrival. An operational caveat should not "
        "silently depend on the customer path always arriving before the VPN/interhub alternative.",
        "The first VPN/ Japan-first attempt reached the restore reserve before its BGP reset, "
        "and the restore/deallocation CLI calls timed out. It is preserved as an unsuccessful "
        "control, not counted as a routing result. A separate recovery confirmed that the original "
        "hub policies, subnet association, temporary-table absence and ten-VM power inventory "
        "were restored before the VPN controls were retried under a fresh baseline. "
        "The retry wrapper temporarily prevents host sleep while running; no Azure routing "
        "or guest policy is changed by that host-side safeguard.",
        winner_table(),
        outcome(),
        "This remains a small controlled lab sample, not proof for every future failure/reconvergence "
        "sequence. A routing-selection limitation and any remaining forwarding failures are separate "
        "findings. **BIRD normally reloads configuration through `birdc configure`; changing "
        "`bird.conf` does not inherently require restarting its daemon.** Some configuration changes "
        "can restart affected protocols, whereas an export-policy update may be applied without "
        "re-establishing a session.",
        "The source report below renders complete matched EU/JP firewall tables and EU/JP/CN NVA "
        "selections for every reset order. Full BIRD sources, all three hubs, all four NVAs, "
        "intermediate withdrawal/first-advertiser evidence and the packet observations are linked.",
    ]
    for case in CASES:
        base = report.PUBLIC + case[1] + "/"
        lines.append(f"**{case[0]}:** [HRP-only, before reset]({base}HRP-only/scenario-result.json); "
                     f"[after reset]({report.link(case, 'scenario-result.json')}); "
                     f"[transport invariants]({base}bgp-reset/transport-invariants.json); "
                     f"[first advertiser]({base}bgp-reset/first-advertiser-winners.json); "
                     f"[control and exact restore]({base}reset-verdict.json).")
    lines.append("Original BIRD bytes/metadata, mixed hub preferences/branch flags and stable firewall "
                 "winners were restored after each variant. Every temporary workload route table "
                 "was deleted and its subnet association restored. Independent original-state "
                 "verification and exact restoration of the ten originally deallocated VMs "
                 "completed afterward. IPsec configuration hashes, BIRD PIDs and mesh establishment "
                 "times are unchanged across each reset; both IKE SAs are established at the checks. "
                 "The IPsec file hashes were compared privately and are redacted from the public "
                 "captures, including encoded guest output. No IPsec restart is issued; normal "
                 "timed rekeys are not represented as tunnel restarts.")
    lines.append("The first independent original-state check had the same BIRD configuration, hub "
                 "settings, subnet association, stable firewall winners and TCP count as the baseline, "
                 "but one formerly passing ICMP direction (`10.30.0.10` to `10.110.0.10`) "
                 "lost both probes: 13/24 rather than 14/24. That discrepancy is retained, not "
                 "relabeled. A single bounded independent retry checks the original state again; "
                 "the four successful corrected-workload B1 captures are separate measurements.")
    lines.append(f"[Independent closure retry]({report.PUBLIC}hrp-reset-independent-retry-20261019/baseline-verdict.json); "
                 f"[first independent capture with ICMP discrepancy]({report.PUBLIC}hrp-reset-independent-20261019/independent-verification/scenario-result.json); "
                 f"[original VM power restoration]({report.PUBLIC}hrp-reset-final-verify-power-stop-20261019/power-verdict.json); "
                 f"[unsuccessful VPN attempt]({report.PUBLIC}hrp-reset-vpngateway-japan-first-20261019/reset-verdict.json); "
                 f"[separate timeout recovery]({report.PUBLIC}hrp-reset-timeout-recovery-20261019/recovery-verdict.json).")
    return "\n\n".join(lines)


def primary_b1():
    generated = report.design_section("B1", CASES[0])
    matched = generated.split("Matched state:", 1)[1]
    return ("## B1: Customer backbone through HRP\n\n"
            "The primary capture now uses the **19 October ExpressRoute / Japan-first BGP reset** "
            "with the original three extra EU/US nonlocal prepends, no extra Japan prepends, "
            "and spoke-only Azure imports. All hub branch flags are enabled and the Japan workload "
            "subnet has its three-spoke UDR through `10.130.0.4`. No BIRD configuration, mesh session "
            "or IPsec tunnel is restarted or changed during the reset.\n\n"
            "The 17 October withdrawal/return captures and their original lower traffic counts "
            "remain in the historical results below. The new reset section compares both HRP modes "
            "and both establishment orders. A post-reset local winner does not prove that every "
            "HRP update requires a reset, or guarantee selection after every future reconvergence.\n\n"
            "Matched state:" + matched)


def update_article(article):
    if HEADING + "\n" in article:
        before, rest = article.split(HEADING + "\n", 1)
        rest = rest.split("\n## ", 1)
        article = before.rstrip() + ("\n\n## " + rest[1] if len(rest) == 2 else "\n")
    marker = "## Conclusions and boundaries"
    if marker not in article:
        raise RuntimeError("Expected article insertion point missing")
    article = article.replace(marker, section() + "\n\n" + marker, 1)
    heading = "## B1: Customer backbone through HRP\n"
    if heading not in article:
        raise RuntimeError("Expected B1 section missing")
    before, rest = article.split(heading, 1)
    _, rest = rest.split("\n## ", 1)
    article = before + primary_b1() + "\n\n## " + rest
    article = article.replace(
        "primary B1 is the returned three-prepend state.",
        "primary B1 is the 19 October ExpressRoute / Japan-first reset capture.")
    article = article.replace(
        "Traffic and routing are separate findings. Acceptance now covers only",
        "The following traffic counts describe the historical **17 October** captures; the "
        "updated B1 matched tables and reset controls appear below. Traffic and routing are "
        "separate findings. Acceptance covers only")
    return article


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blog", type=pathlib.Path)
    args = parser.parse_args()
    validate()
    folder = report.OUTPUT / "hrp-reset-summary-20261019"
    folder.mkdir(exist_ok=True)
    text = section()
    source = [text]
    for case in CASES:
        data = report.load(case)
        source.append("## Complete matched capture: " + case[0])
        for site in ("eu", "jp"):
            source.extend(["### " + site.upper() + " firewall", report.firewall_table(case, site)])
        for site in ("eu", "jp", "cn"):
            source.extend(["### " + site.upper() + " selected NVA routes", report.nva_table(data, site)])
        source.extend(["### Scoped workload traffic", report.matrix(data)])
    (folder / "README.md").write_text("\n\n".join(source) + "\n", encoding="utf-8")
    if args.blog:
        post = args.blog / "2026-10-vwan-sdwan-three-hub" / "README.md"
        article = post.read_text(encoding="utf-8")
        article = update_article(article)
        post.write_text(article, encoding="utf-8")
        refs = post.with_name("references.md")
        references = refs.read_text(encoding="utf-8")
        heading = "## HRP change followed by BGP-only resets, 19 October 2026"
        if heading in references:
            references = references.split(heading, 1)[0].rstrip() + "\n"
        references += "\n" + heading + "\n\n"
        references += f"[Full report and matched tables]({report.PUBLIC}hrp-reset-summary-20261019/README.md).\n\n"
        for case in CASES:
            references += f"- [{case[0]}]({report.link(case, 'scenario-result.json')}).\n"
        references += "\nOnly Azure-facing `azure_0`/`azure_1` protocols were cycled. Mesh sessions "
        references += "and the BIRD process were preserved; strongSwan and WireGuard were not restarted. "
        references += "The Japan workload UDR was held consistent for all forwarding captures. "
        references += "The two re-enable orders per HRP mode are limited lab observations, not a universal determinism guarantee.\n"
        refs.write_text(references, encoding="utf-8")
    print("PASS: four reset controls and exact closure rendered without assuming local routing/traffic success")


if __name__ == "__main__":
    main()
