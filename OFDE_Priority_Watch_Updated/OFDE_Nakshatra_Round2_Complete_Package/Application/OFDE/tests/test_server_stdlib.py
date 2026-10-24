"""Real HTTP round-trips through the stdlib transport (same route table as FastAPI)."""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from ofde.server_stdlib import make_handler
from ofde.service import OfdeService
from tests.fixtures import circle_from_tle, fixture_status
from tests.test_scenarios import make_tle


class TestHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.svc = OfdeService(os.path.join(cls.tmp.name, "h.sqlite3"), propagator_factory=circle_from_tle, status_fn=fixture_status)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.svc))
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.svc.store.close()
        cls.tmp.cleanup()

    def req(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def test_index_served_and_is_self_contained(self):
        st, h, body = self.req("GET", "/")
        self.assertEqual(st, 200)
        self.assertIn("text/html", h["Content-Type"])
        html = body.decode()
        self.assertIn("Orbital Future Decision Engine", html)
        for forbidden in ("http://cdn", "https://cdn", "unpkg.com", "googleapis.com", "<script src="):
            self.assertNotIn(forbidden, html)   # offline requirement: no external assets

    def test_status_and_cors(self):
        st, h, body = self.req("GET", "/api/status")
        self.assertEqual(st, 200)
        self.assertEqual(h["Access-Control-Allow-Origin"], "*")
        self.assertIn("ofde_version", json.loads(body))

    def test_unknown_route_and_wrong_method(self):
        self.assertEqual(self.req("GET", "/api/nope")[0], 404)
        self.assertEqual(self.req("POST", "/api/status", {})[0], 405)

    def test_bad_json_is_400(self):
        r = urllib.request.Request(self.base + "/api/analyses", data=b"{oops", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(r, timeout=10)
        self.assertEqual(cm.exception.code, 400)

    def test_full_demo_workflow_over_http(self):
        a, b = make_tle(90001, 15.0, 0.0), make_tle(90002, 15.2, 355.0)
        text = f"{a.name}\n{a.line1}\n{a.line2}\n{b.name}\n{b.line1}\n{b.line2}\n"
        st, _, body = self.req("POST", "/api/datasets/import", {"text": text, "origin": "manual", "source_description": "http test", "filename": "h.tle"})
        self.assertEqual(st, 200, body)
        ds = json.loads(body)
        self.assertNotIn("original_text", ds)
        st, _, body = self.req("POST", "/api/analyses", {"dataset_id": ds["id"], "object_a": "90001", "object_b": "90002",
                                                         "scenarios": [{"name": "alt", "perturbations": {"b": {"d_mean_anomaly_deg": 1}}}]})
        self.assertEqual(st, 200, body)
        rec = json.loads(body)
        self.assertEqual(len(rec["scenarios"]), 2)
        st, h, body = self.req("GET", f"/api/analyses/{rec['id']}/report.html")
        self.assertEqual(st, 200)
        self.assertIn("text/html", h["Content-Type"])
        self.assertIn("attachment", h["Content-Disposition"])
        st, h, body = self.req("GET", f"/api/analyses/{rec['id']}/report.csv")
        self.assertIn("text/csv", h["Content-Type"])
        self.assertIn("scenario_id", body.decode())
        st, _, body = self.req("GET", f"/api/dashboard?dataset_id={ds['id']}&analysis_id={rec['id']}")
        d = json.loads(body)
        self.assertEqual(d["selected_analysis_id"], rec["id"])
        self.assertEqual(d["total_scenarios"], 2)
        st, _, body = self.req("GET", "/api/metrics/definitions")
        self.assertIn("project-defined", json.loads(body)["category"])

    def test_inline_tle_analysis_validate_and_json_export_over_http(self):
        a, b = make_tle(90001, 15.0, 0.0), make_tle(90002, 15.2, 355.0)
        st, _, body = self.req("POST", "/api/tle/validate", {"text": f"{a.name}\n{a.line1}\n{a.line2}"})
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(body)["valid"][0]["catalog_number"], "90001")
        st, _, body = self.req("POST", "/api/analyses", {"tle_a": f"{a.name}\n{a.line1}\n{a.line2}",
                                                         "tle_b": f"{b.name}\n{b.line1}\n{b.line2}", "origin": "manual"})
        self.assertEqual(st, 200, body)
        rec = json.loads(body)
        st, h, body = self.req("GET", f"/api/analyses/{rec['id']}/export.json")
        self.assertEqual(st, 200)
        self.assertIn("application/json", h["Content-Type"])
        self.assertEqual(json.loads(body)["analysis"]["reproducibility"]["result_sha256"], rec["reproducibility"]["result_sha256"])
        st, _, body = self.req("POST", "/api/analyses", {"tle_a": "garbage", "tle_b": f"{b.line1}\n{b.line2}"})
        self.assertEqual(st, 422)
        self.assertIn("Object A", json.loads(body)["error"]["message"])


if __name__ == "__main__":
    unittest.main()
