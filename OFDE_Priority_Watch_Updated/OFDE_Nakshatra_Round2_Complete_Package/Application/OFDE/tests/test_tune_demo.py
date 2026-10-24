import importlib.util
import math
import os
import unittest

from tests.fixtures import circle_from_tle
from tests.test_scenarios import make_tle, EP

spec = importlib.util.spec_from_file_location("tune_demo", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "tune_demo_sgp4.py"))
tune_demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tune_demo)


class TestTune(unittest.TestCase):
    def test_finds_bracketed_in_window_pass_matching_closed_form(self):
        a, b = make_tle(90001, 15.0, 0.0), make_tle(90002, 15.2, 340.0)   # starts 20 deg behind; a shift within +-30 deg can align it
        res = tune_demo.tune(circle_from_tle, a, b, EP, 14400.0, 60.0, span_deg=30.0, coarse_deg=1.0, fine_deg=0.05)
        # fixture: miss is |r_b - r_a| whenever phases align inside the window; search must land on it
        expected = abs(circle_from_tle(b).r - circle_from_tle(a).r)
        self.assertIsNotNone(res)
        self.assertAlmostEqual(res["miss_km"], expected, places=3)
        self.assertTrue(0.1 * 14400 <= res["tca_offset_s"] <= 0.9 * 14400)

    def test_returns_none_when_no_pass_possible(self):
        a, b = make_tle(90001, 15.0, 0.0), make_tle(90002, 15.0, 0.0)   # identical rates: relative phase constant, no minimum
        b2, _ = make_tle(90002, 15.0, 10.0), None
        res = tune_demo.tune(circle_from_tle, a, b2, EP, 14400.0, 60.0, span_deg=5.0, coarse_deg=1.0, fine_deg=0.1)
        self.assertIsNone(res)


if __name__ == "__main__":
    unittest.main()
