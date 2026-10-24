import unittest
from datetime import datetime, timezone

from ofde.tle import (checksum, parse_tle, parse_implied_exp, format_implied_exp, format_tle, with_checksum)

L1 = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
L2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"


def codes(issues):
    return {i.code for i in issues if i.severity == "error"}


class TestChecksumAndParse(unittest.TestCase):
    def test_checksum_published_sample(self):
        self.assertEqual(checksum(L1), 7)
        self.assertEqual(checksum(L2), 7)

    def test_checksum_minus_counts_one(self):
        self.assertEqual(checksum("-" * 68), 68 % 10)

    def test_parse_valid(self):
        t, issues = parse_tle(L1, L2, "ISS")
        self.assertIsNotNone(t)
        self.assertEqual(t.catalog_number, "25544")
        self.assertEqual(t.name, "ISS")
        self.assertAlmostEqual(t.inclination_deg, 51.6416)
        self.assertAlmostEqual(t.eccentricity, 0.0006703)
        self.assertAlmostEqual(t.mean_motion_rev_per_day, 15.72125391)
        self.assertAlmostEqual(t.bstar, -1.1606e-5, places=12)
        exp = datetime(2008, 9, 20, 12, 25, 40, 104000, tzinfo=timezone.utc)
        self.assertLess(abs((t.epoch - exp).total_seconds()), 1e-3)
        self.assertFalse(t.is_deep_space)

    def test_bad_checksum_rejected(self):
        bad = L1[:68] + "8"
        t, issues = parse_tle(bad, L2)
        self.assertIsNone(t)
        self.assertIn("CHECKSUM_MISMATCH", codes(issues))

    def test_bad_length_rejected(self):
        t, issues = parse_tle(L1[:-1], L2)
        self.assertIsNone(t)
        self.assertIn("BAD_LENGTH", codes(issues))

    def test_wrong_line_number_rejected(self):
        t, issues = parse_tle(L2, L1)
        self.assertIsNone(t)
        self.assertIn("BAD_LINE_NUMBER", codes(issues))

    def test_catalog_mismatch(self):
        l2 = with_checksum("2 25545" + L2[7:68])
        t, issues = parse_tle(L1, l2)
        self.assertIsNone(t)
        self.assertIn("CATALOG_MISMATCH", codes(issues))

    def test_out_of_range_inclination(self):
        l2 = with_checksum(L2[:8] + "181.0000" + L2[16:68])
        t, issues = parse_tle(L1, l2)
        self.assertIsNone(t)
        self.assertIn("OUT_OF_RANGE", codes(issues))

    def test_non_numeric_field(self):
        l2 = with_checksum(L2[:8] + "5x.6416" + " " + L2[17:68])
        t, issues = parse_tle(L1, l2)
        self.assertIsNone(t)
        self.assertIn("BAD_NUMBER", codes(issues))

    def test_zero_mean_motion_rejected(self):
        l2 = with_checksum(L2[:52] + " 0.00000000" + L2[63:68])
        t, issues = parse_tle(L1, l2)
        self.assertIsNone(t)
        self.assertIn("OUT_OF_RANGE", codes(issues))

    def test_trailing_whitespace_is_warned_not_hidden(self):
        t, issues = parse_tle(L1 + "  \n", L2 + "\r\n")
        self.assertIsNotNone(t)
        self.assertEqual(sum(1 for i in issues if i.code == "TRAILING_WHITESPACE_REMOVED"), 1)

    def test_invalid_epoch_day(self):
        l1 = with_checksum(L1[:20] + "400.00000000" + L1[32:68])
        t, issues = parse_tle(l1, L2)
        self.assertIsNone(t)
        self.assertIn("BAD_EPOCH", codes(issues))

    def test_deep_space_flag(self):
        l2 = with_checksum(L2[:52] + " 2.00561730" + L2[63:68])
        t, issues = parse_tle(L1, l2)
        self.assertTrue(t.is_deep_space)
        self.assertIn("DEEP_SPACE", {i.code for i in issues})


class TestExpAndFormat(unittest.TestCase):
    def test_exp_roundtrip(self):
        for v in (-1.1606e-5, 2.8098e-5, 0.0, 1.0, -0.5, 3.0e-4):
            self.assertAlmostEqual(parse_implied_exp(format_implied_exp(v)), v, places=9 if abs(v) < 1 else 5)

    def test_exp_known(self):
        self.assertAlmostEqual(parse_implied_exp(" 28098-4"), 2.8098e-5)
        self.assertEqual(format_implied_exp(-1.1606e-5), "-11606-4")
        self.assertEqual(format_implied_exp(0.0), " 00000+0")

    def test_bad_exp(self):
        with self.assertRaises(ValueError):
            parse_implied_exp("12-4")

    def test_format_parse_roundtrip(self):
        ep = datetime(2026, 10, 24, 6, 30, 0, tzinfo=timezone.utc)
        l1, l2 = format_tle(catalog=90001, intl_designator="26901A", epoch=ep, ndot=0.0, nddot=0.0, bstar=2.0e-5, element_set=999,
                            inclination_deg=74.0, raan_deg=40.0, eccentricity=0.0001, arg_perigee_deg=90.0,
                            mean_anomaly_deg=12.3456, mean_motion_rev_per_day=15.05535302, rev_number=1)
        self.assertEqual((len(l1), len(l2)), (69, 69))
        t, issues = parse_tle(l1, l2)
        self.assertIsNotNone(t, issues)
        # TLE epoch has 8 decimals of a day => resolution 8.64e-4 s; exact equality is not representable.
        self.assertLess(abs((t.epoch - ep).total_seconds()), 8.64e-4)
        self.assertAlmostEqual(t.mean_anomaly_deg, 12.3456)
        self.assertAlmostEqual(t.mean_motion_rev_per_day, 15.05535302)
        self.assertAlmostEqual(t.bstar, 2.0e-5, places=10)

    def test_demo_dataset_lines_are_valid(self):
        import json, os
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "data", "demo_synthetic.json"), encoding="utf-8") as fh:
            demo = json.load(fh)
        lines = demo["tle_text"].strip().splitlines()
        self.assertEqual(len(lines), 12)
        for i in range(0, 12, 3):
            t, issues = parse_tle(lines[i + 1], lines[i + 2], lines[i])
            self.assertIsNotNone(t, issues)


if __name__ == "__main__":
    unittest.main()
