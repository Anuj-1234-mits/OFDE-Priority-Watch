"""FastAPI transport smoke tests. Skipped unless fastapi and httpx are installed."""
import importlib.util
import unittest

HAVE = importlib.util.find_spec("fastapi") is not None and importlib.util.find_spec("httpx") is not None


@unittest.skipUnless(HAVE, "fastapi/httpx not installed in this environment")
class TestFastApi(unittest.TestCase):
    def setUp(self):
        import os, tempfile
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["OFDE_DB_PATH"] = os.path.join(self.tmp.name, "f.sqlite3")
        import importlib
        import ofde.storage, ofde.service, ofde.server_fastapi
        importlib.reload(ofde.storage)
        importlib.reload(ofde.service)
        importlib.reload(ofde.server_fastapi)
        from fastapi.testclient import TestClient
        self.client = TestClient(ofde.server_fastapi.app)

    def tearDown(self):
        self.tmp.cleanup()

    def test_status_and_index(self):
        r = self.client.get("/api/status")
        self.assertEqual(r.status_code, 200)
        self.assertIn("sgp4", r.json())
        self.assertIn("Orbital Future Decision Engine", self.client.get("/").text)

    def test_demo_load_and_validation_errors(self):
        r = self.client.post("/api/datasets/demo")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["origin"], "synthetic")
        r = self.client.post("/api/analyses", content=b"{bad")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.get("/api/analyses/999").status_code, 404)

    def test_report_headers(self):
        ds = self.client.post("/api/datasets/demo").json()
        r = self.client.post("/api/analyses", json={"dataset_id": ds["id"], "object_a": "90001", "object_b": "90002"})
        if r.status_code == 503:
            self.skipTest("sgp4 not installed")
        self.assertEqual(r.status_code, 200)
        rep = self.client.get(f"/api/analyses/{r.json()['id']}/report.html")
        self.assertIn("text/html", rep.headers["content-type"])
        self.assertIn("attachment", rep.headers["content-disposition"])
