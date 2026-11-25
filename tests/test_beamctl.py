"""Parser tests for beamctl. Run: python3 -m unittest discover -s tests"""

import importlib.machinery
import importlib.util
import json
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


class PerCastFirewall(unittest.TestCase):
    """Open for one screen on cast, closed afterwards, with ufw faked by a rules file."""

    HOST = "192.168.1.50"
    TUPLE = "### tuple ### allow udp 60000:60010 0.0.0.0/0 any {src} in\n"

    def setUp(self):
        import tempfile
        self.dir = tempfile.TemporaryDirectory()
        d = self.dir.name
        self.saved = {k: getattr(beamctl, k) for k in
                      ("STATE_DIR", "FIREWALL_PATH", "UFW_RULES", "ufw_enabled", "pkexec_ufw")}
        beamctl.STATE_DIR = d
        beamctl.FIREWALL_PATH = os.path.join(d, "firewall.json")
        beamctl.UFW_RULES = os.path.join(d, "user.rules")
        beamctl.ufw_enabled = lambda: True
        self.calls = []
        self.write_rules("")

        def fake_pkexec(args):
            self.calls.append(args)
            if self.refuse:
                return 126, "password dialog dismissed"
            line = self.TUPLE.format(src=args[args.index("from") + 1])
            rules = self.read_rules()
            self.write_rules(rules.replace(line, "") if args[0] == "delete" else rules + line)
            return 0, ""
        self.refuse = False
        beamctl.pkexec_ufw = fake_pkexec

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(beamctl, k, v)
        self.dir.cleanup()

    def write_rules(self, text):
        with open(beamctl.UFW_RULES, "w") as f:
            f.write(text)

    def read_rules(self):
        with open(beamctl.UFW_RULES) as f:
            return f.read()

    def test_open_then_close_adds_and_removes_one_host_rule(self):
        ok, _ = beamctl.firewall_open(self.HOST)
        self.assertTrue(ok)
        self.assertTrue(beamctl.rule_for_host(self.read_rules(), self.HOST))
        self.assertEqual(self.calls[0], ["allow", "from", self.HOST, "to", "any", "port", "60000:60010",
                                         "proto", "udp"])
        ok, msg = beamctl.firewall_close()
        self.assertTrue(ok, msg)
        self.assertFalse(beamctl.rule_for_host(self.read_rules(), self.HOST))
        self.assertEqual(self.calls[1][0], "delete")
        self.assertEqual(beamctl.read_firewall(), {})

    def test_second_close_does_not_prompt_again(self):
        beamctl.firewall_open(self.HOST)
        beamctl.firewall_close()
        beamctl.firewall_close()
        self.assertEqual(len(self.calls), 2)

    def test_dismissed_password_means_no_cast(self):
        self.refuse = True
        ok, msg = beamctl.firewall_open(self.HOST)
        self.assertFalse(ok)
        self.assertIn("dismissed", msg)
        self.assertEqual(beamctl.read_firewall(), {})

    def test_existing_subnet_rule_is_used_and_never_removed(self):
        self.write_rules(self.TUPLE.format(src="192.168.1.0/24"))
        ok, _ = beamctl.firewall_open(self.HOST)
        self.assertTrue(ok)
        self.assertEqual(self.calls, [])
        beamctl.firewall_close()
        self.assertEqual(self.calls, [])
        self.assertIn("192.168.1.0/24", self.read_rules())

    def test_ufw_off_needs_nothing(self):
        beamctl.ufw_enabled = lambda: False
        self.assertTrue(beamctl.firewall_open(self.HOST)[0])
        self.assertEqual(self.calls, [])

    def test_rule_left_behind_is_reported_stale(self):
        beamctl.firewall_open(self.HOST)
        self.assertEqual(beamctl.firewall_status(False), {"host": self.HOST, "stale": True})
        self.assertEqual(beamctl.firewall_status(True), {"host": self.HOST, "stale": False})

    def test_rule_removed_by_hand_clears_state(self):
        beamctl.firewall_open(self.HOST)
        self.write_rules("")
        self.assertEqual(beamctl.firewall_status(False), {})
        self.assertEqual(beamctl.read_firewall(), {})


