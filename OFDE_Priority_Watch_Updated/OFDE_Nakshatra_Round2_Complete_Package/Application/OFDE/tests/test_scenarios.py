import math
import unittest
from datetime import datetime, timezone

from ofde.scenarios import ScenarioError, apply_perturbations, run_scenario, validate_perturbations
from ofde.tle import checksum, format_tle, parse_tle
from tests.fixtures import circle_from_tle, utc

EP = datetime(2026, 10, 24, tzinfo=timezone.utc)


def make_tle(cat, n, m, inc=74.0, raan=40.0, argp=0.0, bstar=2.0e-5):
    l1, l2 = format_tle(catalog=cat, intl_designator="26999A", epoch=EP, ndot=0.0, nddot=0.0, bstar=bstar, element_set=1,
                        inclination_deg=inc, raan_deg=raan, eccentricity=0.0001, arg_perigee_deg=argp,
                        mean_anomaly_deg=m, mean_motion_rev_per_day=n, rev_number=1)
    t, issues = parse_tle(l1, l2, f"OBJ{cat}")
    assert t is not None, issues
    return t


class TestValidatePerturbations(unittest.TestCase):
    def test_empty_ok(self):
        self.assertEqual(validate_perturbations(None), {"a": {}, "b": {}})

    def test_rejections(self):
        bad = [{"c": {"d_raan_deg": 1}}, {"a": {"warp_factor": 1}}, {"a": {"d_raan_deg": 99}}, {"a": {"d_raan_deg": float("nan")}},
               {"a": {"d_raan_deg": True}}, {"a": {"d_raan_deg": "1"}}, {"a": 5}, {"b": {"bstar_scale": -1}}]
        for b in bad:
            with self.assertRaises(ScenarioError, msg=b):
                validate_perturbations(b)


class TestApply(unittest.TestCase):
    def setUp(self):
        self.t = make_tle(90001, 15.0, 10.0)

    def test_noop_returns_same_object(self):
        t2, ch = apply_perturbations(self.t, {})
        self.assertIs(t2, self.t)
        self.assertEqual(ch, [])

    def test_mean_anomaly_shift_recorded_and_checksummed(self):
        t2, ch = apply_perturbations(self.t, {"d_mean_anomaly_deg": 2.5})
        self.assertAlmostEqual(t2.mean_anomaly_deg, 12.5)
        self.assertEqual(ch, [{"field": "mean_anomaly_deg", "original": 10.0, "new": 12.5, "unit": "deg"}])
        self.assertEqual(int(t2.line2[68]), checksum(t2.line2))
        self.assertEqual(len(t2.line2), 69)
        # untouched fields identical
        self.assertEqual(t2.inclination_deg, self.t.inclination_deg)
        self.assertEqual(t2.line1, self.t.line1)
        self.assertEqual(self.t.mean_anomaly_deg, 10.0)    # original not mutated

    def test_wraparound(self):
        t2, _ = apply_perturbations(self.t, {"d_mean_anomaly_deg": -15.0})
        self.assertAlmostEqual(t2.mean_anomaly_deg, 355.0)

    def test_all_fields(self):
        t2, ch = apply_perturbations(self.t, {"d_inclination_deg": 0.5, "d_raan_deg": -1.0,
                                              "d_mean_motion_rev_per_day": 0.001, "bstar_scale": 2.0})
        self.assertAlmostEqual(t2.inclination_deg, 74.5)
        self.assertAlmostEqual(t2.raan_deg, 39.0)
        self.assertAlmostEqual(t2.mean_motion_rev_per_day, 15.001, places=8)
        self.assertAlmostEqual(t2.bstar, 4.0e-5, places=9)
        self.assertEqual(len(ch), 4)
        self.assertEqual(int(t2.line1[68]), checksum(t2.line1))

    def test_invalid_results_rejected(self):
        hi = make_tle(90002, 15.0, 10.0, inc=179.0)
        with self.assertRaises(ScenarioError):
            apply_perturbations(hi, {"d_inclination_deg": 3.0})
        with self.assertRaises(ScenarioError):
            apply_perturbations(make_tle(90003, 0.01, 10.0), {"d_mean_motion_rev_per_day": -0.02})

    def test_zero_bstar_stays_zero(self):
        t = make_tle(90004, 15.0, 10.0, bstar=0.0)
        t2, _ = apply_perturbations(t, {"bstar_scale": 5.0})
        self.assertEqual(t2.bstar, 0.0)


class TestRunScenario(unittest.TestCase):
    def setUp(self):
        # circular fixture: phase diff -5 deg closing at (0.2 rev/day) => alignment at t = 5/(0.2*360/86400) = 6000 s
        self.a = make_tle(90001, 15.0, 0.0)
        self.b = make_tle(90002, 15.2, 355.0)

    def go(self, perts=None, dwell=None):
        return run_scenario(lambda t: circle_from_tle(t), self.a, self.b, EP, 14400.0, 30.0, 1e-3, perts, dwell)

    def test_baseline_analytic(self):
        out = self.go(dwell=10.0)
        r = out["result"]
        self.assertAlmostEqual(r["tca_offset_s"], 6000.0, delta=5e-3)
        ra = circle_from_tle(self.a).r
        rb = circle_from_tle(self.b).r
        self.assertAlmostEqual(r["miss_distance_km"], abs(rb - ra), places=5)
        self.assertEqual(out["propagator"]["category"], "test-fixture")
        self.assertIsNotNone(out["dwell"])

    def test_deterministic(self):
        self.assertEqual(self.go({"b": {"d_mean_anomaly_deg": 1.0}}), self.go({"b": {"d_mean_anomaly_deg": 1.0}}))

    def test_phase_shift_moves_tca_as_closed_form(self):
        base = self.go()["result"]["tca_offset_s"]
        shifted = self.go({"b": {"d_mean_anomaly_deg": 1.0}})["result"]["tca_offset_s"]
        # relative angular rate = 0.2 rev/day*360/86400 deg/s ; +1 deg phase => alignment earlier by 1/rate seconds
        rate = 0.2 * 360.0 / 86400.0
        self.assertAlmostEqual(shifted - base, -1.0 / rate, delta=0.05)

    def test_changes_are_recorded_in_output(self):
        out = self.go({"a": {"d_raan_deg": 1.0}})
        self.assertEqual(out["changes"]["a"][0]["field"], "raan_deg")
        self.assertEqual(out["changes"]["b"], [])
        self.assertNotEqual(out["tle_a"]["line2"], self.a.line2)
        self.assertEqual(out["tle_b"]["line2"], self.b.line2)

    def test_invalid_perturbation_propagates(self):
        with self.assertRaises(ScenarioError):
            self.go({"a": {"d_raan_deg": 50.0}})


if __name__ == "__main__":
    unittest.main()
