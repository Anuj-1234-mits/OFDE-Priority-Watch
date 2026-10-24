"""Re-phase synthetic object B using the REAL SGP4 pipeline so the demo pair has a genuine close pass inside the window.

    python tools/tune_demo_sgp4.py            # dry run: prints the best shift and the resulting miss distance
    python tools/tune_demo_sgp4.py --write    # also rewrites data/demo_synthetic.json (B's mean anomaly)

The search shifts B's mean anomaly (the supported 'd_mean_anomaly_deg' perturbation), requires the minimum to be bracketed
and to lie inside the middle 80% of the window, and keeps the smallest miss distance. The data stay fictitious.
"""
import argparse
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ofde.scenarios import run_scenario, apply_perturbations  # noqa: E402
from ofde.tle import parse_tle  # noqa: E402


def tune(factory, tle_a, tle_b, start, duration_s, step_s, span_deg=30.0, coarse_deg=0.25, fine_deg=0.005):
    """Return dict(delta_deg, miss_km, tca_offset_s) for the best bracketed in-window pass, or None if none exists."""
    def evaluate(delta):
        r = run_scenario(factory, tle_a, tle_b, start, duration_s, step_s, 0.01, {"b": {"d_mean_anomaly_deg": delta}})["result"]
        ok = r["bracketed"] and 0.1 * duration_s <= r["tca_offset_s"] <= 0.9 * duration_s
        return (r["miss_distance_km"] if ok else math.inf), r

    def scan(lo, hi, h):
        best = (math.inf, None, None)
        n = int(round((hi - lo) / h))
        for k in range(n + 1):
            d = lo + k * h
            m, r = evaluate(d)
            if m < best[0]:
                best = (m, d, r)
        return best

    m, d, r = scan(-span_deg, span_deg, coarse_deg)
    if d is None:
        return None
    m, d, r = scan(max(-span_deg, d - coarse_deg), min(span_deg, d + coarse_deg), fine_deg)
    return {"delta_deg": d, "miss_km": m, "tca_offset_s": r["tca_offset_s"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    from ofde.propagation import Sgp4Propagator, sgp4_status
    if not sgp4_status()["available"]:
        print("sgp4 is not installed: pip install -r requirements.txt")
        return 1
    path = os.path.join(ROOT, "data", "demo_synthetic.json")
    with open(path, encoding="utf-8") as fh:
        demo = json.load(fh)
    lines = demo["tle_text"].splitlines()
    ta, _ = parse_tle(lines[1], lines[2], lines[0])
    tb, _ = parse_tle(lines[4], lines[5], lines[3])
    res = tune(Sgp4Propagator, ta, tb, ta.epoch, 14400.0, 30.0)
    if res is None:
        print("No bracketed in-window pass found for this pair with the supported shift range.")
        return 2
    print(f"Best shift of B mean anomaly: {res['delta_deg']:+.4f} deg -> SGP4 miss {res['miss_km']:.3f} km at t = {res['tca_offset_s']:.1f} s")
    if a.write:
        new_b, _ = apply_perturbations(tb, {"d_mean_anomaly_deg": res["delta_deg"]})
        lines[4], lines[5] = new_b.line1, new_b.line2
        demo["tle_text"] = "\n".join(lines) + "\n"
        demo["source_description"] += f" Object B phasing re-tuned with SGP4 on this machine (shift {res['delta_deg']:+.4f} deg); still fictitious."
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(demo, fh, indent=2)
        print("data/demo_synthetic.json updated. Re-run: python tools/verify_sgp4.py")
    else:
        print("Dry run: nothing written. Add --write to update the demo file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
