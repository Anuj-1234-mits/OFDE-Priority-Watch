"""Round-2 additions: inline two-TLE analysis, live validation, exports, persistence across restart, config, repo hygiene."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

from ofde import config
from ofde.service import OfdeService, ROUTES
from tests.fixtures import circle_from_tle, fixture_status
from tests.test_scenarios import make_tle
from tests.test_service_workflow import call, make_service

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tle_text(t, name=True):
    return (f"{t.name}\n" if name else "") + f"{t.line1}\n{t.line2}"


class TestInlineAnalysis(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.svc = make_service(self.tmp.name)
        self.a, self.b = make_tle(90001, 15.0, 0.0), make_tle(90002, 15.2, 355.0)

    def tearDown(self):
        self.svc.store.close()
        self.tmp.cleanup()

    def test_two_pasted_tles_are_analysed_and_stored(self):
        st, rec = call(self.svc, "run_analysis", body={"tle_a": tle_text(self.a), "tle_b": tle_text(self.b, name=False),
                                                       "origin": "real", "source_description": "unit test paste"})
        self.assertEqual(st, 200, rec)
        self.assertAlmostEqual(rec["scenarios"][0]["result"]["tca_offset_s"], 6000.0, delta=5e-3)
        self.assertEqual(rec["dataset"]["origin"], "real")
        self.assertEqual(rec["dataset"]["source_description"], "unit test paste")
        self.assertEqual(rec["input_summary"]["epoch_difference_s"], 0.0)
        # original TLEs preserved
        self.assertEqual(rec["objects"]["a"]["tle"]["line1"], self.a.line1)
        self.assertEqual(rec["objects"]["b"]["tle"]["line2"], self.b.line2)
        ds = call(self.svc, "list_datasets")[1]["datasets"]
        self.assertEqual(len(ds), 1)

    def test_source_defaults_to_explicit_unstated(self):
        st, rec = call(self.svc, "run_analysis", body={"tle_a": tle_text(self.a), "tle_b": tle_text(self.b)})
        self.assertEqual(st, 200)
        self.assertIn("source not stated", rec["dataset"]["source_description"])
        self.assertEqual(rec["dataset"]["origin"], "manual")

    def test_invalid_tle_is_attributed_and_nothing_stored(self):
        bad = self.a.line1[:68] + str((int(self.a.line1[68]) + 1) % 10)
        st, e = call(self.svc, "run_analysis", body={"tle_a": f"X\n{bad}\n{self.a.line2}", "tle_b": tle_text(self.b)})
        self.assertEqual((st, e["error"]["code"]), (422, "TLE_INVALID"))
        self.assertIn("Object A", e["error"]["message"])
        self.assertIn("checksum", e["error"]["message"])
        self.assertEqual(call(self.svc, "list_datasets")[1]["datasets"], [])
        self.assertEqual(call(self.svc, "list_analyses")[1]["analyses"], [])

    def test_missing_second_tle_and_multiple_tles_in_one_box(self):
        st, e = call(self.svc, "run_analysis", body={"tle_a": tle_text(self.a)})
        self.assertEqual(st, 400)
        st, e = call(self.svc, "run_analysis", body={"tle_a": tle_text(self.a) + "\n" + tle_text(self.b), "tle_b": tle_text(self.b)})
        self.assertEqual(st, 422)
        self.assertIn("exactly one", e["error"]["message"])

    def test_epoch_difference_is_reported_and_warned(self):
        from datetime import timedelta
        from ofde.tle import format_tle, parse_tle
        late = self.b.epoch + timedelta(days=2)
        l1, l2 = format_tle(catalog=90002, intl_designator="26999A", epoch=late, ndot=0.0, nddot=0.0, bstar=2.0e-5, element_set=1,
                            inclination_deg=74.0, raan_deg=40.0, eccentricity=0.0001, arg_perigee_deg=0.0,
                            mean_anomaly_deg=355.0, mean_motion_rev_per_day=15.2, rev_number=1)
        st, rec = call(self.svc, "run_analysis", body={"tle_a": tle_text(self.a), "tle_b": f"B\n{l1}\n{l2}", "duration_s": 600})
        self.assertEqual(st, 200, rec)
        self.assertAlmostEqual(rec["input_summary"]["epoch_difference_s"], 2 * 86400.0, delta=1.0)
        self.assertTrue(any("epochs differ" in w for w in rec["warnings"]))
        st, html = call(self.svc, "report_html", {"analysis_id": str(rec["id"])})
        self.assertIn("Epoch difference", html)

    def test_user_supplied_name_is_escaped_in_report(self):
        evil = self.a
        txt = f"<img src=x onerror=alert(1)>\n{evil.line1}\n{evil.line2}"
        st, rec = call(self.svc, "run_analysis", body={"tle_a": txt, "tle_b": tle_text(self.b)})
        self.assertEqual(st, 200)
        st, html = call(self.svc, "report_html", {"analysis_id": str(rec["id"])})
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;img src=x", html)


class TestValidateEndpoint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.svc = make_service(self.tmp.name)

    def tearDown(self):
        self.svc.store.close()
        self.tmp.cleanup()

    def test_valid_and_rejected(self):
        a = make_tle(90001, 15.0, 0.0)
        st, r = call(self.svc, "validate_tle", body={"text": tle_text(a)})
        self.assertEqual(st, 200)
        self.assertEqual(len(r["valid"]), 1)
        self.assertEqual(r["valid"][0]["catalog_number"], "90001")
        self.assertAlmostEqual(r["valid"][0]["period_min"], 96.0, places=2)
        st, r = call(self.svc, "validate_tle", body={"text": a.line1[:60] + "\n" + a.line2})
        self.assertEqual(len(r["valid"]), 0)
        self.assertIn("BAD_LENGTH", json.dumps(r["rejected"]))

    def test_empty_is_400_and_nothing_stored(self):
        self.assertEqual(call(self.svc, "validate_tle", body={"text": ""})[0], 400)
        self.assertEqual(call(self.svc, "validate_tle", body={})[0], 400)
        self.assertEqual(call(self.svc, "list_datasets")[1]["datasets"], [])


class TestExportsAndPersistence(unittest.TestCase):
    def test_history_survives_restart_and_exports_match_saved_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = make_service(tmp)
            a, b = make_tle(90001, 15.0, 0.0), make_tle(90002, 15.2, 355.0)
            st, rec = call(svc, "run_analysis", body={"tle_a": tle_text(a), "tle_b": tle_text(b), "scenarios": [
                {"name": "B shifted", "perturbations": {"b": {"d_mean_anomaly_deg": 1.0}}}]})
            self.assertEqual(st, 200)
            db = svc.store.path
            svc.store.close()
            # "restart": brand-new service object on the same database file
            svc2 = OfdeService(db, propagator_factory=circle_from_tle, status_fn=fixture_status)
            hist = call(svc2, "list_analyses")[1]["analyses"]
            self.assertEqual([h["id"] for h in hist], [rec["id"]])
            self.assertEqual(hist[0]["baseline_miss_km"], rec["scenarios"][0]["result"]["miss_distance_km"])
            st, saved = call(svc2, "get_analysis", {"analysis_id": str(rec["id"])})
            self.assertEqual(saved["reproducibility"]["result_sha256"], rec["reproducibility"]["result_sha256"])
            # JSON export: valid, complete, equals the saved record
            st, ctype, raw, headers = svc2.handle([r for r in ROUTES if r.handler == "export_json"][0], {"analysis_id": str(rec["id"])}, {}, None)
            self.assertEqual(st, 200)
            self.assertIn("attachment", headers["Content-Disposition"])
            exp = json.loads(raw)
            self.assertEqual(exp["ofde_export_version"], 1)
            self.assertEqual(exp["analysis"], saved)
            self.assertEqual(exp["analysis"]["objects"]["a"]["tle"]["line1"], a.line1)   # original TLE preserved
            self.assertEqual(exp["analysis"]["window"]["step_s"], 30.0)                  # settings preserved
            # CSV: headers with units, rows equal saved numbers
            st, csv_text = call(svc2, "report_csv", {"analysis_id": str(rec["id"])})
            hdr = [l for l in csv_text.splitlines() if l.startswith("scenario_id")][0].split(",")
            for col in ("tca_utc", "tca_offset_s", "miss_distance_km", "rel_speed_km_s", "dwell_s", "dwell_radius_km"):
                self.assertIn(col, hdr)
            self.assertIn("units: distance km, speed km/s, time s / UTC", csv_text)
            self.assertIn(repr(saved["scenarios"][1]["result"]["miss_distance_km"]), csv_text)
            svc2.store.close()

    def test_history_is_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = make_service(tmp)
            a, b = make_tle(90001, 15.0, 0.0), make_tle(90002, 15.2, 355.0)
            ids = [call(svc, "run_analysis", body={"tle_a": tle_text(a), "tle_b": tle_text(b)})[1]["id"] for _ in range(3)]
            self.assertEqual([h["id"] for h in call(svc, "list_analyses")[1]["analyses"]], ids[::-1])
            svc.store.close()


class TestDashboardAggregation(unittest.TestCase):
    def test_totals_span_all_datasets_and_mode_follows_selected_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = make_service(tmp)
            a, b = make_tle(90001, 15.0, 0.0), make_tle(90002, 15.2, 355.0)
            call(svc, "run_analysis", body={"tle_a": tle_text(a), "tle_b": tle_text(b), "origin": "real", "source_description": "x"})
            st, r2 = call(svc, "run_analysis", body={"tle_a": tle_text(a), "tle_b": tle_text(b), "origin": "synthetic", "source_description": "y",
                                                     "scenarios": [{"name": "s", "perturbations": {"b": {"d_mean_anomaly_deg": 1}}}]})
            self.assertEqual(st, 200)
            st, d = call(svc, "dashboard")
            self.assertEqual((d["total_analyses"], d["total_scenarios"]), (2, 3))     # two datasets, one analysis each
            self.assertEqual(d["mode_origin"], "synthetic")
            self.assertTrue(d["demo_mode"])
            first = call(svc, "list_analyses")[1]["analyses"][-1]["id"]
            st, d = call(svc, "dashboard", query={"analysis_id": str(first)})
            self.assertEqual(d["mode_origin"], "real")
            self.assertFalse(d["demo_mode"])
            svc.store.close()


class TestConfigAndHygiene(unittest.TestCase):
    def test_dotenv_loaded_but_environment_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, ".env")
            with open(p, "w") as fh:
                fh.write('# comment\nOFDE_TEST_A="one"\nOFDE_TEST_B=two\n\nbadline\n')
            os.environ.pop("OFDE_TEST_A", None)
            os.environ["OFDE_TEST_B"] = "from-env"
            try:
                loaded = config.load_dotenv(p)
                self.assertEqual(os.environ["OFDE_TEST_A"], "one")
                self.assertEqual(os.environ["OFDE_TEST_B"], "from-env")
                self.assertEqual(loaded, {"OFDE_TEST_A": "one"})
            finally:
                os.environ.pop("OFDE_TEST_A", None)
                os.environ.pop("OFDE_TEST_B", None)
        self.assertEqual(config.load_dotenv(os.path.join(ROOT, "definitely-missing.env")), {})

    def test_relative_paths_resolve_under_project_root(self):
        self.assertTrue(config.resolve_path("ofde.sqlite3").startswith(ROOT))
        self.assertEqual(config.resolve_path(os.path.abspath(__file__)), os.path.abspath(__file__))

    def test_no_machine_specific_absolute_paths_in_shipped_source(self):
        bad = re.compile(r"(/home/claude|/mnt/user-data|C:\\Users\\|/Users/[a-z]+/|/tmp/ofde)", re.I)
        offenders = []
        for sub in ("ofde", "tools", "frontend", "data", "tests"):
            for dp, _dn, fns in os.walk(os.path.join(ROOT, sub)):
                if "__pycache__" in dp:
                    continue
                for fn in fns:
                    path = os.path.join(dp, fn)
                    if fn == os.path.basename(__file__):
                        continue
                    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                        if bad.search(fh.read()):
                            offenders.append(os.path.relpath(path, ROOT))
        self.assertEqual(offenders, [])

    def test_frontend_api_base_is_correct(self):
        with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as fh:
            html = fh.read()
        self.assertIn('location.protocol.startsWith("http") ? "" : "http://127.0.0.1:8000"', html)
        self.assertNotIn("localhost:3000", html)

    def test_module_entrypoint_help_runs(self):
        r = subprocess.run([sys.executable, "-m", "ofde", "--help"], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--stdlib", r.stdout)

    def test_requirements_pins_are_exact(self):
        for fn in ("requirements.txt", "requirements-dev.txt"):
            with open(os.path.join(ROOT, fn)) as fh:
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith(("#", "-r")):
                        self.assertIn("==", line, f"{fn}: {line} is not pinned")


if __name__ == "__main__":
    unittest.main()
