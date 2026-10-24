"""End-to-end workflow through OfdeService using the analytic TEST fixture propagator.
These tests verify orchestration, data flow, metrics wiring, persistence and reporting; they do NOT
validate SGP4 (see test_sgp4_required.py for that)."""
import json
import math
import os
import tempfile
import unittest

from ofde.propagation import default_propagator_factory, sgp4_status
from ofde.report import f, report_html, scenarios_csv, sensitivity_csv
from ofde.service import OfdeService, ROUTES, ServiceError
from tests.fixtures import circle_from_tle, fixture_status
from tests.test_scenarios import make_tle, EP

ROUTE = {r.handler: r for r in ROUTES}


def call(svc, handler, params=None, query=None, body=None):
    raw = json.dumps(body).encode() if body is not None else None
    status, ctype, data, headers = svc.handle(ROUTE[handler], params or {}, query or {}, raw)
    if ctype.startswith("application/json"):
        return status, json.loads(data)
    return status, data.decode()


def make_service(tmp):
    return OfdeService(os.path.join(tmp, "t.sqlite3"), propagator_factory=circle_from_tle, status_fn=fixture_status)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.svc = make_service(self._tmp.name)
        a, b = make_tle(90001, 15.0, 0.0), make_tle(90002, 15.2, 355.0)
        text = f"{a.name}\n{a.line1}\n{a.line2}\n{b.name}\n{b.line1}\n{b.line2}\n"
        st, ds = call(self.svc, "import_dataset", body={"text": text, "filename": "t.tle", "origin": "manual",
                                                        "source_description": "unit-test fixture TLEs", "name": "fixture"})
        assert st == 200, ds
        self.ds = ds
        self.ra, self.rb = circle_from_tle(a).r, circle_from_tle(b).r

    def tearDown(self):
        self.svc.store.close()
        self._tmp.cleanup()

    def analyse(self, **extra):
        body = {"dataset_id": self.ds["id"], "object_a": "90001", "object_b": "90002", "duration_s": 14400, "step_s": 30}
        body.update(extra)
        return call(self.svc, "run_analysis", body=body)


