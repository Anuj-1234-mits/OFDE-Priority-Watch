"""WIRING tests for ofde.propagation and tools/verify_sgp4.py using a FAKE `sgp4` module injected into sys.modules.

These tests are NOT SGP4 verification and are reported separately. They check OUR code: arguments passed to the library,
SGP4 error-code mapping, unavailable/rejected handling, the verification-marker lifecycle, and the pass/fail/exit-code
logic of verify_sgp4.py. Real SGP4 behaviour is covered only by tests/test_sgp4_required.py on a machine with sgp4."""
import importlib.util
import json
import math
import os
import sys
import tempfile
import types
import unittest
from datetime import timedelta

from ofde import propagation, reference_cases as ref
from ofde.tle import parse_tle, with_checksum
from ofde.timeutil import UTC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def install_fake(script=None, version="9.9.9"):
    """Install fake sgp4 + sgp4.api. `script(satrec, jd, fr)` returns (err, r, v)."""
    calls = {"jday": [], "twoline": [], "sgp4": []}
    api = types.ModuleType("sgp4.api")
    api.WGS72 = "WGS72"

    def jday(y, mo, d, h, mi, s):
        calls["jday"].append((y, mo, d, h, mi, s))
        from datetime import datetime
        jd0 = datetime(y, mo, d).toordinal() + 1721424.5
        return jd0, (h + mi / 60 + s / 3600) / 24.0
    api.jday = jday

    class Satrec:
        @classmethod
        def twoline2rv(cls, l1, l2, const=None):
            calls["twoline"].append((l1, l2, const))
            if "BAD" in l1:
                raise ValueError("fake rejection")
            o = cls()
            t, _ = parse_tle(l1, l2)
            y, mo, d, h, mi, s = t.epoch.year, t.epoch.month, t.epoch.day, t.epoch.hour, t.epoch.minute, t.epoch.second + t.epoch.microsecond / 1e6
            o.jdsatepoch, o.jdsatepochF = jday(y, mo, d, h, mi, s)
            o.cat = t.catalog_number
            return o

        def sgp4(self, jd, fr):
            calls["sgp4"].append((jd, fr))
            return script(self, jd, fr)
    api.Satrec = Satrec
    pkg = types.ModuleType("sgp4")
    pkg.__version__ = version
    pkg.api = api
    sys.modules["sgp4"], sys.modules["sgp4.api"] = pkg, api
    return calls


def remove_fake():
    for k in ("sgp4", "sgp4.api"):
        sys.modules.pop(k, None)


class FakeBase(unittest.TestCase):
    def setUp(self):
        self._real = {k: sys.modules.get(k) for k in ("sgp4", "sgp4.api")}
        self._marker = propagation.VERIFICATION_MARKER
        self.tmp = tempfile.TemporaryDirectory()
        propagation.VERIFICATION_MARKER = os.path.join(self.tmp.name, "marker.json")
        # make importlib.metadata unable to find the fake package so the adapter falls back to __version__
        self.iss, _ = parse_tle(ref.ISS_LINE1, ref.ISS_LINE2, "ISS")

    def tearDown(self):
        remove_fake()
        for k, v in self._real.items():
            if v is not None:
                sys.modules[k] = v
        propagation.VERIFICATION_MARKER = self._marker
        self.tmp.cleanup()


class TestAdapter(FakeBase):
    def test_arguments_passed_to_library_and_state_returned(self):
        calls = install_fake(lambda s, jd, fr: (0, (1.0, 2.0, 3.0), (0.1, 0.2, 0.3)))
        p = propagation.Sgp4Propagator(self.iss)
        self.assertEqual(calls["twoline"][0][:2], (self.iss.line1, self.iss.line2))
        self.assertEqual(calls["twoline"][0][2], "WGS72")
        from datetime import datetime
        r, v = p.state_at(datetime(2000, 1, 1, 12, 30, 15, 500000, tzinfo=UTC))
        self.assertEqual(calls["jday"][-1], (2000, 1, 1, 12, 30, 15.5))   # UTC components, seconds incl. fraction
        self.assertEqual((r, v), ((1.0, 2.0, 3.0), (0.1, 0.2, 0.3)))
        self.assertEqual(p.frame, "TEME")
        self.assertEqual(p.category, "computed")

    def test_non_utc_input_is_converted_to_utc(self):
        calls = install_fake(lambda s, jd, fr: (0, (1.0, 0, 0), (0, 1.0, 0)))
        p = propagation.Sgp4Propagator(self.iss)
        from datetime import datetime, timezone
        ist = timezone(timedelta(hours=5, minutes=30))
        p.state_at(datetime(2026, 10, 24, 5, 30, 0, tzinfo=ist))
        self.assertEqual(calls["jday"][-1], (2026, 10, 24, 0, 0, 0.0))

    def test_every_sgp4_error_code_becomes_propagation_error(self):
        for code in range(1, 7):
            install_fake(lambda s, jd, fr, c=code: (c, (math.nan,) * 3, (math.nan,) * 3))
            p = propagation.Sgp4Propagator(self.iss)
            with self.assertRaises(propagation.PropagationError) as cm:
                p.state_at(self.iss.epoch)
            self.assertEqual(cm.exception.code, "SGP4_ERROR")
            self.assertIn(propagation.SGP4_ERRORS[code], cm.exception.message)
            self.assertIn("25544", cm.exception.message)

    def test_non_finite_state_is_an_error_not_a_number(self):
        install_fake(lambda s, jd, fr: (0, (math.inf, 0, 0), (0, 0, 0)))
        with self.assertRaises(propagation.PropagationError) as cm:
            propagation.Sgp4Propagator(self.iss).state_at(self.iss.epoch)
        self.assertEqual(cm.exception.code, "NON_FINITE_STATE")

    def test_library_rejecting_the_tle_is_reported(self):
        install_fake(lambda s, jd, fr: (0, (0, 0, 0), (0, 0, 0)))
        class T:  # TLE object whose line1 makes the fake raise
            line1, line2, catalog_number = "BAD " + self.iss.line1, self.iss.line2, "1"
        with self.assertRaises(propagation.PropagationError) as cm:
            propagation.Sgp4Propagator(T())
        self.assertEqual(cm.exception.code, "TLE_REJECTED_BY_SGP4")

    def test_unavailable_when_package_missing(self):
        remove_fake()
        sys.modules["sgp4"] = None   # makes `import sgp4` raise ImportError
        sys.modules["sgp4.api"] = None
        st = propagation.sgp4_status()
        self.assertFalse(st["available"])
        with self.assertRaises(propagation.PropagationUnavailable) as cm:
            propagation.Sgp4Propagator(self.iss)
        self.assertIn("pip install", cm.exception.message)

    def test_status_reports_version_when_present(self):
        install_fake(lambda s, jd, fr: (0, (0, 0, 0), (0, 0, 0)), version="9.9.9")
        st = propagation.sgp4_status()
        self.assertTrue(st["available"])
        self.assertIsNotNone(st["version"])


