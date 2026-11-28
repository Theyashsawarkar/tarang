"""links.py: every kind of connection said the same way (no GTK needed)."""
import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location("links", pathlib.Path(__file__).parent.parent / "tarang" / "links.py")
links = importlib.util.module_from_spec(spec)
spec.loader.exec_module(links)

ETH = {"name": "Wired connection 1", "type": "ethernet", "label": "Ethernet", "device": "enp3s0", "primary": True,
       "speed": 1000, "duplex": "full", "ip4": ["192.168.1.42/24"], "ip6": ["fe80::1/64", "2001:db8::42/64"],
       "gateway": "192.168.1.1", "dns": ["192.168.1.1"], "mac": "02:00:00:00:00:03", "driver": "r8169"}
VPN = {"name": "Office VPN", "type": "vpn", "label": "VPN", "device": "wlan0", "vpn": True, "via": "Home Fiber 5G",
       "via_device": "wlan0", "server": "vpn.example.org:1194", "ip4": ["10.8.0.6/24"], "gateway": "10.8.0.1"}


class Words(unittest.TestCase):
    def test_speeds(self):
        self.assertEqual(links.speed_text(1000), "1 Gb/s")
        self.assertEqual(links.speed_text(2500), "2.5 Gb/s")
        self.assertEqual(links.speed_text(100), "100 Mb/s")
        self.assertEqual(links.speed_text(0), "")
        self.assertEqual(links.speed_text(None), "")

    def test_subtitles(self):
        self.assertEqual(links.subtitle(ETH), "Ethernet · 1 Gb/s · 192.168.1.42")
        self.assertEqual(links.subtitle(VPN), "VPN · over Home Fiber 5G · 10.8.0.6")
        self.assertEqual(links.subtitle({"type": "mobile", "label": "Mobile", "operator": "40445"}),
                         "Mobile · operator 40445")

    def test_ipv6_skips_link_local(self):
        self.assertEqual(links.first_ip(ETH["ip6"], v6=True), "2001:db8::42")
        self.assertEqual(links.first_ip(["fe80::1/64"], v6=True), "fe80::1")

    def test_facts_by_kind(self):
        f = dict(links.facts(ETH))
        self.assertEqual(f["Link speed"], "1 Gb/s · full duplex")
        self.assertEqual(f["Route"], "Default: your traffic goes this way")
        self.assertEqual(f["Device"], "enp3s0 · r8169")
        v = dict(links.facts(VPN, "Home Fiber 5G"))
        self.assertEqual(v["Server"], "vpn.example.org:1194")
        self.assertEqual(v["Rides on"], "Home Fiber 5G (wlan0)")
        self.assertEqual(v["Route"], "Standby: Home Fiber 5G is used first")
        self.assertNotIn("Link speed", v)

    def test_graph_device(self):
        self.assertEqual(links.graph_device(ETH), "enp3s0")
        self.assertEqual(links.graph_device({"vpn_device": "wg0", "device": ""}), "wg0")
        self.assertEqual(links.graph_device({"via_device": "wlan0"}), "wlan0")


class Sources(unittest.TestCase):
    def test_live_state_with_connections(self):
        ls = {"running": True, "connections": [ETH, {"type": "hotspot", "name": "Vayu Hotspot"}]}
        self.assertEqual([c["name"] for c in links.from_live(ls)], ["Wired connection 1"])

    def test_older_vyom_wired_name_and_its_device(self):
        ls = {"running": True, "wired": "Wired connection 1", "device": "wlan0", "active": None}
        out = links.from_live(ls, ["wlan0", "enp3s0"], "wlan0")
        self.assertEqual(out[0]["device"], "enp3s0")
        self.assertEqual(out[0]["type"], "ethernet")

    def test_older_vyom_wifi(self):
        ls = {"running": True, "wired": "", "device": "wlan0", "active": {"ssid": "Home", "strength": 80},
              "connection": {"name": "Home"}}
        self.assertEqual(links.from_live(ls)[0]["type"], "wifi")

    def test_not_running(self):
        self.assertIsNone(links.from_live(None))
        self.assertIsNone(links.from_live({"running": False}))

    def test_nmcli(self):
        lines = [["enp3s0", "ethernet", "connected", "Wired connection 1"],
                 ["usb0", "ethernet", "connected", "Pixel 8 USB"],
                 ["wlan0", "wifi", "connected", "Home"],
                 ["docker0", "bridge", "connected (externally)", "docker0"],
                 ["lo", "loopback", "connected (externally)", "lo"],
                 ["wwan0", "gsm", "connected", "Mobile"]]
        drivers = {"enp3s0": "r8169", "usb0": "rndis_host", "wwan0": "qmi_wwan"}
        out = links.parse_nmcli(lines, lambda d: {"driver": drivers.get(d, ""), "speed": 1000 if d == "enp3s0" else 0})
        self.assertEqual([(c["name"], c["type"]) for c in out],
                         [("Wired connection 1", "ethernet"), ("Pixel 8 USB", "usb"), ("Mobile", "mobile")])
        self.assertTrue(out[0]["primary"])


if __name__ == "__main__":
    unittest.main()
