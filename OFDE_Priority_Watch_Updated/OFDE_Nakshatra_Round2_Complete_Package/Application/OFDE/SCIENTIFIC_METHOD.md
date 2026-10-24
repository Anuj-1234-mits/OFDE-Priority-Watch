# Scientific method

## 1. Categories of result

Computed (by tested software), Input (user or dataset), Illustrative (synthetic), Unavailable, External. In the dashboard: computed results carry a "computed" chip and the propagator name and version; synthetic datasets carry a "synthetic (fictitious)" chip and banner; unavailable values display "unavailable", never 0.

## 2. Inputs, time, frame, units

* Input: TLE mean elements (SGP4/SDP4 convention). Angles deg, mean motion rev/day, B* 1/earth-radii.
* Time: all timestamps are UTC. SGP4 uses time since the TLE epoch; OFDE passes UTC for both the epoch and requested times, so only differences matter and UT1-UTC (<0.9 s) cancels in relative geometry. No conversion to Earth-fixed frames is performed.
* Frame: SGP4 outputs **TEME**, km and km/s. Both objects use the same propagator type and frame; `analyse()` refuses mismatched frames.
* Units: distance km, speed km/s, time s or UTC. `units.py` holds conversions (tested).
* Constants: `sgp4` WGS-72 gravity constants (standard for TLE/SGP4).

## 2b. Input handling and epochs

Users may paste two TLEs (validated server-side; errors are attributed to object A or B) or select dataset objects. The record keeps the original lines, origin class (real/synthetic/manual) and source text. The two TLE epochs, their difference and the window start relative to each epoch are stored (`input_summary`) and warned about (older epoch propagated further; heuristics: 7 days from window start, 1 day between epochs).

## 3. Propagation

`Sgp4Propagator` calls `Satrec.twoline2rv` / `Satrec.sgp4` from the pinned `sgp4` package. Nonzero SGP4 error codes (1 to 6) and non-finite states raise `PropagationError` with the object and window offset; the analysis stops explicitly.

Limitations: a TLE is a fitted mean-element set, not a measurement; accuracy degrades with age (OFDE warns when the window start is more than 7 days from an epoch; 7 days is a heuristic, not a standard). No covariance is available. Deep-space objects (period >= 225 min) use SDP4 and are flagged.

**Validation (to be run on your machine):** `tools/verify_sgp4.py` and `tests/test_sgp4_required.py` compare against reference case 00005 (Vallado SGP4-VER) at t = 0 and 360 min (position tolerance 1e-4 km, velocity 1e-6 km/s) and check ISS self-consistency (radius 6600 to 6900 km, speed 7.5 to 7.8 km/s, velocity vs finite difference of position < 1e-4 km/s). **The reference digits were transcribed from memory and could not be cross-checked offline.** A mismatch should first prompt a comparison with the sgp4 package's own test data.

## 4. Closest approach (TCA)

Separation s(t) = |r_B(t) - r_A(t)|.

1. Sample s on a uniform grid with step h across [0, T]; the last sample is clipped to T.
2. Candidates: grid samples with s_i <= s_{i-1} and s_i < s_{i+1} (window edges included).
3. For each interior candidate, minimise f(t) = s(t)^2 on [t_{i-1}, t_{i+1}] by **golden-section search** (bracket shrinks by 0.618 per iteration) until the bracket is <= tol (default 1e-3 s). f is smooth and locally unimodal near a close pass, so the bracket is valid. The refined value is never allowed to exceed the grid sample it brackets.
4. The smallest refined value is the reported closest approach. TCA = start + t*. Relative position and velocity at t* come from the propagator states (km, km/s); relative speed is |v_B - v_A|.
5. If the best candidate is a window edge it is reported with `bracketed = false` and a warning: the true minimum may lie outside the window. Perfectly (to 1e-9 relative) constant separation is reported as constant with no unique minimum.

