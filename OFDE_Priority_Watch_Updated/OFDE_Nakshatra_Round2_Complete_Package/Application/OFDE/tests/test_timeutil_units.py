import math
import unittest
from datetime import datetime, timedelta, timezone

from ofde import units
from ofde.timeutil import (TimeParseError, parse_utc, format_utc, julian_date, tle_epoch_to_datetime, datetime_to_tle_epoch)


class TestTime(unittest.TestCase):
    def test_parse_z_and_offset(self):
        a = parse_utc("2026-10-24T00:00:00Z")
        b = parse_utc("2026-10-24T05:30:00+05:30")
        self.assertEqual(a, b)
        self.assertEqual(a.utcoffset(), timedelta(0))

    def test_naive_rejected(self):
        with self.assertRaises(TimeParseError):
            parse_utc("2026-10-24T00:00:00")

    def test_garbage_rejected(self):
        for bad in ("yesterday", "", "2026-13-40T00:00:00Z", None, 5):
            with self.assertRaises(TimeParseError):
                parse_utc(bad)

    def test_format_roundtrip(self):
        t = parse_utc("2026-10-24T01:02:03.456Z")
        self.assertEqual(format_utc(t), "2026-10-24T01:02:03.456Z")

    def test_julian_date_references(self):
        self.assertAlmostEqual(julian_date(parse_utc("2000-01-01T12:00:00Z")), 2451545.0, places=9)
        self.assertAlmostEqual(julian_date(parse_utc("1970-01-01T00:00:00Z")), 2440587.5, places=9)

    def test_tle_epoch_published_sample(self):
        t = tle_epoch_to_datetime(8, 264.51782528)
        self.assertEqual((t.year, t.month, t.day, t.hour, t.minute, t.second), (2008, 9, 20, 12, 25, 40))

    def test_tle_year_pivot(self):
        self.assertEqual(tle_epoch_to_datetime(56, 1.0).year, 2056)
        self.assertEqual(tle_epoch_to_datetime(57, 1.0).year, 1957)

    def test_tle_epoch_day_bounds(self):
        with self.assertRaises(ValueError):
            tle_epoch_to_datetime(25, 366.5)   # 2025 not a leap year
        self.assertEqual(tle_epoch_to_datetime(24, 366.0).month, 12)
        with self.assertRaises(ValueError):
            tle_epoch_to_datetime(25, 0.5)

    def test_epoch_roundtrip(self):
        t = parse_utc("2026-10-24T00:00:00Z")
        yy, day = datetime_to_tle_epoch(t)
        self.assertEqual((yy, day), (26, 297.0))
        self.assertEqual(tle_epoch_to_datetime(yy, day), t)


class TestUnits(unittest.TestCase):
    def test_length(self):
        self.assertEqual(units.km_to_m(1.5), 1500.0)
        self.assertAlmostEqual(units.m_to_km(2500.0), 2.5)

    def test_angles(self):
        self.assertAlmostEqual(units.deg_to_rad(180.0), math.pi)
        self.assertAlmostEqual(units.rad_to_deg(math.pi / 2), 90.0)

    def test_mean_motion(self):
        self.assertAlmostEqual(units.rev_per_day_to_rad_per_s(1.0), 2 * math.pi / 86400.0)
        self.assertAlmostEqual(units.rev_per_day_to_period_min(15.0), 96.0)
        with self.assertRaises(ValueError):
            units.rev_per_day_to_period_min(0.0)


if __name__ == "__main__":
    unittest.main()
