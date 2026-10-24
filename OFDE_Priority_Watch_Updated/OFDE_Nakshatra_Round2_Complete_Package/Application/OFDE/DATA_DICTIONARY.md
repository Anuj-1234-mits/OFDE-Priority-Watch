# Data dictionary

Unknown values are `null` (shown as "unknown" or "unavailable"), never `0` or an empty string.

## Dataset (stored; `original_text` is kept verbatim but not returned by the API)

| Field | Type | Meaning |
|---|---|---|
| `id` | int | Database id |
| `name`, `filename` | string / null | Label; source filename if any |
| `format` | string | "TLE (2-line / 3-line)" |
| `origin` | `real` / `synthetic` / `manual` | Required provenance class |
| `source_description` | string | Required: where the elements came from (and when) |
| `imported_utc` | UTC string | Import time |
| `units_frame_assumptions` | string | Units and frame statement |
| `validation` | object | `outcome` (`accepted`, `accepted_with_rejections`, `rejected`), `accepted`, `rejected`, `warnings` |
| `objects` | list | See below |
| `rejected` | list | Records refused, with `issues` (code, message, line) and `source_lines` |
| `cases` | list | Predefined pairs: `id`, `object_a`, `object_b`, `description`, `suggested_window` |

## Object

| Field | Unit | Meaning |
|---|---|---|
| `object_id` | | Catalog number (duplicates get `#2`, `#3` and a warning) |
| `name` | | From name line; null if unknown |
| `object_type` | | PAYLOAD / DEBRIS / ... only if supplied as metadata; null = unknown (TLEs do not carry it) |
| `tle.epoch_utc` | UTC | Element epoch (resolution 8.64e-4 s) |
| `tle.inclination_deg`, `raan_deg`, `arg_perigee_deg`, `mean_anomaly_deg` | deg | Mean elements |
| `tle.eccentricity` | 1 | From 7 digits, implied decimal point |
| `tle.mean_motion_rev_per_day` | rev/day | Kozai mean motion as in TLE |
| `tle.period_min` | min | 1440 / mean motion |
| `tle.bstar_per_earth_radius` | 1/Re | B* drag term |
| `tle.ndot_rev_per_day2`, `nddot_rev_per_day3` | | As given in TLE |
| `tle.line1`, `line2` | | Original lines (trailing whitespace removed with a warning if present) |
| `provenance` | | `origin`, `source`, `filename`, `imported_utc`, `source_lines` |
| `issues` | | Validation messages: `severity` (error/warning/info), `code`, `message` |

## Analysis request (`POST /api/analyses`)

| Field | Default | Unit / range |
|---|---|---|
| `tle_a`, `tle_b` (+ `origin`, `source_description`) **or** `dataset_id`, `object_a`, `object_b` | required | Inline TLEs (one TLE per field) or two different dataset objects |
| `start_utc` | later TLE epoch | ISO 8601 with Z or offset (naive times rejected) |
| `duration_s` | 14400 | s, 0 < d <= 432000 |
| `step_s` | 30 | s, 0.01 to 3600, must not exceed duration |
| `tol_s` | 0.001 | s, refinement tolerance |
| `scenarios` | [] | up to 12: `{name, perturbations:{a:{...}, b:{...}}}` |
| `fei` | defaults | `d_ref_km`, `radius_km`, `t_ref_s`, `w_d`, `w_t` |
| `sensitivity` | [] | up to 4: `{target, parameter, values:[...]}` or `{min, max, n}` (2 to 21 points) |

Perturbation parameters: `d_mean_anomaly_deg` (deg, +/-30), `d_mean_motion_rev_per_day` (rev/day, +/-0.05), `d_inclination_deg` (deg, +/-5), `d_raan_deg` (deg, +/-5), `bstar_scale` (factor 0 to 100; 1 = unchanged).

## Analysis record (response, stored)

`id`, `title`, `created_utc`, `status` ("computed"), `dataset` (provenance snapshot), `objects.a/b`, `window`, `input_summary` (`epoch_a_utc`, `epoch_b_utc`, `epoch_difference_s`, window start minus each epoch in days), `scenarios[]`, `comparison[]`, `fei`, `sensitivity[]`, `warnings[]`, `limitations[]`, `software`, `reproducibility`.

Each scenario: `id`, `name`, `perturbations`, `changes`, `tle_a`, `tle_b` (lines used), `propagator` (`name`, `version`, `frame`, `category`), `dwell` (`duration_s`, `radius_km`, `censored_low/high`), and `result`:

| `result` field | Unit | Meaning |
|---|---|---|
| `tca_utc`, `tca_offset_s` | UTC / s | Time of closest approach, offset from window start |
| `miss_distance_km` | km | Separation at TCA |
| `rel_position_km` | km | B minus A, TEME |
| `rel_velocity_km_s`, `rel_speed_km_s` | km/s | B minus A, TEME; magnitude |
| `bracketed` | bool | Minimum strictly inside the window |
| `n_local_minima`, `candidates[]` | | All local minima found, smallest first |
| `grid_min_km` | km | Smallest grid sample (always >= refined miss) |
| `series` | km, s | Thinned samples: `t_offset_s`, `separation_km`, `rel_x/y/z_km` |
| `notes`, `scope` | | Plain-language caveats |

`reproducibility`: `request` (canonical, includes dataset SHA-256), `request_sha256`, `result_sha256`.

## Endpoints

`GET /` dashboard; `GET /api/status`; `GET /api/datasets`; `POST /api/datasets/import` (`text`, `origin`, `source_description`, optional `name`, `filename`); `POST /api/datasets/demo`; `GET /api/datasets/{id}`; `POST /api/reset`; `GET /api/dashboard?dataset_id=&analysis_id=`; `GET /api/metrics/definitions`; `POST /api/analyses`; `GET /api/analyses`; `GET /api/analyses/{id}`; `GET /api/analyses/{id}/report.html`, `report.csv`, `sensitivity.csv`, `export.json`; `POST /api/tle/validate`. Full details: `API_REFERENCE.md`.

Errors: `{"error":{"code","message"}}` with 400 (invalid input), 404, 422 (propagation or data failure), 503 (`PROPAGATION_UNAVAILABLE`), 500 (unexpected).