Scope: the result is the minimum **within the analysed window**, not a proven global minimum. Assumption: s(t) has no features narrower than the grid step h; for LEO periods (about 90 min) h = 30 s is comfortable. Check by halving h.

**Time inside radius R (dwell):** starting at t*, walk outward in grid steps until s >= R, then bisect that bracket (1e-4 s). If the window edge is reached first, the value is flagged *censored*. Assumes one contiguous dip around the TCA.

**Validation:** closed-form tests (`tests/test_tca.py`): linear relative motion (TCA = -r0.v/|v|^2, miss = |r0 x v|/|v|), coplanar circles with different radii (miss = |R2 - R1| at phase alignment), grid-step independence, window-edge flag, multiple minima, identical/constant trajectories, injected propagation failure, invalid windows, and closed-form dwell time 2*sqrt(R^2 - d^2)/v.

## 5. Scenarios (what-if edits)

A scenario is a set of explicit edits to TLE fields of object A and/or B: `d_mean_anomaly_deg`, `d_mean_motion_rev_per_day`, `d_inclination_deg`, `d_raan_deg`, `bstar_scale`, each with a documented range (see `/api/metrics/definitions`). The edited TLE is regenerated with correct checksums; the original is untouched; every change (field, original, new, unit) is recorded and the TLE lines used are in the report. Values are quantised to TLE resolution (angles 1e-4 deg, mean motion 1e-8 rev/day). These edits are **hypothetical** and are not a covariance model.

## 6. Project-defined metrics (not aerospace standards)

**Threat Transfer** (baseline b vs alternative k): TT_km = d_b - d_k [km]; TT_rel = TT_km / d_b [1] (undefined if d_b = 0); dTCA = t_k - t_b [s]. Positive: alternative passes closer. Worked example: d_b = 10, d_k = 6 gives 4 km, 0.40.

**Future Exposure Index** for a compared case: c_d = d_ref/(d_ref + d); c_t = min(1, T/t_ref); FEI = 100 (w_d c_d + w_t c_t)/(w_d + w_t). Defaults d_ref = 5 km, R = 10 km, t_ref = 3 s, w_d = 0.7, w_t = 0.3, all user-visible and adjustable; they are conventions, not physical thresholds. Ranking is by FEI descending, ties by smaller miss distance. Cases with missing d or T are listed as unranked (never zero-filled). Worked example: d = d_ref = 5 km, T = 1.5 s, t_ref = 3 s gives FEI = 50. FEI is not a collision probability or a universal risk score.

**Decision Sensitivity:** for a swept parameter with baseline value p_0 (0, or 1 for `bstar_scale`; the baseline point is always added), S_k = (y_k - y_0)/(p_k - p_0) in unit of y per unit of p, plus the least-squares slope over the sweep and the output range. Output y is miss distance (km) or TCA offset (s). Worked example: y = 2p + 1 gives slope 2.

Validation: `tests/test_metrics.py` (worked examples, bounds, monotonicity, ties, missing data, parameter validation), `tests/test_service_workflow.py` (closed-form TCA shift per degree of phase, -1/rate s/deg).

## 7. Sensitivity versus uncertainty

Sensitivity analysis: "if this input differed by this amount, how would the answer change?" Uncertainty propagation: "given a distribution of input errors, how uncertain is the answer?" The latter needs a state covariance and a stated distribution. TLEs do not provide one, so **Monte Carlo and collision probability are unavailable** and are not approximated. Sweeps are labelled sensitivity experiments everywhere (UI, report, CSV). The "distribution of computed outputs" chart is the spread of what-if outputs, not a probability distribution.

## 8. Synthetic demo set

Four fictitious objects (`data/demo_synthetic.json`). A two-body design aid (`tools/generate_demo.py`) chose object B's phasing so a close pass should exist; its numbers (about 3 km at about 8750 s) are **not results** and are not used by the application. Real values come from SGP4 on your machine, and may differ; `tools/tune_demo_sgp4.py` re-phases B with SGP4 itself.
