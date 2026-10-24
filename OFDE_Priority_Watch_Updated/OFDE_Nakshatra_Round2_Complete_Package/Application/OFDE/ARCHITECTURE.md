# Architecture

## Data flow

```
TLE text ──► ingest.py ──► tle.py (strict validation) ──► dataset (SQLite, original text kept)
                                                              │
 dashboard (frontend/index.html) ◄── JSON ── service.py ◄─────┤
                                                              ▼
                      scenarios.py (apply hypothetical edits, re-checksum TLE)
                                                              ▼
                      propagation.py (Sgp4Propagator) ──► tca.py (grid + golden-section)
                                                              ▼
                      metrics.py (Threat Transfer, FEI, sensitivity) ──► storage.py ──► report.py (HTML/CSV)
```

## Modules

| Module | Responsibility | UI-free? |
|---|---|---|
| `units.py`, `timeutil.py` | Explicit unit conversions; UTC parsing/formatting; Julian date; TLE epoch | yes |
| `tle.py` | Parse and validate TLE (length, line numbers, checksum, ranges); format TLE for synthetic/perturbed data | yes |
| `ingest.py` | 2/3-line TLE files to records; provenance; rejected records with reasons; original text preserved | yes |
| `propagation.py` | `Propagator` interface; `Sgp4Propagator` adapter; availability and verification status | yes |
| `tca.py` | Separation sampling, local-minimum bracketing, golden-section refinement, dwell time | yes |
| `scenarios.py` | Allowed perturbations, validation, application, per-scenario run | yes |
| `metrics.py` | Project-defined metrics with formulas in the docstring | yes |
| `storage.py` | SQLite persistence | yes |
| `report.py` | HTML/CSV from stored records only (cannot disagree with API output) | yes |
| `config.py` | Optional `.env` loader (OFDE_HOST/PORT/DB_PATH); relative paths resolve under the project root | yes |
| `service.py` | Orchestration (dataset or **inline two-TLE** analyses), live TLE validation, exports, error mapping, dashboard statistics, shared **route table** | yes |
| `__main__.py` | `python -m ofde`: FastAPI+uvicorn if installed, else stdlib server | yes |
| `server_fastapi.py`, `server_stdlib.py` | Two thin transports over the same route table | yes |
| `frontend/index.html` | Presentation only (cinematic UI, inline SVG charts, local starfield canvas); all science is server-side | n/a |

## Design decisions

* **No homemade SGP4.** `Sgp4Propagator` wraps the `sgp4` package. If it is absent, `PropagationUnavailable` is raised and the API answers 503. There is no fallback propagator in the application; analytic propagators exist only under `tests/` and are injected via `OfdeService(propagator_factory=...)`.
* **One route table, two transports.** `service.ROUTES` is used by FastAPI and by the stdlib server, so API behaviour is identical. The stdlib transport is exercised by the tests here; FastAPI is a small wrapper (`server_fastapi.py`) not executed in the sandbox.
* **Verification marker.** `tools/verify_sgp4.py` writes `data/sgp4_verification.json` only if its checks pass on the local machine; the API reports `verified` only then (and only for the same `sgp4` version).
* **Reproducibility.** Each analysis stores the canonical request, a dataset content hash, SHA-256 of request and results, and software versions. Same inputs and same versions give identical result hashes (tested).
* **Dashboard statistics are queries**, never constants (`service.h_dashboard`).
* **Unknown is not zero.** Missing values are `None`/null and rendered "unavailable".
* **Single-file frontend** avoids Node/Vite setup risk during a 12-hour event. Charts are hand-built SVG so nothing loads from the network.

## Trade-offs

* FastAPI's auto-generated schema is minimal because handlers take raw JSON (needed to share one route table). `/docs` lists endpoints but not typed schemas; `DATA_DICTIONARY.md` documents them.
* Pure-Python TCA search is fast enough for LEO windows of hours (milliseconds to a few hundred milliseconds per scenario); screening thousands of pairs would need vectorisation (out of scope).
