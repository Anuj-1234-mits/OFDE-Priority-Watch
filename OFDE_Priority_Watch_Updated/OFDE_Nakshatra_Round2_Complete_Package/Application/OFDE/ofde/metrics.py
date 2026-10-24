"""OFDE project-defined decision metrics. These are NOT established aerospace standards.

Definitions (full text in SCIENTIFIC_METHOD.md):

Threat Transfer (TT), baseline b vs alternative k:
    TT_km  = d_b - d_k            [km]   positive: alternative is closer than baseline
    TT_rel = (d_b - d_k) / d_b    [1]    undefined if d_b == 0
    dTCA_s = t_k - t_b            [s]
    dVrel  = v_k - v_b            [km/s]
  d = computed miss distance in the analysed window, t = TCA, v = relative speed at TCA.

Future Exposure Index (FEI) for a case i among a compared set:
    c_d = d_ref / (d_ref + d_i)               in (0, 1]      closeness
    c_t = min(1, T_i / t_ref)                 in [0, 1]      dwell inside radius R
    FEI_i = 100 * (w_d*c_d + w_t*c_t) / (w_d + w_t)
  d_ref, R, t_ref, w_d, w_t are user-visible reference parameters, not physical thresholds.
  Cases with missing d_i or T_i are listed as 'unranked' (never zero-filled). FEI is not a probability.

Decision Sensitivity:
    for a swept parameter p with baseline value p0: for each point k,
    S_k = (y_k - y_0) / (p_k - p_0)  [unit of y per unit of p], undefined at p_k == p_0
    plus the least-squares slope of y on p over the swept range and the range (max - min) of y.
"""
from __future__ import annotations

import math
from typing import Optional

DEFAULT_FEI_PARAMS = {"d_ref_km": 5.0, "radius_km": 10.0, "t_ref_s": 3.0, "w_d": 0.7, "w_t": 0.3}


class MetricError(ValueError):
    pass


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def threat_transfer(base: dict, alt: dict) -> dict:
    """base/alt: dicts with miss_distance_km, tca_offset_s, rel_speed_km_s. Missing values give None + reason."""
    out = {"tt_km": None, "tt_rel": None, "delta_tca_s": None, "delta_rel_speed_km_s": None, "notes": []}
    db, da = base.get("miss_distance_km"), alt.get("miss_distance_km")
    if _finite(db) and _finite(da):
        out["tt_km"] = db - da
        if db > 0:
            out["tt_rel"] = (db - da) / db
        else:
            out["notes"].append("Relative Threat Transfer undefined: baseline miss distance is zero")
    else:
        out["notes"].append("Miss distance unavailable for baseline or alternative")
    tb, ta = base.get("tca_offset_s"), alt.get("tca_offset_s")
    if _finite(tb) and _finite(ta):
        out["delta_tca_s"] = ta - tb
    vb, va = base.get("rel_speed_km_s"), alt.get("rel_speed_km_s")
    if _finite(vb) and _finite(va):
        out["delta_rel_speed_km_s"] = va - vb
    return out


def validate_fei_params(params: Optional[dict]) -> dict:
    p = dict(DEFAULT_FEI_PARAMS)
    p.update(params or {})
    for k in DEFAULT_FEI_PARAMS:
        if not _finite(p[k]):
            raise MetricError(f"FEI parameter {k} must be a finite number")
    for k in ("d_ref_km", "radius_km", "t_ref_s"):
        if p[k] <= 0:
            raise MetricError(f"FEI parameter {k} must be > 0")
    if p["w_d"] < 0 or p["w_t"] < 0 or (p["w_d"] + p["w_t"]) <= 0:
        raise MetricError("FEI weights must be non-negative and not both zero")
    return p


def fei_value(d_km: float, dwell_s: float, p: dict) -> dict:
    c_d = p["d_ref_km"] / (p["d_ref_km"] + d_km)
    c_t = min(1.0, dwell_s / p["t_ref_s"])
    fei = 100.0 * (p["w_d"] * c_d + p["w_t"] * c_t) / (p["w_d"] + p["w_t"])
    return {"closeness": c_d, "dwell_term": c_t, "fei": fei}


def fei_ranking(cases: list, params: Optional[dict] = None) -> dict:
    """cases: list of {id, name, miss_distance_km, dwell_s}. Returns ranking (desc FEI, ties by smaller miss) + unranked."""
    p = validate_fei_params(params)
    ranked, unranked = [], []
    for c in cases:
        d, t = c.get("miss_distance_km"), c.get("dwell_s")
        if not _finite(d) or d < 0 or not _finite(t) or t < 0:
            unranked.append({"id": c.get("id"), "name": c.get("name"), "reason": "missing or invalid miss distance / dwell time"})
            continue
        v = fei_value(d, t, p)
        ranked.append({"id": c.get("id"), "name": c.get("name"), "miss_distance_km": d, "dwell_s": t, **v})
    ranked.sort(key=lambda r: (-r["fei"], r["miss_distance_km"], str(r["id"])))
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i
    return {"params": p, "ranking": ranked, "unranked": unranked,
            "disclaimer": "FEI is a project-defined comparative indicator. It is not a collision probability or a standard risk score."}


def sensitivity_table(param_name: str, param_unit: str, base_value: float, points: list, output_name: str, output_unit: str) -> dict:
    """points: list of {p: parameter value, y: output value or None}. Includes the baseline-relative slope table."""
    if not _finite(base_value):
        raise MetricError("baseline parameter value must be finite")
    y0 = None
    for pt in points:
        if _finite(pt.get("p")) and abs(pt["p"] - base_value) < 1e-12 and _finite(pt.get("y")):
            y0 = pt["y"]
    rows = []
    for pt in points:
        p, y = pt.get("p"), pt.get("y")
        row = {"p": p, "y": y, "delta_p": None, "delta_y": None, "slope": None}
        if _finite(p) and _finite(y) and y0 is not None:
            row["delta_p"] = p - base_value
            row["delta_y"] = y - y0
            if abs(row["delta_p"]) > 1e-12:
                row["slope"] = row["delta_y"] / row["delta_p"]
        rows.append(row)
    valid = [(r["p"], r["y"]) for r in rows if _finite(r["p"]) and _finite(r["y"])]
    ls_slope = None
    if len(valid) >= 2:
        mp = sum(p for p, _ in valid) / len(valid)
        my = sum(y for _, y in valid) / len(valid)
        den = sum((p - mp) ** 2 for p, _ in valid)
        if den > 0:
            ls_slope = sum((p - mp) * (y - my) for p, y in valid) / den
    return {"parameter": param_name, "parameter_unit": param_unit, "baseline_value": base_value,
            "output": output_name, "output_unit": output_unit, "rows": rows,
            "least_squares_slope": ls_slope,
            "output_range": (max(y for _, y in valid) - min(y for _, y in valid)) if valid else None,
            "n_valid": len(valid), "n_total": len(rows),
            "kind": "sensitivity experiment (hypothetical perturbation); not a validated uncertainty estimate"}
