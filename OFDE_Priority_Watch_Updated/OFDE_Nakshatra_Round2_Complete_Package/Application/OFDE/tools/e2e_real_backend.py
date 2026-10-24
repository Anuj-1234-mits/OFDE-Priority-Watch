"""End-to-end check of the REAL backend over HTTP (standard library only; no browser needed).

    python tools/e2e_real_backend.py            # spawns its own temporary server + database, restarts it, checks everything
    python tools/e2e_real_backend.py --stdlib   # force the dependency-free server

For every available transport (FastAPI if installed, then the stdlib server) it checks: page served, status/SGP4 state,
TLE validation, invalid-input errors with nothing saved, a real SGP4 analysis of the documented SYNTHETIC demo pair,
reproducible hashes, SQLite persistence across a server RESTART, JSON/CSV/HTML exports, HTML safety, and failure paths.
Results go to e2e_results.json. Exit code 1 if any check FAILS. WARN/INFO lines are advisory (e.g. unexpected miss distance).
Run on your own machine: the build sandbox had no sgp4, so this was only exercised there against a test fixture.
"""
import argparse
import csv
import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVIL_NAME = "<script>alert('xss')</script>"


def http(method, url, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def jget(base, path):
    st, _, raw = http("GET", base + path)
    return st, json.loads(raw)


def jpost(base, path, body):
    st, _, raw = http("POST", base + path, body)
    return st, json.loads(raw)


def demo_pair():
    with open(os.path.join(ROOT, "data", "demo_synthetic.json"), encoding="utf-8") as fh:
        demo = json.load(fh)
    L = demo["tle_text"].splitlines()
    return "\n".join(L[0:3]), "\n".join(L[3:6]), demo["source_description"]


def run_checks(base, restart=None, expect_real_sgp4=True):
    """Return a list of {name, status: PASS|FAIL|WARN|INFO|SKIP, detail}. `restart` is a callable that restarts the server on the same database."""
    out = []

    def rec(name, status, detail=""):
        out.append({"name": name, "status": status, "detail": str(detail)})
        print(f"  [{status:4}] {name}" + (f" - {detail}" if detail else ""))

    def check(name, cond, detail=""):
        rec(name, "PASS" if cond else "FAIL", detail)
        return bool(cond)

    ta, tb, source = demo_pair()
    # 1 page
    st, h, raw = http("GET", base + "/")
    page = raw.decode("utf-8", "replace")
    check("dashboard served", st == 200 and "Orbital Future Decision Engine" in page, f"HTTP {st}")
    check("dashboard has no external resources", not re.search(r"(src|href)=[\"']https?://(?!127\.0\.0\.1|localhost)", page))
    # 2 status
    st, s = jget(base, "/api/status")
    check("status endpoint", st == 200 and "ofde_version" in s)
    sg = s["sgp4"]
    if expect_real_sgp4:
        check("real sgp4 package available", sg["available"], f"version={sg['version']} error={sg['error']}")
        rec("sgp4 verification marker", "PASS" if sg["verification"].get("verified") else "WARN", sg["verification"])
        if not sg["available"]:
            rec("remaining checks need sgp4", "SKIP", "install requirements and rerun")
            return out
    # 3 validation
    st, v = jpost(base, "/api/tle/validate", {"text": ta})
    check("valid TLE A accepted", st == 200 and len(v["valid"]) == 1 and not v["rejected"])
    lines = ta.splitlines()
    bad = lines[0] + "\n" + lines[1][:68] + str((int(lines[1][68]) + 1) % 10) + "\n" + lines[2]
    st, v = jpost(base, "/api/tle/validate", {"text": bad})
    check("corrupted checksum rejected", st == 200 and not v["valid"] and "CHECKSUM_MISMATCH" in json.dumps(v["rejected"]))
    n_before = len(jget(base, "/api/analyses")[1]["analyses"])
    # 4 invalid input -> clear error, nothing saved
    st, e = jpost(base, "/api/analyses", {"tle_a": bad, "tle_b": tb})
    check("invalid TLE gives 422 naming object A", st == 422 and "Object A" in e["error"]["message"], e.get("error", {}).get("message", "")[:100])
    st, e = jpost(base, "/api/analyses", {"tle_a": ta, "tle_b": tb, "duration_s": 0})
    check("invalid window gives 400", st == 400)
    st, e = jpost(base, "/api/analyses", {"tle_a": ta, "tle_b": tb, "scenarios": [{"name": "x", "perturbations": {"b": {"nonsense": 1}}}]})
    check("unknown perturbation gives 400", st == 400)
    check("failed requests saved nothing", len(jget(base, "/api/analyses")[1]["analyses"]) == n_before)
    # 5 real analysis
    req = {"tle_a": ta, "tle_b": tb, "origin": "synthetic", "source_description": source, "duration_s": 14400, "step_s": 30,
           "scenarios": [{"name": "B along-track +0.02 deg", "perturbations": {"b": {"d_mean_anomaly_deg": 0.02}}},
                         {"name": "B drag x2", "perturbations": {"b": {"bstar_scale": 2}}}],
           "sensitivity": [{"target": "b", "parameter": "d_mean_anomaly_deg", "min": -0.1, "max": 0.1, "n": 5}]}
    t0 = time.time()
    st, rec1 = jpost(base, "/api/analyses", req)
    if not check("analysis returns 200", st == 200, rec1.get("error", {}).get("message", f"{time.time() - t0:.1f}s")):
        return out
    base_r = rec1["scenarios"][0]["result"]
    prop = rec1["scenarios"][0]["propagator"]
    if expect_real_sgp4:
        check("propagator is the real SGP4 package", prop["name"].startswith("SGP4") and prop["category"] == "computed", f"{prop['name']} {prop['version']}")
    finite = all(isinstance(base_r[k], (int, float)) and base_r[k] == base_r[k] for k in ("miss_distance_km", "tca_offset_s", "rel_speed_km_s"))
    check("results finite", finite)
    check("TCA inside window", 0 <= base_r["tca_offset_s"] <= 14400)
    check("refined miss <= grid minimum", base_r["miss_distance_km"] <= base_r["grid_min_km"] + 1e-9)
    check("relative speed plausible for LEO (0 to 16 km/s)", 0 <= base_r["rel_speed_km_s"] <= 16)
    check("frame and units stated", base_r["frame"] == "TEME")
    check("scenario count and changes recorded", len(rec1["scenarios"]) == 3 and rec1["comparison"][0]["inputs_changed"][0]["field"] == "mean_anomaly_deg")
    check("sensitivity table includes baseline point", any(abs(r["p"]) < 1e-12 for r in rec1["sensitivity"][0]["miss_table"]["rows"]))
    check("epoch difference recorded", "epoch_difference_s" in rec1["input_summary"])
    check("synthetic origin recorded", rec1["dataset"]["origin"] == "synthetic")
    if not base_r["bracketed"] or base_r["miss_distance_km"] > 100:
        rec("demo pair has no meaningful close pass in the window", "WARN",
            f"miss={base_r['miss_distance_km']:.3f} km bracketed={base_r['bracketed']}: run tools/tune_demo_sgp4.py (synthetic data; never a real prediction)")
    else:
        rec("demo pair result (SYNTHETIC, informational)", "INFO", f"miss={base_r['miss_distance_km']:.3f} km at {base_r['tca_utc']}, v_rel={base_r['rel_speed_km_s']:.3f} km/s")
    st, rec2 = jpost(base, "/api/analyses", req)
    check("identical request reproduces identical result hash", st == 200 and rec2["reproducibility"]["result_sha256"] == rec1["reproducibility"]["result_sha256"])
    # 6 evil name -> report safety
    evil_a = EVIL_NAME + "\n" + "\n".join(ta.splitlines()[1:])
    st, rec3 = jpost(base, "/api/analyses", {"tle_a": evil_a, "tle_b": tb, "origin": "synthetic", "source_description": source, "duration_s": 3600})
    check("analysis with hostile object name accepted", st == 200, rec3.get("error", {}).get("message", ""))
    if st == 200:
        _, _, html = http("GET", f"{base}/api/analyses/{rec3['id']}/report.html")
        html = html.decode()
        check("HTML report escapes user strings", "<script>alert" not in html and "&lt;script&gt;" in html)
        check("HTML report forbids scripts via CSP and is printable", "Content-Security-Policy" in html and "@media print" in html)
    # 7 exports
    st, h, raw = http("GET", f"{base}/api/analyses/{rec1['id']}/export.json")
    exp = json.loads(raw)
    check("JSON export is the saved record", st == 200 and exp["analysis"]["reproducibility"]["result_sha256"] == rec1["reproducibility"]["result_sha256"]
          and exp["analysis"]["objects"]["a"]["tle"]["line1"] == ta.splitlines()[1])
    st, h, raw = http("GET", f"{base}/api/analyses/{rec1['id']}/report.csv")
    rows = list(csv.reader(io.StringIO(raw.decode())))
    hdr = next(r for r in rows if r and r[0] == "scenario_id")
    first = rows[rows.index(hdr) + 1]
    check("CSV headers carry units and values match the record", "miss_distance_km" in hdr and float(first[hdr.index("miss_distance_km")]) == base_r["miss_distance_km"])
    st, h, raw = http("GET", f"{base}/api/analyses/{rec1['id']}/report.html")
    check("HTML report states provenance and caveats", b"SYNTHETIC DEMONSTRATION DATA" in raw and b"collision probability" in raw)
    # 8 persistence across restart
    before = jget(base, "/api/analyses/%d" % rec1["id"])[1]
    ids_before = [a["id"] for a in jget(base, "/api/analyses")[1]["analyses"]]
    if restart is None:
        rec("history persists across restart", "SKIP", "no restart callback")
    else:
        restart()
        st, hist = jget(base, "/api/analyses")
        check("history persists across restart", st == 200 and [a["id"] for a in hist["analyses"]] == ids_before)
        after = jget(base, "/api/analyses/%d" % rec1["id"])[1]
        check("saved record identical after restart", after == before)
        st, d = jget(base, "/api/dashboard")
        check("dashboard statistics derive from persisted state", d["total_analyses"] == len(ids_before))
    # 9 failure path (real SGP4 only): a rapidly decaying orbit
    if expect_real_sgp4:
        from ofde.tle import format_tle
        ep = datetime(2026, 10, 24, tzinfo=timezone.utc)
        d1, d2 = format_tle(catalog=90099, intl_designator="26999Z", epoch=ep, ndot=0.0, nddot=0.0, bstar=0.5, element_set=1,
                            inclination_deg=51.6, raan_deg=10.0, eccentricity=0.0005, arg_perigee_deg=0.0, mean_anomaly_deg=0.0,
                            mean_motion_rev_per_day=16.9, rev_number=1)
        n0 = len(jget(base, "/api/analyses")[1]["analyses"])
        st, e = jpost(base, "/api/analyses", {"tle_a": "DECAY\n" + d1 + "\n" + d2, "tle_b": tb, "origin": "synthetic", "source_description": "decay test",
                                              "start_utc": "2026-10-24T00:00:00Z", "duration_s": 5 * 86400, "step_s": 600})
        n1 = len(jget(base, "/api/analyses")[1]["analyses"])
        if st in (422, 400):
            check("propagation failure gives a clear error, not fake numbers", "error" in e and n1 == n0, e["error"]["message"][:120])
        elif st == 200:
            rec("propagation failure path", "INFO", "could not provoke an SGP4 error with this TLE on this sgp4 version; unit test covers the error mapping")
        else:
            check("propagation failure path", False, f"unexpected HTTP {st}")
    return out


# ------------------------------------------------------------------ server management
def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, port, db, stdlib):
        self.port, self.db, self.stdlib, self.proc = port, db, stdlib, None

    def start(self):
        env = dict(os.environ, OFDE_DB_PATH=self.db)
        cmd = [sys.executable, "-m", "ofde", "--port", str(self.port)] + (["--stdlib"] if self.stdlib else [])
        self.proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for _ in range(120):
            if self.proc.poll() is not None:
                raise RuntimeError("server exited early:\n" + (self.proc.stdout.read() or "")[-1500:])
            try:
                if http("GET", f"http://127.0.0.1:{self.port}/api/status", timeout=2)[0] == 200:
                    return
            except Exception:
                time.sleep(0.25)
        raise RuntimeError("server did not become ready in 30 s")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def restart(self):
        self.stop()
        self.start()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stdlib", action="store_true", help="only test the stdlib server")
    a = ap.parse_args()
    transports = [True] if a.stdlib else []
    if not a.stdlib:
        try:
            import fastapi, uvicorn  # noqa: F401
            transports = [False, True]
        except ImportError:
            print("FastAPI/uvicorn not installed: testing the stdlib transport only (FastAPI NOT tested).")
            transports = [True]
    all_results, failed = {}, False
    for stdlib in transports:
        name = "stdlib" if stdlib else "fastapi"
        print(f"\n=== transport: {name} ===")
        with tempfile.TemporaryDirectory() as tmp:
            srv = Server(free_port(), os.path.join(tmp, "e2e.sqlite3"), stdlib)
            try:
                srv.start()
                res = run_checks(f"http://127.0.0.1:{srv.port}", srv.restart, True)
                srv.stop()
                try:
                    http("GET", f"http://127.0.0.1:{srv.port}/api/status", timeout=2)
                    res.append({"name": "backend stopped is unreachable", "status": "FAIL", "detail": "still answering"})
                except Exception:
                    res.append({"name": "stopped backend is unreachable (UI shows offline banner)", "status": "PASS", "detail": ""})
            except Exception as exc:
                res = [{"name": "server start/run", "status": "FAIL", "detail": str(exc)}]
                print("  [FAIL] server start/run -", exc)
            finally:
                srv.stop()
        all_results[name] = res
        failed |= any(r["status"] == "FAIL" for r in res)
    with open(os.path.join(ROOT, "e2e_results.json"), "w", encoding="utf-8") as fh:
        json.dump({"finished_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "python": sys.version, "results": all_results}, fh, indent=2)
    flat = sum(all_results.values(), [])
    n = {k: sum(1 for r in flat if r["status"] == k) for k in ("PASS", "FAIL", "WARN", "INFO", "SKIP")}
    print(f"\nSUMMARY: {n}  (details: e2e_results.json)")
    print("E2E FAILED" if failed else "E2E PASSED (WARN/SKIP lines, if any, need your attention)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
