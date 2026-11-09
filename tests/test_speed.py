"""speed.py: the live view's numbers and its sampler (no GTK needed)."""
import importlib.util
import os
import pathlib
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("speed", pathlib.Path(__file__).parent.parent / "tarang" / "speed.py")
speed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(speed)


class Numbers(unittest.TestCase):
    def test_rates_pick_their_unit(self):
        self.assertEqual(speed.rate_parts(0), ("0", "B/s"))
        self.assertEqual(speed.rate_parts(999), ("999", "B/s"))
        self.assertEqual(speed.rate_parts(1500), ("1.5", "kB/s"))
        self.assertEqual(speed.rate_parts(146_000), ("146", "kB/s"))
        self.assertEqual(speed.rate_parts(4_300_000), ("4.3", "MB/s"))
        self.assertEqual(speed.rate_parts(2.5e9), ("2.5", "GB/s"))

    def test_scale_labels_drop_a_dot_zero(self):
        self.assertEqual(speed.rate_text(20e6, short=True), "20 MB/s")
        self.assertEqual(speed.rate_text(20e6), "20.0 MB/s")

    def test_sizes_and_durations(self):
        self.assertEqual(speed.size_text(2.2e9), "2.2 GB")
        self.assertEqual(speed.size_text(312e6), "312 MB")
        self.assertEqual(speed.duration_text(30), "less than a minute")
        self.assertEqual(speed.duration_text(5040), "1 h 24 min")
        self.assertEqual(speed.duration_text(3 * 86400 + 7200), "3 d 2 h")

    def test_the_graph_scale_is_round_and_above_the_peak(self):
        for v, want in ((0, 10e3), (11.6e6, 20e6), (4e6, 5e6), (5e6, 5e6), (101e3, 200e3)):
            self.assertEqual(speed.nice_ceiling(v), want, v)


class Sampler(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        os.makedirs(f"{self.dir.name}/wlan0/statistics")
        self.wireless = f"{self.dir.name}/wireless"
        with open(self.wireless, "w") as f:
            f.write("Inter-| sta-|\n face | tus |\n wlan0: 0000   63.  -47.  -256  0 0 0 0 0 0\n")
        self.patches = [mock.patch.object(speed, "SYS_NET", self.dir.name),
                        mock.patch.object(speed, "PROC_WIRELESS", self.wireless)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.dir.cleanup()

    def write(self, rx, tx):
        for name, v in (("rx_bytes", rx), ("tx_bytes", tx)):
            with open(f"{self.dir.name}/wlan0/statistics/{name}", "w") as f:
                f.write(str(v))

    def test_speeds_come_from_the_counters(self):
        t = speed.Traffic()
        clock = iter([100.0, 101.0, 102.0])
        with mock.patch.object(speed.time, "monotonic", lambda: next(clock)):
            self.write(1_000_000, 50_000)
            self.assertTrue(t.sample("wlan0"))
            self.write(3_000_000, 150_000)
            t.sample("wlan0")
            self.write(4_000_000, 160_000)
            t.sample("wlan0")
        self.assertEqual(list(t.rx), [2_000_000, 1_000_000])
        self.assertEqual(t.now(), (1_000_000, 10_000))
        self.assertEqual(t.peak(), (2_000_000, 100_000))
        self.assertEqual(t.average(), (1_500_000, 55_000))
        self.assertEqual(t.totals, (4_000_000, 160_000))
        self.assertEqual(list(t.sig), [90, 90, 90])   # 63/70
        self.assertEqual(t.dbm, -47)

    def test_a_gap_starts_the_minute_over(self):
        t = speed.Traffic()
        clock = iter([100.0, 101.0, 130.0, 131.0])
        with mock.patch.object(speed.time, "monotonic", lambda: next(clock)):
            for rx in (0, 1000, 50_000, 51_000):
                self.write(rx, 0)
                t.sample("wlan0")
        self.assertEqual(list(t.rx), [1000])   # nothing averaged over the time the panel was closed

    def test_a_missing_card_is_not_a_crash(self):
        t = speed.Traffic()
        self.assertFalse(t.sample("wlan9"))
        self.assertEqual(t.now(), (0.0, 0.0))

    def test_never_negative_when_counters_reset(self):
        t = speed.Traffic()
        clock = iter([100.0, 101.0])
        with mock.patch.object(speed.time, "monotonic", lambda: next(clock)):
            self.write(9_000_000, 9_000)
            t.sample("wlan0")
            self.write(100, 10)
            t.sample("wlan0")
        self.assertEqual(t.now(), (0, 0))


if __name__ == "__main__":
    unittest.main()
