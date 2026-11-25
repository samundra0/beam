"""Parser tests for beamctl. Run: python3 -m unittest discover -s tests"""

import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "..", "beamctl")
loader = importlib.machinery.SourceFileLoader("beamctl", PATH)
spec = importlib.util.spec_from_loader("beamctl", loader)
beamctl = importlib.util.module_from_spec(spec)
loader.exec_module(beamctl)

HORION_AIRPLAY = ('=;wlp0s20f3;IPv4;Horion_ld;AirPlay Remote Video;local;-9a-a5-0c-01-74-eb.local;192.168.26.1;7027;'
                  '"deviceid=E4:65:64:61:E4:69" "features=0x5A7FFFF6,0x1E" "flags=0x4" "model=AppleTV3,2" '
                  '"srcvers=220.68" "vv=2"')
HORION_AIRPLAY_V6 = HORION_AIRPLAY.replace(";IPv4;", ";IPv6;").replace("192.168.26.1", "fe80::1")
HORION_RAOP = ('=;wlp0s20f3;IPv4;E4\\05865\\05864\\05861\\058E4\\05869\\064Horion_ld;AirTunes Remote Audio;local;'
               '-9a-a5-0c-01-74-eb.local;192.168.26.1;47027;"am=AppleTV3,2" "tp=UDP"')


class AvahiParsing(unittest.TestCase):
    def test_unescape(self):
        self.assertEqual(beamctl.avahi_unescape("E4\\05865\\064Horion_ld"), "E4:65@Horion_ld")
        self.assertEqual(beamctl.avahi_unescape("Living\\032Room"), "Living Room")

    def test_airplay_line(self):
        r = beamctl.parse_avahi_line(HORION_AIRPLAY)
        self.assertEqual(r["name"], "Horion_ld")
        self.assertEqual(r["address"], "192.168.26.1")
        self.assertEqual(r["host"], "-9a-a5-0c-01-74-eb.local")
        self.assertEqual(r["port"], 7027)
        self.assertEqual(r["txt"]["deviceid"], "E4:65:64:61:E4:69")
        self.assertEqual(r["txt"]["model"], "AppleTV3,2")

    def test_non_resolved_lines_ignored(self):
        self.assertIsNone(beamctl.parse_avahi_line("+;wlp0s20f3;IPv4;Horion_ld;AirPlay Remote Video;local"))
        self.assertIsNone(beamctl.parse_avahi_line("=;short;line"))

    def test_groups_horion_and_prefers_raop_port_and_ipv4(self):
        air = [beamctl.parse_avahi_line(HORION_AIRPLAY_V6), beamctl.parse_avahi_line(HORION_AIRPLAY)]
        raop = [beamctl.parse_avahi_line(HORION_RAOP)]
        devices = beamctl.group_receivers(air, raop)
        self.assertEqual(len(devices), 1)
        d = devices[0]
        self.assertEqual(d["name"], "Horion_ld")
        self.assertEqual(d["deviceId"], "E4:65:64:61:E4:69")
        self.assertEqual(d["host"], "192.168.26.1")
        self.assertEqual(d["model"], "AppleTV3,2")
        self.assertEqual(d["candidates"], [47027, 7027, 7000])

    def test_raop_hex_prefix_gets_colons(self):
        line = HORION_RAOP.replace("E4\\05865\\05864\\05861\\058E4\\05869", "E46564 61E469".replace(" ", ""))
        devices = beamctl.group_receivers([], [beamctl.parse_avahi_line(line)])
        self.assertEqual(devices[0]["deviceId"], "E4:65:64:61:E4:69")
        self.assertEqual(devices[0]["name"], "Horion_ld")

    def test_markup_name_stays_text(self):
        line = HORION_AIRPLAY.replace("Horion_ld", "<img src=x>")
        self.assertEqual(beamctl.parse_avahi_line(line)["name"], "<img src=x>")


def airplay_line(name, model, features, port=7000, addr="192.168.1.20"):
    return (f'=;wlan0;IPv4;{name};AirPlay Remote Video;local;{name}.local;{addr};{port};'
            f'"deviceid=AA:BB:CC:DD:EE:{len(name):02X}" "features={features}" "model={model}"')


