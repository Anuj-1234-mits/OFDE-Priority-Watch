"""Tests that REQUIRE the real sgp4 package. They are skipped (not passed) when it is not installed.
Run on your machine after `pip install -r requirements.txt`. See TEST_REPORT.md."""
import math
import os
import tempfile
import unittest
from datetime import timedelta

from ofde import reference_cases as ref
from ofde.propagation import PropagationError, Sgp4Propagator, sgp4_status
from ofde.tca import analyse
from ofde.tle import parse_tle

AVAILABLE = sgp4_status()["available"]


@unittest.skipUnless(AVAILABLE, "sgp4 package not installed in this environment")
class TestSgp4Reference(unittest.TestCase):
    def test_reference_case_00005_raw_library(self):
        from sgp4.api import Satrec, WGS72
        sat = Satrec.twoline2rv(ref.CASE_00005_LINE1, ref.CASE_00005_LINE2, WGS72)
        for tsince, r_ref, v_ref in ref.CASE_00005_STATES:
            e, r, v = sat.sgp4(sat.jdsatepoch, sat.jdsatepochF + tsince / 1440.0)
            self.assertEqual(e, 0)
            self.assertLessEqual(math.dist(r, r_ref), ref.POSITION_TOL_KM)
            self.assertLessEqual(math.dist(v, v_ref), ref.VELOCITY_TOL_KM_S)

    def test_reference_case_via_ofde_wrapper(self):
        tle, _ = parse_tle(ref.CASE_00005_LINE1, ref.CASE_00005_LINE2)
        p = Sgp4Propagator(tle)
        for tsince, r_ref, _v in ref.CASE_00005_STATES:
            r, v = p.state_at(tle.epoch + timedelta(minutes=tsince))
            self.assertLessEqual(math.dist(r, r_ref), 1e-3)   # allows microsecond epoch rounding

    def test_iss_self_consistency(self):
        tle, _ = parse_tle(ref.ISS_LINE1, ref.ISS_LINE2)
        p = Sgp4Propagator(tle)
        t0 = tle.epoch + timedelta(minutes=30)
        r, v = p.state_at(t0)
        self.assertTrue(6600 < math.hypot(*r) < 6900)
        self.assertTrue(7.5 < math.hypot(*v) < 7.8)
        rp, _ = p.state_at(t0 + timedelta(seconds=0.5))
        rm, _ = p.state_at(t0 - timedelta(seconds=0.5))
        vfd = [(a - b) / 1.0 for a, b in zip(rp, rm)]
        self.assertLess(math.dist(v, vfd), 1e-4)

    def test_decayed_or_invalid_orbit_raises_explicit_error(self):
        tle, _ = parse_tle(ref.ISS_LINE1, ref.ISS_LINE2)
        p = Sgp4Propagator(tle)
        # ISS at ~2008 propagated ~60 years ahead: drag model eventually fails or diverges; either way must not return silently-bad data
        try:
            r, v = p.state_at(tle.epoch + timedelta(days=365 * 60))
            self.assertTrue(all(math.isfinite(x) for x in (*r, *v)))
        except PropagationError as e:
            self.assertIn(e.code, ("SGP4_ERROR", "NON_FINITE_STATE"))

    def test_demo_pair_end_to_end_is_deterministic_and_sane(self):
        import json
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "data", "demo_synthetic.json"), encoding="utf-8") as fh:
            lines = json.load(fh)["tle_text"].splitlines()
        ta, _ = parse_tle(lines[1], lines[2], lines[0])
        tb, _ = parse_tle(lines[4], lines[5], lines[3])
        r1 = analyse(Sgp4Propagator(ta), Sgp4Propagator(tb), ta.epoch, 14400.0, 30.0)
        r2 = analyse(Sgp4Propagator(ta), Sgp4Propagator(tb), ta.epoch, 14400.0, 30.0)
        self.assertEqual(r1.to_dict(), r2.to_dict())
        self.assertTrue(math.isfinite(r1.miss_distance_km) and r1.miss_distance_km >= 0)
        self.assertLessEqual(r1.miss_distance_km, r1.grid_min_km + 1e-9)
        # both objects are ~550 km LEO: separation can never exceed twice the orbital radius
        self.assertLess(r1.grid_min_km, 2 * 7000)
        self.assertEqual(r1.frame, "TEME")

    def test_full_service_run_with_real_sgp4(self):
        from ofde.service import OfdeService, ROUTES
        import json
        route = {r.handler: r for r in ROUTES}
        with tempfile.TemporaryDirectory() as tmp:
            svc = OfdeService(os.path.join(tmp, "s.sqlite3"))
            st, _, data, _ = svc.handle(route["load_demo"], {}, {}, b"{}")
            ds = json.loads(data)
            body = {"dataset_id": ds["id"], "object_a": "90001", "object_b": "90002",
                    "scenarios": [{"name": "B +0.05 deg", "perturbations": {"b": {"d_mean_anomaly_deg": 0.05}}}]}
            st, _, data, _ = svc.handle(route["run_analysis"], {}, {}, json.dumps(body).encode())
            self.assertEqual(st, 200, data)
            rec = json.loads(data)
            self.assertEqual(rec["scenarios"][0]["propagator"]["category"], "computed")
            self.assertTrue(rec["scenarios"][0]["propagator"]["name"].startswith("SGP4"))
            svc.store.close()


class TestUnavailableMessage(unittest.TestCase):
    @unittest.skipIf(AVAILABLE, "sgp4 installed")
    def test_clear_error_when_missing(self):
        from ofde.propagation import PropagationUnavailable
        tle, _ = parse_tle(ref.ISS_LINE1, ref.ISS_LINE2)
        with self.assertRaises(PropagationUnavailable) as cm:
            Sgp4Propagator(tle)
        self.assertIn("pip install", cm.exception.message)


if __name__ == "__main__":
    unittest.main()