class PkexecCommand(unittest.TestCase):
    """Which program pkexec is asked to run decides the dialog's wording."""

    def run_with(self, installed, args):
        saved = (beamctl.helpers_installed, beamctl.subprocess.run, beamctl.shutil.which, beamctl.ufw_path)
        seen = {}

        class Done:
            returncode, stdout, stderr = 0, "", ""

        def fake_run(cmd, **kw):
            seen["cmd"] = cmd
            return Done()
        beamctl.helpers_installed = lambda: installed
        beamctl.subprocess.run = fake_run
        beamctl.shutil.which = lambda name: "/usr/bin/" + name
        beamctl.ufw_path = lambda: "/usr/bin/ufw"
        try:
            beamctl.pkexec_ufw(args)
        finally:
            (beamctl.helpers_installed, beamctl.subprocess.run, beamctl.shutil.which, beamctl.ufw_path) = saved
        return seen["cmd"]

    def test_helpers_get_just_the_address(self):
        rule = beamctl.ufw_rule("192.168.1.50")
        self.assertEqual(self.run_with(True, rule),
                         ["/usr/bin/pkexec", "/usr/local/libexec/beam/beam-firewall-open", "192.168.1.50"])
        self.assertEqual(self.run_with(True, ["delete"] + rule),
                         ["/usr/bin/pkexec", "/usr/local/libexec/beam/beam-firewall-close", "192.168.1.50"])

    def test_without_helpers_falls_back_to_ufw(self):
        rule = beamctl.ufw_rule("192.168.1.50")
        self.assertEqual(self.run_with(False, rule), ["/usr/bin/pkexec", "/usr/bin/ufw"] + rule)

    def test_helper_files_ship_with_the_plugin(self):
        for src, dest, mode in beamctl.system_files():
            self.assertTrue(os.path.isfile(src), src)
        self.assertEqual(len(beamctl.helper_install_commands()), 3)


class ShareChoice(unittest.TestCase):
    """--choose drops only doubletake's saved screen pick, never the pairing."""

    def setUp(self):
        import tempfile
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "credentials.json")
        self.creds = {
            "E4:65:64:61:E4:69": {"pairing_id": "p1", "ed25519_seed": "s1", "restore_token": "t1"},
            "AA:BB:CC:DD:EE:FF": {"pairing_id": "p2", "restore_token": "t2"},
        }
        with open(self.path, "w") as f:
            json.dump(self.creds, f)

    def tearDown(self):
        self.dir.cleanup()

    def load(self):
        with open(self.path) as f:
            return json.load(f)

    def test_drops_only_that_screens_token(self):
        self.assertEqual(beamctl.forget_share_choice("e4:65:64:61:e4:69", self.path), 1)
        d = self.load()
        self.assertNotIn("restore_token", d["E4:65:64:61:E4:69"])
        self.assertEqual(d["E4:65:64:61:E4:69"]["ed25519_seed"], "s1")
        self.assertEqual(d["AA:BB:CC:DD:EE:FF"]["restore_token"], "t2")

    def test_without_device_id_drops_every_token(self):
        self.assertEqual(beamctl.forget_share_choice("", self.path), 2)
        self.assertTrue(all("restore_token" not in c for c in self.load().values()))

    def test_keeps_file_private(self):
        beamctl.forget_share_choice("", self.path)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_missing_file_is_fine(self):
        self.assertEqual(beamctl.forget_share_choice("", self.path + ".nope"), 0)


class SourceHandover(unittest.TestCase):
    """The old cast's watcher must leave the firewall and sound to the new cast."""

    def setUp(self):
        self.saved = beamctl.is_doubletake

    def tearDown(self):
        beamctl.is_doubletake = self.saved

    def test_marked_before_restart(self):
        beamctl.is_doubletake = lambda pid: False
        self.assertTrue(beamctl.handed_over(100, {"pid": 100, "handoverFrom": 100}))

    def test_new_cast_running(self):
        beamctl.is_doubletake = lambda pid: pid == 200
        self.assertTrue(beamctl.handed_over(100, {"pid": 200, "handoverFrom": 100}))
        self.assertTrue(beamctl.handed_over(100, {"pid": 200}))

    def test_plain_stop_is_not_a_handover(self):
        beamctl.is_doubletake = lambda pid: False
        self.assertFalse(beamctl.handed_over(100, {"pid": None}))
        self.assertFalse(beamctl.handed_over(100, {"pid": 100}))

    def test_failed_replacement_is_not_a_handover_for_its_own_watcher(self):
        beamctl.is_doubletake = lambda pid: False
        self.assertFalse(beamctl.handed_over(200, {"pid": 200, "handoverFrom": 100}))


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
