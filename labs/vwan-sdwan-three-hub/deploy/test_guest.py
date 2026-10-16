"""Regression checks for guest provenance, transport and protected deployment."""
import json
import subprocess
import unittest
from unittest.mock import patch

import guest

HUBS = {"eu": ["10.250.0.69", "10.250.0.70"],
        "us": ["10.250.2.70", "10.250.2.69"]}
VPN = [{"bgp": "169.254.21.2", "public": "20.27.135.137", "id": 41},
       {"bgp": "169.254.21.6", "public": "4.190.54.71", "id": 42}]
KEYS = {s: {"private": "TEST_PRIVATE", "public": "TEST_PUBLIC"} for s in guest.SITES}


class GuestTests(unittest.TestCase):
    def test_pair_addresses_and_unique_local_ports(self):
        for site in guest.SITES:
            links = guest.links(site)
            self.assertEqual(len(links), 3)
            self.assertEqual(len({link["port"] for link in links}), 3)
            for link in links:
                reverse = next(x for x in guest.links(link["peer"]) if x["peer"] == site)
                self.assertEqual(link["remote"], reverse["local"])
                self.assertEqual(link["local"], reverse["remote"])
                self.assertEqual(link["interface"], reverse["interface"])

    def test_strict_provenance_and_kernel_forwarding(self):
        for site in guest.SITES:
            config = guest.bird(site, HUBS, VPN)
            self.assertNotIn("import all", config)
            self.assertNotIn("export all", config)
            self.assertNotIn("blackhole", config)
            self.assertIn('proto = "own_dc" || proto ~ "mesh_*"', config)
            self.assertIn('proto ~ "azure_*"', config)
            self.assertIn("igp table underlay4", config)
            self.assertIn("kernel table 254", config)
            self.assertEqual(config.count("hold time 180"), 3 if site == "cn" else 5)
            self.assertEqual(config.count("keepalive time 60"), 3 if site == "cn" else 5)
            self.assertNotIn("allow local as", config)

    def test_underlay_and_vpn_custom_routes(self):
        config = guest.bird("jp", HUBS, VPN)
        self.assertEqual(config.count("local 169.254.21.1 as 65013"), 2)
        self.assertIn('route 169.254.21.2/32 via "xfrm41"', config)
        self.assertIn('route 169.254.21.6/32 via "xfrm42"', config)
        self.assertNotIn("169.254.21.5", config)
        eu = guest.bird("eu", HUBS, VPN)
        self.assertIn("bgp_next_hop = __GATEWAY__", eu)
        self.assertIn("route 10.250.0.69/32 via __GATEWAY__", eu)
        self.assertNotIn("bgp_next_hop = 10.250.0.", eu)

    def test_wireguard_allowed_source_and_no_data_nat(self):
        for site in guest.SITES:
            files = guest.router_files(site, HUBS, VPN, KEYS, "TEST_PSK", "104.46.220.128")
            for link in guest.links(site):
                conf = files[f"/etc/wireguard/{link['interface']}.conf"]
                self.assertIn("Table = off", conf)
                self.assertIn("MTU = 1380", conf)
                self.assertIn("FwMark = 0x200", conf)
                self.assertIn(f"Endpoint = {guest.IPS[link['peer']]}:{link['port']}", conf)
                self.assertIn(f"ListenPort = {link['port']}", conf)
                for prefix in guest.SPOKE_PREFIXES:
                    self.assertIn(prefix, conf)
            net = files["/opt/threehub/network.sh"]
            self.assertNotIn("MASQUERADE", net)
            self.assertNotIn("TH_WG_", net)
            self.assertNotIn("SNAT", net)
            self.assertNotIn("REDIRECT", net)
            self.assertIn("fwmark 0x200 lookup 100", net)
            for peer, ip in guest.IPS.items():
                if peer != site:
                    self.assertIn(f"ip route replace table 100 {ip}/32", net)
                    self.assertNotIn(f"ip route replace {ip}/32", net)

    def test_swan_policy_and_persistence(self):
        files = guest.router_files("jp", HUBS, VPN, KEYS, "TEST_PSK", "104.46.220.128")
        conf = files["/etc/swanctl/swanctl.conf"]
        self.assertIn("esp_proposals = aes256-sha256-modp2048", conf)
        self.assertEqual(conf.count("local_ts = 0.0.0.0/0"), 2)
        self.assertEqual(conf.count("set_mark_out = 0x200"), 2)
        self.assertIn("threehub-ipsec.service", files["/etc/systemd/system/bird.service.d/threehub.conf"])
        self.assertIn("install_routes = no", files["/etc/strongswan.d/threehub.conf"])

    def test_secure_sources_and_failure_propagation(self):
        sources = {"router-eu": "SECRET_SCRIPT", "probe-dc-jp": "OTHER_SCRIPT"}
        document, params = guest.managed_template(sources, "stage")
        self.assertNotIn("SECRET_SCRIPT", json.dumps(document))
        self.assertEqual(params["parameters"]["router_eu"]["value"], "SECRET_SCRIPT")
        for value in document["parameters"].values():
            self.assertEqual(value["type"], "secureString")
        for resource in document["resources"]:
            self.assertFalse(resource["properties"]["asyncExecution"])
            self.assertTrue(resource["properties"]["treatFailureAsDeploymentFailure"])
            self.assertEqual(resource["properties"]["timeoutInSeconds"], 900)

    def test_cloudinit_backup_and_parse_before_activation(self):
        stage = guest.stage_script(guest.listener_files(), "eu")
        self.assertIn("timeout 240 cloud-init status --wait --long", stage)
        self.assertIn("backup.tar", stage)
        self.assertIn("bird -p -c /etc/bird/bird.conf", stage)
        self.assertNotIn("systemctl restart bird", stage)
        active = guest.activate_script("eu")
        self.assertLess(active.index("bird -p"), active.index("systemctl restart bird"))

    def test_japan_uses_only_swanctl_daemon(self):
        active = guest.activate_script("jp")
        self.assertLess(active.index("systemctl disable --now strongswan-starter.service"),
                        active.index("systemctl enable --now strongswan.service"))
        self.assertIn("if systemctl list-unit-files strongswan-starter.service", active)
        self.assertNotIn("strongswan-starter", guest.activate_script("eu"))

    def test_listener_can_read_public_content_but_keys_stay_private(self):
        stage = guest.stage_script(guest.listener_files())
        final = guest.write_final_files(guest.listener_files())
        for script in (stage, final):
            self.assertIn("0o644 if path.startswith('/var/lib/lab-http/')", script)
            self.assertIn("else 0o600", script)
        self.assertIn("User=nobody", guest.listener_files()["/etc/systemd/system/lab-http.service"])

    def test_restore_uses_seekable_route_input(self):
        restore = guest.restore_script("jp")
        self.assertIn("stdin=saved_routes", restore)
        self.assertIn("(root/'routes.save').open('rb')", restore)
        self.assertNotIn("input=(root/'routes.save').read_bytes()", restore)
        self.assertIn("if 'fwmark 0x200 lookup 100' in marked:", restore)
        self.assertIn("Restored route snapshot mismatch", restore)
        self.assertIn("Restored service enablement mismatch", restore)
        self.assertIn("'activeStateRecorded':False", restore)

    def test_instanceview_query_is_windows_cmd_safe(self):
        with patch.object(guest.control, "az", return_value={
                "properties": {"instanceView": {"exitCode": 0}}}) as az, \
                patch.object(guest.control, "save"), \
                patch.object(guest.control, "account_id", return_value="TEST_SUBSCRIPTION"):
            guest.outputs("stage", ["router-eu"])
        arguments = az.call_args.args[0]
        self.assertIn("--url-parameters", arguments)
        self.assertTrue(arguments[arguments.index("--url-parameters") + 1].startswith("@"))
        self.assertNotIn("&", arguments[arguments.index("--url") + 1])

    def test_activation_rewrites_all_files_and_preserves_backups(self):
        snapshot = {"runtimeEndpoints": {"router-jp": {"publicIp": "104.46.220.128"}}}
        with patch.object(guest, "bindings", return_value=(snapshot, HUBS, VPN)), \
                patch.object(guest, "keys", return_value=KEYS), \
                patch.object(guest.pathlib.Path, "read_text",
                             return_value=json.dumps({"parameters": {"vpnSharedKey": {"value": "TEST_PSK"}}})):
            scripts = guest.scripts("activate")
        for name, script in scripts.items():
            self.assertLess(script.index("final_hashes"), script.index("systemctl enable --now"))
            self.assertIn("activation-files.json", script)
            self.assertIn("originalBackupsPreserved", script)
            self.assertNotIn("tarfile.open(root/'backup.tar'", script)
            self.assertIn("tarfile.open(root/'activation-files.tar','w')", script)
        self.assertIn("threehub-probe.service", scripts["probe-dc-jp"])
        self.assertIn("time.monotonic()+120", scripts["router-eu"])
        self.assertNotIn("test \"$(birdc show protocols", scripts["router-eu"])

    def test_shell_syntax(self):
        scripts = [guest.stage_script(guest.listener_files(), site) for site in (*guest.SITES, None)]
        scripts += [guest.activate_script(site) for site in (*guest.SITES, None)]
        scripts += [guest.network(site, HUBS, VPN) for site in guest.SITES]
        scripts += [guest.smoke_script(site) for site in (*guest.SITES, None)]
        scripts += [guest.restore_script(site) for site in (*guest.SITES, None)]
        scripts += [guest.write_final_files(guest.listener_files())]
        scripts += [guest.activation_proof(site) for site in (*guest.SITES, None)]
        for text in scripts:
            result = subprocess.run(["wsl", "-d", "Ubuntu-24.04", "--exec", "bash", "-n"],
                                    input=text.encode(), capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
