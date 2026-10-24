"""Scenario engine: baseline + alternatives. Every change to an input is explicit and recorded.

Supported perturbations are HYPOTHETICAL what-if edits of TLE fields. They are NOT a covariance
model and do not represent validated physical uncertainty.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Callable, Optional

from .tle import Tle, parse_tle, with_checksum, format_implied_exp
from .tca import analyse, time_within_radius, AnalysisInputError
from .propagation import Propagator, PropagationError
from .timeutil import format_utc

# parameter -> (unit, description, min, max)
PERTURBATION_SPECS = {
    "d_mean_anomaly_deg": ("deg", "Add to mean anomaly (shifts the object along its orbit)", -30.0, 30.0),
    "d_mean_motion_rev_per_day": ("rev/day", "Add to mean motion (changes orbital period)", -0.05, 0.05),
    "d_inclination_deg": ("deg", "Add to inclination", -5.0, 5.0),
    "d_raan_deg": ("deg", "Add to right ascension of ascending node", -5.0, 5.0),
    "bstar_scale": ("factor", "Multiply the B* drag term (1 = unchanged)", 0.0, 100.0),
}
TARGETS = ("a", "b")


class ScenarioError(ValueError):
    pass


def validate_perturbations(perts: Optional[dict]) -> dict:
    """Return a cleaned {'a': {...}, 'b': {...}}. Unknown parameters/targets or out-of-range values are errors."""
    perts = perts or {}
    clean = {"a": {}, "b": {}}
    for target, values in perts.items():
        if target not in TARGETS:
            raise ScenarioError(f"Unknown perturbation target {target!r}; use 'a' or 'b'")
        if not isinstance(values, dict):
            raise ScenarioError(f"Perturbations for {target!r} must be an object")
        for key, val in values.items():
            if key not in PERTURBATION_SPECS:
                raise ScenarioError(f"Unknown perturbation parameter {key!r}. Supported: {', '.join(PERTURBATION_SPECS)}")
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
                raise ScenarioError(f"Perturbation {key} must be a finite number")
            unit, _, lo, hi = PERTURBATION_SPECS[key]
            if not (lo <= val <= hi):
                raise ScenarioError(f"Perturbation {key}={val} {unit} outside the supported range [{lo}, {hi}]")
            clean[target][key] = float(val)
    return clean


def apply_perturbations(tle: Tle, perts: dict) -> tuple[Tle, list]:
    """Return (new_tle, changes). The original Tle is untouched. New TLE text is regenerated with correct
    checksums. Values are quantised to TLE field resolution (angles 1e-4 deg, mean motion 1e-8 rev/day)."""
    if not perts:
        return tle, []
    l1, l2 = tle.line1, tle.line2
    changes = []
    inc, raan, ma, n = tle.inclination_deg, tle.raan_deg, tle.mean_anomaly_deg, tle.mean_motion_rev_per_day
    if "d_inclination_deg" in perts:
        new = inc + perts["d_inclination_deg"]
        if not (0.0 <= new <= 180.0):
            raise ScenarioError(f"Perturbed inclination {new} outside [0, 180]")
        changes.append({"field": "inclination_deg", "original": inc, "new": round(new, 4), "unit": "deg"})
        inc = new
    if "d_raan_deg" in perts:
        new = round(raan + perts["d_raan_deg"], 4) % 360.0
        changes.append({"field": "raan_deg", "original": raan, "new": round(new, 4), "unit": "deg"})
        raan = new
    if "d_mean_anomaly_deg" in perts:
        new = round(ma + perts["d_mean_anomaly_deg"], 4) % 360.0
        changes.append({"field": "mean_anomaly_deg", "original": ma, "new": round(new, 4), "unit": "deg"})
        ma = new
    if "d_mean_motion_rev_per_day" in perts:
        new = n + perts["d_mean_motion_rev_per_day"]
        if new <= 0:
            raise ScenarioError("Perturbed mean motion must remain positive")
        changes.append({"field": "mean_motion_rev_per_day", "original": n, "new": round(new, 8), "unit": "rev/day"})
        n = new
    ecc7 = l2[26:33]
    rev = l2[63:68]
    new_l2 = with_checksum(f"2 {tle.catalog_number:>5s} {inc:8.4f} {raan:8.4f} {ecc7} {l2[34:42]} {ma:8.4f} {n:11.8f}{rev}")
    if "bstar_scale" in perts:
        new_b = tle.bstar * perts["bstar_scale"]
        changes.append({"field": "bstar_per_earth_radius", "original": tle.bstar, "new": new_b, "unit": "1/earth-radii"})
        l1 = with_checksum(l1[:53] + format_implied_exp(new_b) + l1[61:68])
    new_tle, issues = parse_tle(l1, new_l2, tle.name)
    if new_tle is None:
        raise ScenarioError("Perturbation produced an invalid TLE: " + "; ".join(i.message for i in issues if i.severity == "error"))
    return new_tle, changes


def run_scenario(factory: Callable[[Tle], Propagator], tle_a: Tle, tle_b: Tle, start: datetime, duration_s: float,
                 step_s: float, tol_s: float, perturbations: Optional[dict], dwell_radius_km: Optional[float] = None) -> dict:
    perts = validate_perturbations(perturbations)
    new_a, ch_a = apply_perturbations(tle_a, perts["a"])
    new_b, ch_b = apply_perturbations(tle_b, perts["b"])
    pa, pb = factory(new_a), factory(new_b)
    res = analyse(pa, pb, start, duration_s, step_s, tol_s)
    out = {
        "perturbations": perts,
        "changes": {"a": ch_a, "b": ch_b},
        "tle_a": {"line1": new_a.line1, "line2": new_a.line2},
        "tle_b": {"line1": new_b.line1, "line2": new_b.line2},
        "result": res.to_dict(),
        "propagator": {"name": pa.name, "version": pa.version, "frame": pa.frame, "category": pa.category},
        "dwell": None,
    }
    if dwell_radius_km is not None:
        dw = time_within_radius(pa, pb, start, res, dwell_radius_km)
        dw["radius_km"] = dwell_radius_km
        out["dwell"] = dw
    return out
