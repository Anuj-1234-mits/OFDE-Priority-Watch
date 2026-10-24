"""TCA search/refinement validated against closed-form geometry (test fixtures, not orbital physics)."""
import math
import unittest
from datetime import timedelta

from ofde.propagation import PropagationError
from ofde.tca import AnalysisInputError, analyse, golden_section_min, time_within_radius
from tests.fixtures import CirclePropagator, LinearPropagator, utc

T0 = utc(2026, 10, 24)


def linear_case(r0, v):
    """A static at origin; B moves linearly. Relative position at window start is r0, relative velocity v."""
    return LinearPropagator((0, 0, 0), (0, 0, 0), T0), LinearPropagator(r0, v, T0)


class TestGolden(unittest.TestCase):
    def test_quadratic(self):
        x, fx, it = golden_section_min(lambda x: (x - 2.0) ** 2 + 1.0, 0.0, 5.0, 1e-6)
        self.assertAlmostEqual(x, 2.0, places=5)
        self.assertAlmostEqual(fx, 1.0, places=9)

    def test_bad_bracket(self):
        with self.assertRaises(AnalysisInputError):
            golden_section_min(lambda x: x, 1.0, 1.0, 1e-3)


class TestLinearAnalytic(unittest.TestCase):
    def setUp(self):
        # relative: r(t) = (-700, 12, 5) + (7, 0, 0)*t  -> TCA t*=100 s, miss = sqrt(12^2+5^2) = 13 km
        self.a, self.b = linear_case((-700.0, 12.0, 5.0), (7.0, 0.0, 0.0))

    def test_tca_and_miss_match_closed_form(self):
        r = analyse(self.a, self.b, T0, 600.0, 30.0)
        self.assertTrue(r.bracketed)
        self.assertAlmostEqual(r.tca_offset_s, 100.0, delta=2e-3)
        self.assertAlmostEqual(r.miss_distance_km, 13.0, places=6)
        self.assertAlmostEqual(r.rel_speed_km_s, 7.0, places=9)
        self.assertEqual(r.tca, T0 + timedelta(seconds=r.tca_offset_s))
        self.assertEqual(r.frame, "TEME")

    def test_relative_vector_at_tca(self):
        r = analyse(self.a, self.b, T0, 600.0, 30.0)
        self.assertAlmostEqual(r.rel_position_km[0], 0.0, delta=2e-2)
        self.assertAlmostEqual(r.rel_position_km[1], 12.0, places=6)
        self.assertAlmostEqual(r.rel_position_km[2], 5.0, places=6)

    def test_grid_resolution_does_not_change_refined_answer(self):
        coarse = analyse(self.a, self.b, T0, 600.0, 90.0)
        fine = analyse(self.a, self.b, T0, 600.0, 5.0)
        self.assertAlmostEqual(coarse.tca_offset_s, fine.tca_offset_s, delta=5e-3)
        self.assertAlmostEqual(coarse.miss_distance_km, fine.miss_distance_km, places=5)
        self.assertGreaterEqual(coarse.grid_min_km, coarse.miss_distance_km)  # refinement never worse than grid

    def test_minimum_at_window_edge_is_flagged(self):
        r = analyse(self.a, self.b, T0, 60.0, 10.0)  # window ends before TCA at 100 s
        self.assertFalse(r.bracketed)
        self.assertTrue(any("edge" in n for n in r.notes))
        self.assertAlmostEqual(r.tca_offset_s, 60.0)

    def test_dwell_time_closed_form(self):
        r = analyse(self.a, self.b, T0, 600.0, 30.0)
        R = 20.0
        dw = time_within_radius(self.a, self.b, T0, r, R)
        expected = 2 * math.sqrt(R * R - 13.0 ** 2) / 7.0
        self.assertAlmostEqual(dw["duration_s"], expected, delta=2e-3)
        self.assertFalse(dw["censored_low"] or dw["censored_high"])

    def test_dwell_zero_when_never_inside(self):
        r = analyse(self.a, self.b, T0, 600.0, 30.0)
        self.assertEqual(time_within_radius(self.a, self.b, T0, r, 10.0)["duration_s"], 0.0)

    def test_dwell_censored_by_window(self):
        r = analyse(self.a, self.b, T0, 101.0, 1.0)   # window ends 1 s after TCA, still inside 20 km radius
        dw = time_within_radius(self.a, self.b, T0, r, 20.0)
        self.assertTrue(dw["censored_high"])

    def test_dwell_bad_radius(self):
        r = analyse(self.a, self.b, T0, 600.0, 30.0)
        with self.assertRaises(AnalysisInputError):
            time_within_radius(self.a, self.b, T0, r, 0.0)


