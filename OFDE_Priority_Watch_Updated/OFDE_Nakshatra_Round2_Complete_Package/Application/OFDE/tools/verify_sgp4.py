"""Verify the sgp4 integration on THIS machine. Writes data/sgp4_verification.json only if every check passes.

    python tools/verify_sgp4.py

Checks: (1) package importable + version, (2) reference case 00005 via the raw library,
(3) the same reference through OFDE's Sgp4Propagator wrapper, (4) ISS self-consistency
(radius, speed, velocity vs finite-difference of position), (5) informational run of the demo pair (not asserted).
"""
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ofde import reference_cases as ref  # noqa: E402
from ofde.propagation import Sgp4Propagator, sgp4_status, VERIFICATION_MARKER  # noqa: E402
from ofde.tle import parse_tle  # noqa: E402


def dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def main() -> int:
    checks, ok = [], True

    def record(name, passed, detail):
        nonlocal ok
        ok = ok and passed
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
        print(("PASS " if passed else "FAIL ") + name + " - " + detail)

    st = sgp4_status()
    record("sgp4 importable", st["available"], f"version={st['version']} error={st['error']}")
    if not st["available"]:
        print("\nInstall first:  pip install -r requirements.txt")
        return 1
    from sgp4.api import Satrec, WGS72
    sat = Satrec.twoline2rv(ref.CASE_00005_LINE1, ref.CASE_00005_LINE2, WGS72)
    for tsince, r_ref, v_ref in ref.CASE_00005_STATES:
        e, r, v = sat.sgp4(sat.jdsatepoch, sat.jdsatepochF + tsince / 1440.0)
        dr, dv = dist(r, r_ref), dist(v, v_ref)
        record(f"reference 00005 raw library t={tsince:.0f} min", e == 0 and dr <= ref.POSITION_TOL_KM and dv <= ref.VELOCITY_TOL_KM_S,
               f"err={e} |dr|={dr:.3e} km (tol {ref.POSITION_TOL_KM}) |dv|={dv:.3e} km/s (tol {ref.VELOCITY_TOL_KM_S})")
    tle, _ = parse_tle(ref.CASE_00005_LINE1, ref.CASE_00005_LINE2)
    prop = Sgp4Propagator(tle)
    for tsince, r_ref, v_ref in ref.CASE_00005_STATES:
        r, v = prop.state_at(tle.epoch + timedelta(minutes=tsince))
        dr = dist(r, r_ref)
        record(f"reference 00005 via OFDE wrapper t={tsince:.0f} min", dr <= 1e-3, f"|dr|={dr:.3e} km (tol 1e-3: allows epoch microsecond rounding)")
    iss, _ = parse_tle(ref.ISS_LINE1, ref.ISS_LINE2)
    p = Sgp4Propagator(iss)
    t0 = iss.epoch + timedelta(minutes=30)
    r, v = p.state_at(t0)
    rr, sp = math.sqrt(sum(x * x for x in r)), math.sqrt(sum(x * x for x in v))
    record("ISS radius plausible (6600-6900 km)", 6600 <= rr <= 6900, f"{rr:.1f} km")
    record("ISS speed plausible (7.5-7.8 km/s)", 7.5 <= sp <= 7.8, f"{sp:.3f} km/s")
    dt = 0.5
    rp, _ = p.state_at(t0 + timedelta(seconds=dt))
    rm, _ = p.state_at(t0 - timedelta(seconds=dt))
    vfd = tuple((a - b) / (2 * dt) for a, b in zip(rp, rm))
    record("ISS velocity consistent with d(position)/dt", dist(v, vfd) < 1e-4, f"|v - v_fd| = {dist(v, vfd):.3e} km/s")
    try:
        with open(os.path.join(ROOT, "data", "demo_synthetic.json"), encoding="utf-8") as fh:
            demo = json.load(fh)
        lines = [l for l in demo["tle_text"].splitlines()]
        ta, _ = parse_tle(lines[1], lines[2], lines[0])
        tb, _ = parse_tle(lines[4], lines[5], lines[3])
        from ofde.tca import analyse
        res = analyse(Sgp4Propagator(ta), Sgp4Propagator(tb), ta.epoch, 14400.0, 30.0)
        print(f"INFO demo pair (SYNTHETIC) computed by SGP4: miss={res.miss_distance_km:.3f} km at {res.tca.isoformat()} "
              f"bracketed={res.bracketed} (informational, not asserted)")
    except Exception as exc:
        print(f"INFO demo pair run failed: {type(exc).__name__}: {exc}")
    if ok:
        with open(VERIFICATION_MARKER, "w", encoding="utf-8") as fh:
            json.dump({"passed": True, "sgp4_version": st["version"], "checked_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "checks": checks}, fh, indent=2)
        print("\nALL CHECKS PASSED - verification marker written. OFDE will now report propagation as verified.")
        return 0
    if os.path.exists(VERIFICATION_MARKER):
        os.remove(VERIFICATION_MARKER)
    print("\nSOME CHECKS FAILED - no verification marker written; OFDE will keep labelling results as unverified.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