class TestWorkflow(Base):
    def test_baseline_matches_closed_form(self):
        st, rec = self.analyse()
        self.assertEqual(st, 200, rec)
        base = rec["scenarios"][0]["result"]
        self.assertAlmostEqual(base["tca_offset_s"], 6000.0, delta=5e-3)
        self.assertAlmostEqual(base["miss_distance_km"], abs(self.rb - self.ra), places=5)
        self.assertEqual(rec["status"], "computed")
        self.assertEqual(len(rec["scenarios"]), 1)

    def test_scenarios_comparison_fei_and_diff_of_inputs(self):
        st, rec = self.analyse(scenarios=[{"name": "B earlier", "perturbations": {"b": {"d_mean_anomaly_deg": 1.0}}},
                                          {"name": "B drag x3", "perturbations": {"b": {"bstar_scale": 3.0}}}],
                               fei={"d_ref_km": 5.0, "radius_km": 20.0})
        self.assertEqual(st, 200, rec)
        self.assertEqual([s["name"] for s in rec["scenarios"]], ["Baseline", "B earlier", "B drag x3"])
        c1, c2 = rec["comparison"]
        self.assertEqual([c["field"] for c in c1["inputs_changed"]], ["mean_anomaly_deg"])
        self.assertEqual(c1["inputs_changed"][0]["object"], "b")
        rate = 0.2 * 360.0 / 86400.0
        self.assertAlmostEqual(c1["threat_transfer"]["delta_tca_s"], -1.0 / rate, delta=0.05)
        self.assertAlmostEqual(c1["threat_transfer"]["tt_km"], 0.0, places=4)   # circular fixture: miss unchanged by phase
        self.assertAlmostEqual(c2["threat_transfer"]["tt_km"], 0.0, places=9)   # fixture ignores B*
        self.assertEqual(len(rec["fei"]["ranking"]), 3)
        self.assertEqual(rec["fei"]["unranked"], [])
        for s in rec["scenarios"]:
            self.assertIsNotNone(s["dwell"])
            self.assertEqual(s["dwell"]["radius_km"], 20.0)

    def test_sensitivity_sweep_adds_baseline_and_matches_closed_form(self):
        st, rec = self.analyse(sensitivity=[{"target": "b", "parameter": "d_mean_anomaly_deg", "values": [-1.0, 1.0, 2.0]}])
        self.assertEqual(st, 200, rec)
        sx = rec["sensitivity"][0]
        ps = [r["p"] for r in sx["miss_table"]["rows"]]
        self.assertEqual(ps, [-1.0, 0.0, 1.0, 2.0])          # baseline point auto-added, shown to the user
        rate = 0.2 * 360.0 / 86400.0
        for row in sx["tca_table"]["rows"]:
            if row["p"] != 0.0:
                self.assertAlmostEqual(row["slope"], -1.0 / rate, delta=0.05)   # s per degree
        self.assertAlmostEqual(sx["miss_table"]["output_range"], 0.0, places=4)
        self.assertIn("not a validated uncertainty", sx["miss_table"]["kind"])

    def test_sweep_min_max_n_form_and_limits(self):
        st, rec = self.analyse(sensitivity=[{"target": "a", "parameter": "d_mean_anomaly_deg", "min": -2, "max": 2, "n": 5}])
        self.assertEqual(st, 200, rec)
        self.assertEqual(len(rec["sensitivity"][0]["miss_table"]["rows"]), 5)
        st, err = self.analyse(sensitivity=[{"target": "a", "parameter": "d_mean_anomaly_deg", "min": -500, "max": 2, "n": 5}])
        self.assertEqual(st, 400)

    def test_reproducible_hashes(self):
        _, r1 = self.analyse(scenarios=[{"name": "x", "perturbations": {"b": {"d_mean_anomaly_deg": 0.5}}}])
        _, r2 = self.analyse(scenarios=[{"name": "x", "perturbations": {"b": {"d_mean_anomaly_deg": 0.5}}}])
        self.assertEqual(r1["reproducibility"]["request_sha256"], r2["reproducibility"]["request_sha256"])
        self.assertEqual(r1["reproducibility"]["result_sha256"], r2["reproducibility"]["result_sha256"])
        self.assertNotEqual(r1["id"], r2["id"])
        _, r3 = self.analyse(scenarios=[{"name": "x", "perturbations": {"b": {"d_mean_anomaly_deg": 0.6}}}])
        self.assertNotEqual(r1["reproducibility"]["result_sha256"], r3["reproducibility"]["result_sha256"])

    def test_window_edge_warning_surfaces(self):
        st, rec = self.analyse(duration_s=3000)   # alignment at 6000 s is outside
        self.assertEqual(st, 200)
        self.assertFalse(rec["scenarios"][0]["result"]["bracketed"])
        self.assertTrue(any("edge of the analysis window" in w for w in rec["warnings"]))

    def test_unverified_propagation_is_flagged(self):
        _, rec = self.analyse()
        self.assertTrue(any("not been verified" in w for w in rec["warnings"]))
        self.assertFalse(rec["software"]["sgp4_verification"]["verified"])

    def test_stale_tle_warning(self):
        st, rec = self.analyse(start_utc="2026-11-20T00:00:00Z", duration_s=600)
        self.assertEqual(st, 200)
        self.assertTrue(any("days from the window start" in w for w in rec["warnings"]))


