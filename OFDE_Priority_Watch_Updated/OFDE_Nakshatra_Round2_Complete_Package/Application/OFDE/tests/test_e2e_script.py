"""Tests the logic of tools/e2e_real_backend.run_checks against an in-process server using the TEST-FIXTURE propagator
(expect_real_sgp4=False). This validates the checking script, including a genuine server restart on the same SQLite file.
It is NOT real-SGP4 verification: run `python tools/e2e_real_backend.py` on a machine with sgp4 for that."""
import importlib.util
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

from ofde.server_stdlib import make_handler
from ofde.service import OfdeService
from tests.fixtures import circle_from_tle, fixture_status

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("e2e_mod", os.path.join(ROOT, "tools", "e2e_real_backend.py"))
e2e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e2e)


class Harness:
    def __init__(self, db):
        self.db, self.httpd, self.svc, self.port = db, None, None, 0

    def start(self):
        self.svc = OfdeService(self.db, propagator_factory=circle_from_tle, status_fn=fixture_status)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), make_handler(self.svc))
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.svc.store.close()

    def restart(self):
        self.stop()
        self.start()


class TestRunChecks(unittest.TestCase):
    def test_all_generic_checks_pass_with_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(os.path.join(tmp, "e.sqlite3"))
            h.start()
            try:
                res = e2e.run_checks(f"http://127.0.0.1:{h.port}", h.restart, expect_real_sgp4=False)
            finally:
                h.stop()
        fails = [r for r in res if r["status"] == "FAIL"]
        self.assertEqual(fails, [])
        names = {r["name"] for r in res if r["status"] == "PASS"}
        for must in ("history persists across restart", "saved record identical after restart", "HTML report escapes user strings",
                     "HTML report forbids scripts via CSP and is printable", "failed requests saved nothing",
                     "identical request reproduces identical result hash", "JSON export is the saved record",
                     "CSV headers carry units and values match the record", "invalid TLE gives 422 naming object A"):
            self.assertIn(must, names)
        self.assertFalse(any(r["name"].startswith("propagator is the real") for r in res))   # not claimed for the fixture

    def test_script_detects_a_broken_backend(self):
        """A backend that loses history on restart must be reported as FAIL (the checker is not vacuous)."""
        with tempfile.TemporaryDirectory() as tmp:
            h = Harness(os.path.join(tmp, "e.sqlite3"))
            h.start()

            def lossy_restart():
                h.stop()
                h.db = os.path.join(tmp, "other.sqlite3")   # new empty database
                h.start()
            try:
                res = e2e.run_checks(f"http://127.0.0.1:{h.port}", lossy_restart, expect_real_sgp4=False)
            finally:
                h.stop()
        self.assertTrue(any(r["name"] == "history persists across restart" and r["status"] == "FAIL" for r in res))

    def test_real_sgp4_expectation_fails_loudly_without_sgp4(self):
        from ofde.propagation import sgp4_status
        if sgp4_status()["available"]:
            self.skipTest("sgp4 installed")
        with tempfile.TemporaryDirectory() as tmp:
            svc = OfdeService(os.path.join(tmp, "e.sqlite3"))   # default (real) factory
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(svc))
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                res = e2e.run_checks(f"http://127.0.0.1:{httpd.server_address[1]}", None, expect_real_sgp4=True)
            finally:
                httpd.shutdown(); httpd.server_close(); svc.store.close()
        self.assertTrue(any(r["name"] == "real sgp4 package available" and r["status"] == "FAIL" for r in res))


if __name__ == "__main__":
    unittest.main()