class ScreenFilter(unittest.TestCase):
    def group(self, airplay=(), raop=()):
        p = beamctl.parse_avahi_line
        return beamctl.group_receivers([p(l) for l in airplay], [p(l) for l in raop])

    def test_horion_is_a_screen(self):
        [d] = self.group([HORION_AIRPLAY], [HORION_RAOP])
        self.assertTrue(d["screen"])

    def test_apple_tv_and_tv_are_screens(self):
        ds = self.group([airplay_line("Living Room", "AppleTV14,1", "0x4A7FDFD5,0xBC177FDE"),
                         airplay_line("Samsung", "UN55TU8300", "0x7F8AD0,0x38BCF46")])
        self.assertTrue(all(d["screen"] for d in ds))

    def test_homepod_is_not_a_screen(self):
        [d] = self.group([airplay_line("Kitchen", "AudioAccessory5,1", "0x4A7FDFD5,0xBC157FDE")])
        self.assertFalse(d["screen"])

    def test_speaker_without_mirroring_bit_is_not_a_screen(self):
        [d] = self.group([airplay_line("Sonos One", "S13", "0x445F8A00,0x1C340")])
        self.assertFalse(d["screen"])

    def test_raop_only_receiver_is_not_a_screen(self):
        [d] = self.group([], [HORION_RAOP])
        self.assertFalse(d["screen"])

    def test_unknown_features_are_kept(self):
        [d] = self.group([airplay_line("Odd", "Thing", "")])
        self.assertTrue(d["screen"])


class Firewall(unittest.TestCase):
    RULES = """
### tuple ### allow udp 53317 0.0.0.0/0 any 0.0.0.0/0 in
### tuple ### allow udp 60000:60010 0.0.0.0/0 any 192.168.26.0/24 in
"""

    def test_subnet_rule(self):
        self.assertTrue(beamctl.ufw_allows(self.RULES, "192.168.26.200"))
        self.assertFalse(beamctl.ufw_allows(self.RULES, "10.10.131.149"))
        self.assertFalse(beamctl.ufw_allows(self.RULES, ""))

    def test_private_ranges(self):
        rules = "### tuple ### allow udp 60000:60010 0.0.0.0/0 any 10.0.0.0/8 in\n"
        self.assertTrue(beamctl.ufw_allows(rules, "10.10.131.149"))

    def test_partial_range_not_enough(self):
        rules = "### tuple ### allow udp 60000:60005 0.0.0.0/0 any 0.0.0.0/0 in\n"
        self.assertFalse(beamctl.ufw_allows(rules, "192.168.1.5"))

    def test_tcp_rule_ignored(self):
        rules = "### tuple ### allow tcp 60000:60010 0.0.0.0/0 any 0.0.0.0/0 in\n"
        self.assertFalse(beamctl.ufw_allows(rules, "192.168.1.5"))


class LogState(unittest.TestCase):
    LIVE = """2026/11/25 12:35:09 connected to: Apple TV (model: AppleTV3,2, initialVolume: unavailable, volumeControlType: 0)
2026/11/25 12:35:09 pairing complete
2026/11/25 12:35:09 FairPlay setup complete
2026/11/25 12:35:10 mirror session ready (data port: 7127)
2026/11/25 12:35:10 audio capture started
"""

    def test_connecting(self):
        self.assertEqual(beamctl.log_state("")["phase"], "connecting")

    def test_pairing(self):
        self.assertEqual(beamctl.log_state(self.LIVE.splitlines()[0])["phase"], "pairing")

    def test_live(self):
        s = beamctl.log_state(self.LIVE)
        self.assertEqual(s["phase"], "live")
        self.assertFalse(s["ended"])
        self.assertEqual(s["lastError"], "")

    def test_ended(self):
        s = beamctl.log_state(self.LIVE + "2026/11/25 12:40:00 shutting down...\n2026/11/25 12:40:00 stream ended\n")
        self.assertTrue(s["ended"])

    def test_error(self):
        s = beamctl.log_state("2026/11/25 12:00:01 session bring-up failed: dial tcp 1.2.3.4:7000: connection refused\n")
        self.assertEqual(s["lastError"], "session bring-up failed: dial tcp 1.2.3.4:7000: connection refused")

    def test_needs_code(self):
        self.assertTrue(beamctl.log_state("Enter the PIN shown on the receiver: ")["needsCode"])
        self.assertTrue(beamctl.log_state("Enter the code shown on the receiver, or its configured password: ")["needsCode"])


class Args(unittest.TestCase):
    def test_arg_value(self):
        args = ["doubletake", "-target", "192.168.26.1", "-port", "47027"]
        self.assertEqual(beamctl.arg_value(args, "-target"), "192.168.26.1")
        self.assertEqual(beamctl.arg_value(args, "-port"), "47027")
        self.assertEqual(beamctl.arg_value(["doubletake", "--target=1.2.3.4"], "-target"), "1.2.3.4")
        self.assertEqual(beamctl.arg_value(args, "-code"), "")


if __name__ == "__main__":
    unittest.main()