class TestErrors(Base):
    def test_same_and_unknown_object(self):
        self.assertEqual(self.analyse(object_b="90001")[0], 400)
        st, e = self.analyse(object_b="12345")
        self.assertEqual((st, e["error"]["code"]), (400, "UNKNOWN_OBJECT"))

    def test_bad_inputs_store_nothing(self):
        bad = [dict(duration_s=0), dict(step_s=0), dict(duration_s=10, step_s=30), dict(start_utc="tomorrow"),
               dict(duration_s="long"), dict(scenarios="x"), dict(scenarios=[{"perturbations": {"a": {"nope": 1}}}]),
               dict(fei={"d_ref_km": -1}), dict(dataset_id=999), dict(sensitivity="x"), dict(tol_s=0)]
        for extra in bad:
            st, e = self.analyse(**extra)
            self.assertIn(st, (400, 404), (extra, st, e))
            self.assertIn("error", e)
        self.assertEqual(call(self.svc, "list_analyses")[1]["analyses"], [])

    def test_missing_dataset_id(self):
        st, e = call(self.svc, "run_analysis", body={"object_a": "1", "object_b": "2"})
        self.assertEqual(st, 400)

    def test_invalid_json_and_non_object(self):
        for raw in (b"{not json", b"[1,2]"):
            st, ctype, data, _ = self.svc.handle(ROUTE["run_analysis"], {}, {}, raw)
            self.assertEqual(st, 400)
            self.assertIn("INVALID_JSON", data.decode())

    def test_not_found(self):
        self.assertEqual(call(self.svc, "get_analysis", {"analysis_id": "77"})[0], 404)
        self.assertEqual(call(self.svc, "get_analysis", {"analysis_id": "abc"})[0], 400)
        self.assertEqual(call(self.svc, "get_dataset", {"dataset_id": "99"})[0], 404)
        self.assertEqual(call(self.svc, "report_html", {"analysis_id": "77"})[0], 404)

    def test_import_failures(self):
        st, e = call(self.svc, "import_dataset", body={"text": "garbage only", "origin": "manual", "source_description": "x"})
        self.assertEqual(st, 422)
        st, e = call(self.svc, "import_dataset", body={"text": "", "origin": "manual", "source_description": "x"})
        self.assertEqual(st, 400)
        st, e = call(self.svc, "import_dataset", body={"origin": "manual", "source_description": "x"})
        self.assertEqual(st, 400)
        st, e = call(self.svc, "import_dataset", body={"text": "x", "origin": "manual"})
        self.assertEqual(st, 400)   # source description required
        self.assertEqual(len(call(self.svc, "list_datasets")[1]["datasets"]), 1)   # only the fixture dataset

    def test_propagation_failure_returns_422_and_stores_nothing(self):
        from ofde.propagation import PropagationError

        def boom(tle):
            raise PropagationError("SGP4_ERROR", "synthetic failure")
        self.svc.factory = boom
        st, e = self.analyse()
        self.assertEqual((st, e["error"]["code"]), (422, "SGP4_ERROR"))
        self.assertEqual(call(self.svc, "list_analyses")[1]["analyses"], [])