class TestMarker(FakeBase):
    def write(self, **kw):
        with open(propagation.VERIFICATION_MARKER, "w") as fh:
            json.dump(kw, fh)

    def test_missing_marker_is_unverified(self):
        self.assertFalse(propagation.read_verification_marker("1.0")["verified"])

    def test_pass_marker_with_matching_version(self):
        self.write(passed=True, sgp4_version="1.0", checked_utc="t", checks=[])
        self.assertTrue(propagation.read_verification_marker("1.0")["verified"])

    def test_version_mismatch_invalidates(self):
        self.write(passed=True, sgp4_version="1.0")
        m = propagation.read_verification_marker("2.0")
        self.assertFalse(m["verified"])
        self.assertIn("re-run", m["reason"])

    def test_failed_or_corrupt_marker_is_unverified(self):
        self.write(passed=False, sgp4_version="1.0")
        self.assertFalse(propagation.read_verification_marker("1.0")["verified"])
        with open(propagation.VERIFICATION_MARKER, "w") as fh:
            fh.write("{not json")
        self.assertFalse(propagation.read_verification_marker("1.0")["verified"])


def load_verify_tool():
    spec = importlib.util.spec_from_file_location("verify_tool", os.path.join(ROOT, "tools", "verify_sgp4.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TestVerifyToolLogic(FakeBase):
    """Fake library that reproduces the reference table exactly / with an error. Checks pass-fail logic and exit codes only."""

    def scripted(self, perturb=0.0):
        def f(sat, jd, fr):
            if sat.cat == "00005":
                tsince = ((jd - sat.jdsatepoch) + (fr - sat.jdsatepochF)) * 1440.0
                for t, r, v in ref.CASE_00005_STATES:
                    if abs(tsince - t) < 1e-3:
                        return 0, (r[0] + perturb, r[1], r[2]), v
                return 0, (7000.0, 0, 0), (0, 7.5, 0)
            # circular motion for the ISS consistency checks: radius 6800 km, speed 7.55 km/s
            t = ((jd - sat.jdsatepoch) + (fr - sat.jdsatepochF)) * 86400.0
            R, w = 6800.0, 7.55 / 6800.0
            return 0, (R * math.cos(w * t), R * math.sin(w * t), 0.0), (-R * w * math.sin(w * t), R * w * math.cos(w * t), 0.0)
        return f

    def run_tool(self, perturb):
        install_fake(self.scripted(perturb))
        tool = load_verify_tool()
        tool.VERIFICATION_MARKER = propagation.VERIFICATION_MARKER
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = tool.main()
        return code, buf.getvalue()

    def test_pass_path_writes_marker_with_version(self):
        code, out = self.run_tool(0.0)
        self.assertEqual(code, 0, out)
        with open(propagation.VERIFICATION_MARKER) as fh:
            m = json.load(fh)
        self.assertTrue(m["passed"])
        self.assertEqual(m["sgp4_version"], propagation.sgp4_status()["version"])
        self.assertTrue(all(c["passed"] for c in m["checks"]))

    def test_discrepancy_fails_exit_code_and_removes_stale_marker(self):
        with open(propagation.VERIFICATION_MARKER, "w") as fh:
            json.dump({"passed": True, "sgp4_version": "x"}, fh)
        code, out = self.run_tool(0.5)   # 0.5 km discrepancy >> 1e-4 km tolerance
        self.assertEqual(code, 2, out)
        self.assertIn("FAIL", out)
        self.assertFalse(os.path.exists(propagation.VERIFICATION_MARKER))

    def test_missing_package_returns_1(self):
        remove_fake()
        sys.modules["sgp4"], sys.modules["sgp4.api"] = None, None
        tool = load_verify_tool()
        tool.VERIFICATION_MARKER = propagation.VERIFICATION_MARKER
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tool.main(), 1)
        self.assertFalse(os.path.exists(propagation.VERIFICATION_MARKER))


if __name__ == "__main__":
    unittest.main()
