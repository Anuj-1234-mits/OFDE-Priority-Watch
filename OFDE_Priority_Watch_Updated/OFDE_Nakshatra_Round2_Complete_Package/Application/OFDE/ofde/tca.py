"""Closest-approach (TCA) search: coarse grid -> local-minimum bracketing -> golden-section refinement.

Method (documented in SCIENTIFIC_METHOD.md):
 1. Sample separation s(t) = |r_B(t) - r_A(t)| on a uniform grid (step_s) across the window.
 2. Every grid local minimum (including window edges) is a candidate.
 3. Interior candidates are bracketed by their neighbouring grid points and refined with
    golden-section search on f(t) = s(t)^2 until the bracket is <= tol_s.
 4. The smallest refined value is reported as the closest approach *within the analysed window*.
    It is not claimed to be a global minimum; a minimum at a window edge is flagged as not bracketed.
Both objects must be expressed in the same frame (propagator.frame); distances km, speed km/s.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional

from .timeutil import format_utc
from .propagation import Propagator, PropagationError

MAX_SAMPLES = 200_000
_PHI = (math.sqrt(5.0) - 1.0) / 2.0


class AnalysisInputError(ValueError):
    pass


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _norm(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def golden_section_min(f: Callable[[float], float], lo: float, hi: float, tol: float, max_iter: int = 200):
    """Minimise a unimodal f on [lo, hi]. Returns (x_min, f_min, iterations)."""
    if not (hi > lo):
        raise AnalysisInputError("golden-section bracket must have hi > lo")
    a, b = lo, hi
    c = b - _PHI * (b - a)
    d = a + _PHI * (b - a)
    fc, fd = f(c), f(d)
    it = 0
    while (b - a) > tol and it < max_iter:
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - _PHI * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + _PHI * (b - a)
            fd = f(d)
        it += 1
    x = 0.5 * (a + b)
    return x, f(x), it


@dataclass
class TcaResult:
    window_start: datetime
    duration_s: float
    step_s: float
    tol_s: float
    n_samples: int
    tca: datetime
    tca_offset_s: float
    miss_distance_km: float
    rel_position_km: tuple
    rel_velocity_km_s: tuple
    rel_speed_km_s: float
    frame: str
    bracketed: bool
    n_local_minima: int
    candidates: list
    refinement_iterations: int
    grid_min_km: float
    series: dict
    notes: list

    def to_dict(self):
        return {
            "window_start_utc": format_utc(self.window_start), "duration_s": self.duration_s, "step_s": self.step_s,
            "refine_tolerance_s": self.tol_s, "n_samples": self.n_samples,
            "tca_utc": format_utc(self.tca), "tca_offset_s": self.tca_offset_s,
            "miss_distance_km": self.miss_distance_km,
            "rel_position_km": list(self.rel_position_km), "rel_velocity_km_s": list(self.rel_velocity_km_s),
            "rel_speed_km_s": self.rel_speed_km_s, "frame": self.frame,
            "bracketed": self.bracketed, "n_local_minima": self.n_local_minima, "candidates": self.candidates,
            "refinement_iterations": self.refinement_iterations, "grid_min_km": self.grid_min_km,
            "series": self.series, "notes": self.notes,
            "scope": "closest approach within the analysed window only; not a guaranteed global minimum",
        }


def _validate(duration_s, step_s, tol_s):
    for nm, v in (("duration_s", duration_s), ("step_s", step_s), ("tol_s", tol_s)):
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
            raise AnalysisInputError(f"{nm} must be a finite number")
    if duration_s <= 0:
        raise AnalysisInputError("Analysis duration must be greater than zero")
    if step_s <= 0:
        raise AnalysisInputError("Time step must be greater than zero")
    if step_s > duration_s:
        raise AnalysisInputError("Time step must not exceed the analysis duration (insufficient time coverage)")
    if tol_s <= 0:
        raise AnalysisInputError("Refinement tolerance must be greater than zero")
    if duration_s / step_s + 1 > MAX_SAMPLES:
        raise AnalysisInputError(f"Window would need more than {MAX_SAMPLES} samples; increase step_s or reduce duration_s")


def analyse(prop_a: Propagator, prop_b: Propagator, start: datetime, duration_s: float, step_s: float,
            tol_s: float = 1e-3, series_max_points: int = 1500) -> TcaResult:
    _validate(duration_s, step_s, tol_s)
    if prop_a.frame != prop_b.frame:
        raise AnalysisInputError(f"Frame mismatch: {prop_a.frame} vs {prop_b.frame}; refusing to mix frames")
    n = int(math.ceil(duration_s / step_s))
    offsets = [min(k * step_s, duration_s) for k in range(n + 1)]
    if len(offsets) >= 2 and offsets[-1] == offsets[-2]:
        offsets.pop()
    notes = []

    def states(t_off):
        t = start + timedelta(seconds=t_off)
        try:
            ra, va = prop_a.state_at(t)
            rb, vb = prop_b.state_at(t)
        except PropagationError as exc:
            raise PropagationError(exc.code, f"{exc.message} (window offset {t_off:.1f} s, {format_utc(t)})") from exc
        return ra, va, rb, vb

    def sep(t_off):
        ra, _, rb, _ = states(t_off)
        return _norm(_sub(rb, ra))

    grid = []
    for t_off in offsets:
        ra, va, rb, vb = states(t_off)
        grid.append((t_off, _sub(rb, ra), _sub(vb, va)))
    s = [_norm(g[1]) for g in grid]
    m = len(s)

    cand_idx = []
    flat = (max(s) - min(s)) <= 1e-9 * max(1.0, max(s))   # round-off-level variation counts as constant
    for i in range(0 if flat else m):
        left = s[i - 1] if i > 0 else None
        right = s[i + 1] if i < m - 1 else None
        if (left is None or s[i] <= left) and (right is None or s[i] < right) and (left is not None or right is not None):
            cand_idx.append(i)
    if flat:  # perfectly flat separation (e.g. identical trajectories): no unique minimum; report the first sample
        cand_idx = [0]
        notes.append("Separation is constant across the window; the first sample is reported")

    candidates, total_iter = [], 0
    for i in cand_idx:
        if 0 < i < m - 1:
            x, fx, it = golden_section_min(lambda t: sep(t) ** 2, offsets[i - 1], offsets[i + 1], tol_s)
            total_iter += it
            d = math.sqrt(max(fx, 0.0))
            if d > s[i]:  # refinement cannot be worse than the grid sample it brackets
                x, d = offsets[i], s[i]
            candidates.append({"offset_s": x, "distance_km": d, "bracketed": True})
        else:
            candidates.append({"offset_s": offsets[i], "distance_km": s[i], "bracketed": bool(flat)})
    best = min(candidates, key=lambda c: c["distance_km"])
    ra, va, rb, vb = states(best["offset_s"])
    rel_r, rel_v = _sub(rb, ra), _sub(vb, va)
    miss = _norm(rel_r)
    if not best["bracketed"]:
        notes.append("Minimum lies at the edge of the analysis window: the true closest approach may be outside it. "
                     "Extend the window.")
    if len(candidates) > 1:
        notes.append(f"{len(candidates)} local minima found in the window; the smallest is reported, others are listed.")

    stride = max(1, int(math.ceil(m / series_max_points)))
    keep = sorted(set(range(0, m, stride)) | {m - 1} | set(cand_idx))
    series = {
        "t_offset_s": [offsets[i] for i in keep],
        "separation_km": [s[i] for i in keep],
        "rel_x_km": [grid[i][1][0] for i in keep], "rel_y_km": [grid[i][1][1] for i in keep],
        "rel_z_km": [grid[i][1][2] for i in keep],
    }
    return TcaResult(window_start=start, duration_s=duration_s, step_s=step_s, tol_s=tol_s, n_samples=m,
                     tca=start + timedelta(seconds=best["offset_s"]), tca_offset_s=best["offset_s"],
                     miss_distance_km=miss, rel_position_km=rel_r, rel_velocity_km_s=rel_v,
                     rel_speed_km_s=_norm(rel_v), frame=prop_a.frame, bracketed=best["bracketed"],
                     n_local_minima=len(candidates), candidates=sorted(candidates, key=lambda c: c["distance_km"]),
                     refinement_iterations=total_iter, grid_min_km=min(s), series=series, notes=notes)


def time_within_radius(prop_a: Propagator, prop_b: Propagator, start: datetime, result: TcaResult, radius_km: float):
    """Duration (s) the separation stays below radius_km around the TCA, within the window.
    Walks outward from the TCA in grid steps to find the first crossing each side, then bisects it.
    Returns dict(duration_s, censored_low, censored_high). Assumes a single contiguous dip around the TCA."""
    if radius_km <= 0 or not math.isfinite(radius_km):
        raise AnalysisInputError("radius_km must be positive")

    def sep(t_off):
        t = start + timedelta(seconds=t_off)
        ra, _ = prop_a.state_at(t)
        rb, _ = prop_b.state_at(t)
        return _norm(_sub(rb, ra))

    t0 = result.tca_offset_s
    if result.miss_distance_km >= radius_km:
        return {"duration_s": 0.0, "censored_low": False, "censored_high": False}
    lo_lim, hi_lim = 0.0, result.duration_s

    def edge(direction):
        inside = t0
        step = result.step_s
        while True:
            nxt = inside + direction * step
            nxt = min(max(nxt, lo_lim), hi_lim)
            if sep(nxt) >= radius_km:
                a, b = inside, nxt  # a inside, b outside
                for _ in range(80):
                    mid = 0.5 * (a + b)
                    if sep(mid) < radius_km:
                        a = mid
                    else:
                        b = mid
                    if abs(b - a) < 1e-4:
                        break
                return 0.5 * (a + b), False
            if nxt in (lo_lim, hi_lim):
                return nxt, True
            inside = nxt

    t_lo, cens_lo = edge(-1)
    t_hi, cens_hi = edge(+1)
    return {"duration_s": t_hi - t_lo, "censored_low": cens_lo, "censored_high": cens_hi}