class TestDashboardAndReports(Base):
    def test_dashboard_stats_derive_from_state(self):
        st, d = call(self.svc, "dashboard", query={"dataset_id": str(self.ds["id"])})
        self.assertEqual((d["total_analyses"], d["total_scenarios"], d["cases_in_dataset"]), (0, 0, 0))
        self.assertIsNone(d["closest_approach"])
        self.assertFalse(d["demo_mode"])
        self.analyse(scenarios=[{"name": "s1", "perturbations": {"b": {"d_mean_anomaly_deg": 1.0}}}])
        self.analyse()
        st, d = call(self.svc, "dashboard", query={"dataset_id": str(self.ds["id"])})
        self.assertEqual((d["total_analyses"], d["total_scenarios"]), (2, 3))
        self.assertAlmostEqual(d["closest_approach"]["miss_distance_km"], abs(self.rb - self.ra), places=5)
        self.assertEqual(len(d["recent"]), 2)
        self.assertEqual(d["data_quality"]["origin"], "manual")
        self.assertEqual(d["data_quality"]["object_types_unknown"], 2)   # unknown stays unknown

    def test_dashboard_without_datasets(self):
        self.svc.store.reset()
        st, d = call(self.svc, "dashboard")
        self.assertEqual(st, 200)
        self.assertIsNone(d["active_dataset"])
        self.assertEqual(d["total_analyses"], 0)

    def test_demo_load_flag_and_reset(self):
        st, demo = call(self.svc, "load_demo")
        self.assertEqual(st, 200, demo)
        self.assertEqual(demo["origin"], "synthetic")
        st, d = call(self.svc, "dashboard", query={"dataset_id": str(demo["id"])})
        self.assertTrue(d["demo_mode"])
        self.assertEqual(d["cases_in_dataset"], 3)
        self.analyse()
        st, r = call(self.svc, "reset", body={})
        self.assertEqual(st, 200)
        self.assertEqual(call(self.svc, "list_analyses")[1]["analyses"], [])
        ds = call(self.svc, "list_datasets")[1]["datasets"]
        self.assertEqual([x["origin"] for x in ds], ["synthetic"])   # only freshly loaded demo remains

    def test_report_matches_displayed_results(self):
        _, rec = self.analyse(scenarios=[{"name": "B earlier", "perturbations": {"b": {"d_mean_anomaly_deg": 1.0}}}],
                              sensitivity=[{"target": "b", "parameter": "d_mean_anomaly_deg", "values": [-1.0, 1.0]}])
        st, html = call(self.svc, "report_html", {"analysis_id": str(rec["id"])})
        self.assertEqual(st, 200)
        st, csv_text = call(self.svc, "report_csv", {"analysis_id": str(rec["id"])})
        st, sens_csv = call(self.svc, "sensitivity_csv", {"analysis_id": str(rec["id"])})
        for s in rec["scenarios"]:
            self.assertIn(f(s["result"]["miss_distance_km"], 3, "km"), html)
            self.assertIn(s["result"]["tca_utc"], html)
            self.assertIn(repr(s["result"]["miss_distance_km"]), csv_text)
            self.assertIn(s["name"], html)
        self.assertIn(rec["reproducibility"]["result_sha256"], html)
        self.assertIn("sensitivity experiments", html)
        self.assertIn("not validated uncertainty", sens_csv)
        self.assertEqual(sum(1 for line in sens_csv.splitlines() if line.startswith("b,d_mean_anomaly_deg")), 3)
        self.assertIn("NOT verified", html)
        self.assertNotIn("SYNTHETIC DEMONSTRATION DATA", html)   # this fixture dataset is not synthetic-labelled
        # printable and script-proof
        self.assertIn("@media print", html)
        self.assertIn("Content-Security-Policy", html)
        self.assertIn("default-src 'none'", html)
        self.assertNotIn("<script", html.lower())

    def test_report_marks_synthetic_data_and_escapes_html(self):
        a = make_tle(90001, 15.0, 0.0)
        b = make_tle(90002, 15.2, 355.0)
        evil = "<script>alert(1)</script>"
        text = f"{evil}\n{a.line1}\n{a.line2}\n{b.name}\n{b.line1}\n{b.line2}\n"
        st, ds = call(self.svc, "import_dataset", body={"text": text, "origin": "synthetic", "source_description": "synthetic <b>test</b>"})
        st, rec = call(self.svc, "run_analysis", body={"dataset_id": ds["id"], "object_a": "90001", "object_b": "90002", "duration_s": 14400})
        self.assertEqual(st, 200, rec)
        st, html = call(self.svc, "report_html", {"analysis_id": str(rec["id"])})
        self.assertIn("SYNTHETIC DEMONSTRATION DATA", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_report_format_helper_never_shows_unknown_as_zero(self):
        self.assertEqual(f(None), "unavailable")
        self.assertEqual(f(0.0, 3, "km"), "0.000 km")


class TestNoPropagationBackend(unittest.TestCase):
    """Default factory = real SGP4. Without the sgp4 package the API must refuse, never fabricate."""

    @unittest.skipIf(sgp4_status()["available"], "sgp4 is installed here; unavailability path not exercisable")
    def test_503_and_nothing_stored_when_sgp4_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = OfdeService(os.path.join(tmp, "t.sqlite3"))
            st, demo = call(svc, "load_demo")
            self.assertEqual(st, 200)
            st, e = call(svc, "run_analysis", body={"dataset_id": demo["id"], "object_a": "90001", "object_b": "90002"})
            self.assertEqual(st, 503)
            self.assertEqual(e["error"]["code"], "PROPAGATION_UNAVAILABLE")
            self.assertIn("pip install", e["error"]["message"])
            self.assertEqual(call(svc, "list_analyses")[1]["analyses"], [])
            st, s = call(svc, "status")
            self.assertFalse(s["propagation_available"])
            self.assertFalse(s["sgp4"]["verification"]["verified"])
            svc.store.close()


if __name__ == "__main__":
    unittest.main()
