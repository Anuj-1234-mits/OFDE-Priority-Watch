import math
import unittest

from ofde.metrics import (MetricError, fei_ranking, fei_value, sensitivity_table, threat_transfer, validate_fei_params,
                          DEFAULT_FEI_PARAMS)


class TestThreatTransfer(unittest.TestCase):
    def test_worked_example(self):
        # baseline 10 km, alternative 6 km => alternative closer by 4 km (40 %)
        tt = threat_transfer({"miss_distance_km": 10.0, "tca_offset_s": 100.0, "rel_speed_km_s": 7.0},
                             {"miss_distance_km": 6.0, "tca_offset_s": 112.5, "rel_speed_km_s": 7.25})
        self.assertAlmostEqual(tt["tt_km"], 4.0)
        self.assertAlmostEqual(tt["tt_rel"], 0.4)
        self.assertAlmostEqual(tt["delta_tca_s"], 12.5)
        self.assertAlmostEqual(tt["delta_rel_speed_km_s"], 0.25)

    def test_negative_when_alternative_farther(self):
        tt = threat_transfer({"miss_distance_km": 5.0}, {"miss_distance_km": 8.0})
        self.assertAlmostEqual(tt["tt_km"], -3.0)
        self.assertIsNone(tt["delta_tca_s"])

    def test_zero_baseline_relative_undefined_not_inf(self):
        tt = threat_transfer({"miss_distance_km": 0.0}, {"miss_distance_km": 2.0})
        self.assertAlmostEqual(tt["tt_km"], -2.0)
        self.assertIsNone(tt["tt_rel"])
        self.assertTrue(tt["notes"])

    def test_missing_data_is_none_not_zero(self):
        tt = threat_transfer({"miss_distance_km": None}, {"miss_distance_km": 3.0})
        self.assertIsNone(tt["tt_km"])
        self.assertIsNone(tt["tt_rel"])

    def test_identical_scenarios(self):
        tt = threat_transfer({"miss_distance_km": 4.0, "tca_offset_s": 1.0}, {"miss_distance_km": 4.0, "tca_offset_s": 1.0})
        self.assertEqual((tt["tt_km"], tt["tt_rel"], tt["delta_tca_s"]), (0.0, 0.0, 0.0))


class TestFEI(unittest.TestCase):
    P = validate_fei_params({"d_ref_km": 5.0, "radius_km": 10.0, "t_ref_s": 3.0, "w_d": 0.7, "w_t": 0.3})

    def test_worked_example(self):
        # d = d_ref => c_d = 0.5 ; dwell = t_ref/2 => c_t = 0.5 ; FEI = 100*(0.7*0.5+0.3*0.5) = 50
        v = fei_value(5.0, 1.5, self.P)
        self.assertAlmostEqual(v["closeness"], 0.5)
        self.assertAlmostEqual(v["dwell_term"], 0.5)
        self.assertAlmostEqual(v["fei"], 50.0)

    def test_bounds(self):
        self.assertAlmostEqual(fei_value(0.0, 99.0, self.P)["fei"], 100.0)
        far = fei_value(1e6, 0.0, self.P)["fei"]
        self.assertTrue(0.0 <= far < 0.01)

    def test_monotonic_in_distance_and_dwell(self):
        vals = [fei_value(d, 1.0, self.P)["fei"] for d in (0.5, 1, 2, 5, 10, 50)]
        self.assertEqual(vals, sorted(vals, reverse=True))
        self.assertLess(fei_value(5.0, 0.5, self.P)["fei"], fei_value(5.0, 2.0, self.P)["fei"])

    def test_ranking_order_ties_and_unranked(self):
        out = fei_ranking([
            {"id": "far", "name": "Far", "miss_distance_km": 30.0, "dwell_s": 0.0},
            {"id": "near", "name": "Near", "miss_distance_km": 2.0, "dwell_s": 1.0},
            {"id": "tie1", "name": "T1", "miss_distance_km": 8.0, "dwell_s": 0.0},
            {"id": "tie2", "name": "T2", "miss_distance_km": 8.0, "dwell_s": 0.0},
            {"id": "missing", "name": "Missing", "miss_distance_km": None, "dwell_s": None},
        ])
        self.assertEqual([r["id"] for r in out["ranking"]], ["near", "tie1", "tie2", "far"])
        self.assertEqual([r["rank"] for r in out["ranking"]], [1, 2, 3, 4])
        self.assertEqual(out["unranked"][0]["id"], "missing")   # excluded, never zero-filled
        self.assertIn("not a collision probability", out["disclaimer"])

    def test_weights_change_result_transparently(self):
        a = fei_value(2.0, 0.0, validate_fei_params({"w_d": 1.0, "w_t": 0.0}))["fei"]
        b = fei_value(2.0, 0.0, validate_fei_params({"w_d": 0.0, "w_t": 1.0}))["fei"]
        self.assertAlmostEqual(a, 100 * 5 / 7)
        self.assertAlmostEqual(b, 0.0)

    def test_param_validation(self):
        for bad in ({"d_ref_km": 0}, {"radius_km": -1}, {"t_ref_s": float("nan")}, {"w_d": -1}, {"w_d": 0, "w_t": 0}, {"w_t": "x"}):
            with self.assertRaises(MetricError, msg=bad):
                validate_fei_params(bad)

    def test_defaults_documented(self):
        self.assertEqual(validate_fei_params(None), DEFAULT_FEI_PARAMS)


class TestSensitivity(unittest.TestCase):
    def test_linear_response(self):
        pts = [{"p": p, "y": 2.0 * p + 1.0} for p in (-2.0, -1.0, 0.0, 1.0, 2.0)]
        t = sensitivity_table("x", "u", 0.0, pts, "y", "km")
        for r in t["rows"]:
            if r["p"] != 0.0:
                self.assertAlmostEqual(r["slope"], 2.0)
        self.assertIsNone([r for r in t["rows"] if r["p"] == 0.0][0]["slope"])
        self.assertAlmostEqual(t["least_squares_slope"], 2.0)
        self.assertAlmostEqual(t["output_range"], 8.0)
        self.assertIn("not a validated uncertainty", t["kind"])

    def test_missing_points_and_missing_baseline(self):
        pts = [{"p": -1.0, "y": 3.0}, {"p": 1.0, "y": None}, {"p": 2.0, "y": 5.0}]
        t = sensitivity_table("x", "u", 0.0, pts, "y", "km")
        self.assertTrue(all(r["slope"] is None for r in t["rows"]))   # no baseline point => no baseline-relative slope
        self.assertEqual(t["n_valid"], 2)
        self.assertEqual(t["n_total"], 3)

    def test_degenerate(self):
        t = sensitivity_table("x", "u", 0.0, [{"p": 0.0, "y": 1.0}], "y", "km")
        self.assertIsNone(t["least_squares_slope"])
        with self.assertRaises(MetricError):
            sensitivity_table("x", "u", float("nan"), [], "y", "km")


if __name__ == "__main__":
    unittest.main()
