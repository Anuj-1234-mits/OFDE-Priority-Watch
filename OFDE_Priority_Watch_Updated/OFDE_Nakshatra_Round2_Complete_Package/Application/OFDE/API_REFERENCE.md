# API reference

Base URL `http://127.0.0.1:8000`. JSON in/out unless noted. CORS is open for local development. Errors: `{"error":{"code","message"}}` with 400 (invalid input), 404, 405, 422 (data/propagation failure), 503 (`PROPAGATION_UNAVAILABLE`), 500.

| Method and path | Purpose |
|---|---|
| `GET /` | Dashboard (`frontend/index.html`) |
| `GET /api/status` | Versions, SGP4 availability and verification status, counts |
| `POST /api/tle/validate` | Body `{text}`. Validates TLE text without storing; returns `valid[]` (name, catalog, epoch, inclination, period, issues) and `rejected[]` (issues) |
| `GET /api/datasets` | List datasets |
| `POST /api/datasets/import` | Body `{text, origin: real|synthetic|manual, source_description (required), name?, filename?}` |
| `POST /api/datasets/demo` | Load the synthetic demo dataset |
| `GET /api/datasets/{id}` | Dataset with objects, provenance, rejected records, cases (no raw text) |
| `POST /api/reset` | Delete all datasets and analyses, reload demo |
| `GET /api/dashboard?dataset_id=&analysis_id=` | Statistics derived from stored state (totals span all analyses) |
| `GET /api/metrics/definitions` | Metric formulas, supported what-if parameters and ranges, limitations |
| `POST /api/analyses` | Run and save an analysis (below) |
| `GET /api/analyses` | History, newest first |
| `GET /api/priority-watch` | Persistent Priority Watch alerts, open/acknowledged first |
| `POST /api/priority-watch` | Create alert: `{priority: critical|needs_attention, reason, analysis_id?, restricted_label?}` |
| `POST /api/priority-watch/{id}/acknowledge` | Acknowledge an open alert |
| `POST /api/priority-watch/{id}/review` | Mark an alert reviewed/resolved |
| `GET /api/analyses/{id}` | Full saved record |
| `GET /api/analyses/{id}/report.html` | Printable HTML report (attachment) |
| `GET /api/analyses/{id}/report.csv` | Scenario and FEI table (attachment) |
| `GET /api/analyses/{id}/sensitivity.csv` | Sensitivity sweep table (attachment) |
| `GET /api/analyses/{id}/export.json` | `{ofde_export_version, exported_utc, analysis}`: the saved record verbatim |

## `POST /api/analyses`

Objects, either **inline TLEs**:
`{"tle_a": "NAME\n1 ...\n2 ...", "tle_b": "...", "origin": "manual", "source_description": "..."}`
(each field must hold exactly one TLE; errors name the object: `Object A: Line 1 checksum ...`), or **dataset objects**:
`{"dataset_id": 1, "object_a": "90001", "object_b": "90002"}`.

Common optional fields: `start_utc` (ISO 8601 with Z; default later TLE epoch), `duration_s` (14400), `step_s` (30), `tol_s` (0.001), `title`, `scenarios[]` (`{name, perturbations:{a:{},b:{}}}`, max 12), `fei` (`d_ref_km, radius_km, t_ref_s, w_d, w_t`), `sensitivity[]` (`{target, parameter, values:[...]}` or `{min,max,n}`).

Response = saved analysis record (see `DATA_DICTIONARY.md`): `scenarios[]` with `result` (TCA, miss, relative vector/velocity, bracketing, candidates, series), `comparison[]` (Threat Transfer), `fei`, `sensitivity[]`, `input_summary` (TLE epochs and epoch difference), `warnings[]`, `limitations[]`, `software`, `reproducibility` (request and result SHA-256).

Nothing is saved when the request fails (validation, propagation error, unavailable SGP4).


## Priority Watch

`GET /api/priority-watch` returns persistent alert records with `id`, `created_utc`, `updated_utc`, optional `analysis_id`, `priority`, `reason`, `restricted_label`, and `status`. Create with `POST /api/priority-watch`; `reason` is required (maximum 1000 characters), `priority` is `critical` or `needs_attention`, and `restricted_label` is one of `none`, `restricted`, `sensitive`, `classified`, or `unknown`. Status starts as `open`, becomes `acknowledged` through the acknowledge endpoint, and becomes `reviewed_resolved` through the review endpoint. Records are stored separately in SQLite and survive restarts. Priority is an operator workflow label only; it is not a collision probability or a certified risk estimate. Restricted-data labels are separate metadata and do not automatically change priority.