class TestCircles(unittest.TestCase):
    R1, R2 = 7000.0, 7005.0

    def make(self, dphi0_deg, dw_deg_s):
        w1 = 2 * math.pi / 5700.0
        a = CirclePropagator(self.R1, w1, 0.0, T0)
        b = CirclePropagator(self.R2, w1 + math.radians(dw_deg_s), math.radians(dphi0_deg), T0)
        return a, b

    def test_alignment_time_and_distance_closed_form(self):
        # phase difference starts at -5 deg and closes at +1e-3 deg/s => alignment at 5000 s, min distance = R2-R1 = 5 km
        a, b = self.make(-5.0, 1e-3)
        r = analyse(a, b, T0, 14400.0, 30.0)
        self.assertTrue(r.bracketed)
        self.assertAlmostEqual(r.tca_offset_s, 5000.0, delta=5e-3)
        self.assertAlmostEqual(r.miss_distance_km, 5.0, places=6)

    def test_multiple_minima_reports_smallest_and_lists_all(self):
        # relative angular rate 0.2 deg/s => alignment every 1800 s; window covers several
        a, b = self.make(-10.0, 0.2)
        r = analyse(a, b, T0, 6000.0, 5.0)
        self.assertGreaterEqual(r.n_local_minima, 3)
        self.assertAlmostEqual(r.miss_distance_km, 5.0, places=5)
        self.assertEqual(len(r.candidates), r.n_local_minima)
        self.assertEqual(r.candidates[0]["distance_km"], min(c["distance_km"] for c in r.candidates))

    def test_identical_trajectories(self):
        a = CirclePropagator(7000.0, 0.001, 0.3, T0)
        b = CirclePropagator(7000.0, 0.001, 0.3, T0)
        r = analyse(a, b, T0, 600.0, 30.0)
        self.assertEqual(r.miss_distance_km, 0.0)
        self.assertTrue(any("constant" in n for n in r.notes))

    def test_constant_separation_with_roundoff_noise_is_not_a_minimum(self):
        # same radius and rate, different phase: true separation is constant; float noise must not create a "bracketed minimum"
        a = CirclePropagator(7000.0, 0.001, 0.0, T0)
        b = CirclePropagator(7000.0, 0.001, 0.4, T0)
        r = analyse(a, b, T0, 14400.0, 60.0)
        self.assertTrue(any("constant" in n for n in r.notes))
        self.assertEqual(r.tca_offset_s, 0.0)

    def test_series_is_consistent_with_grid(self):
        a, b = self.make(-5.0, 1e-3)
        r = analyse(a, b, T0, 14400.0, 30.0, series_max_points=100)
        ts, ss = r.series["t_offset_s"], r.series["separation_km"]
        self.assertLessEqual(len(ts), 140)
        self.assertEqual(len(ts), len(ss))
        for t, s in zip(ts[:5], ss[:5]):
            ra, _ = a.state_at(T0 + timedelta(seconds=t))
            rb, _ = b.state_at(T0 + timedelta(seconds=t))
            self.assertAlmostEqual(s, math.dist(ra, rb), places=9)
        self.assertEqual(ts[-1], 14400.0)


class TestInvalid(unittest.TestCase):
    def setUp(self):
        self.a, self.b = linear_case((-700.0, 12.0, 5.0), (7.0, 0.0, 0.0))

    def test_bad_windows(self):
        cases = [(0.0, 30.0), (-5.0, 30.0), (600.0, 0.0), (600.0, -1.0), (10.0, 30.0), (float("nan"), 30.0),
                 (600.0, float("inf")), (1e9, 0.01)]
        for dur, step in cases:
            with self.assertRaises(AnalysisInputError, msg=(dur, step)):
                analyse(self.a, self.b, T0, dur, step)

    def test_bad_tolerance(self):
        with self.assertRaises(AnalysisInputError):
            analyse(self.a, self.b, T0, 600.0, 30.0, tol_s=0.0)

    def test_non_numeric_rejected(self):
        with self.assertRaises(AnalysisInputError):
            analyse(self.a, self.b, T0, "600", 30.0)
        with self.assertRaises(AnalysisInputError):
            analyse(self.a, self.b, T0, True, 30.0)

    def test_frame_mismatch_refused(self):
        self.b.frame = "ECEF"
        with self.assertRaises(AnalysisInputError):
            analyse(self.a, self.b, T0, 600.0, 30.0)

    def test_propagation_failure_is_explicit_with_offset(self):
        bad = LinearPropagator((-700.0, 12.0, 5.0), (7.0, 0, 0), T0, fail_after_s=200.0)
        with self.assertRaises(PropagationError) as cm:
            analyse(self.a, bad, T0, 600.0, 30.0)
        self.assertIn("window offset", cm.exception.message)
        self.assertEqual(cm.exception.code, "SGP4_ERROR")


if __name__ == "__main__":
    unittest.main()
