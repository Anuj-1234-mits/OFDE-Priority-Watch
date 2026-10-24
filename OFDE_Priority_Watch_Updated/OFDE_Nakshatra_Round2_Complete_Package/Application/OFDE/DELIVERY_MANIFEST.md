# Delivery manifest

Package: `OFDE_Nakshatra_Round2_Final.zip` (project folder `OFDE/`). Prepared from the existing OFDE codebase (no rewrite); backend preserved, frontend rebuilt around the proven chart/result logic.

## Inventory at the start of Round-2 work

| Category | Items |
|---|---|
| Worked and tested | TLE validation, ingest, TCA search and refinement (closed-form checks), scenarios, metrics, SQLite, reports, route table, stdlib server |
| Existed, unverified | Real SGP4 path, FastAPI transport, pinned versions, SGP4 reference digits |
| Missing or incomplete | Two-TLE entry workspace; live validation; `.env`; single start command; PowerShell launcher; VS Code config; server-side JSON export; epoch-difference reporting; history page; cinematic UI |
| Illustrative | Hero orbit scene (labelled); demo dataset (synthetic) |

## Changed in Round 2
* **Backend:** inline two-TLE analysis (`tle_a`/`tle_b`), `POST /api/tle/validate`, `GET /api/analyses/{id}/export.json`, epoch difference and input summary in every record and report, dashboard aggregates all analyses and reports data mode, `.env` loader, `python -m ofde` entry point, relative-path database resolution.
* **Frontend:** cinematic redesign (local CSS/SVG/canvas only): hero, backend/SGP4/DEMO chips, TLE workspace with live validation, COMPUTED/DEMO labels, computed encounter-geometry plot, History page with exports, Method/limits/about, reduced-motion support, responsive layout, offline state.
* **Delivery:** `start_ofde.ps1`, `.vscode/`, `.env.example`, `.gitignore`, `API_REFERENCE.md`, `KNOWN_LIMITATIONS.md`, rewritten README, TEST_REPORT, PRESENTER_GUIDE. Removed stale `DEMO_SCRIPT.md`, `HACKATHON_PLAN.md`, `LIMITATIONS.md`.
* **Tests (Round 2 pass):** 131 to 149; later raised to 177 in the final completion pass (see below); no assertions weakened.

## Real versus illustrative
Real (computed by tested code): validation, TCA, miss distance, relative vector/speed (via SGP4 once installed), scenarios, Threat Transfer, FEI, sensitivity, history, exports. Illustrative: hero scene, offline example, demo dataset (synthetic). Unavailable: collision probability, Monte Carlo.

## Final completion pass (what was and was not achievable)
The brief asked to install dependencies and run real SGP4, FastAPI and the real end-to-end flow. The environment still has **no network** (DNS failure, no local copies of sgp4/fastapi/pytest), so those items remain **unverified**. What was done instead: fixed real defects found by code inspection (PowerShell native-stderr handling, missing report print/CSP, untested adapter/marker logic), added `tools/e2e_real_backend.py` (one command that performs the full real-backend verification on your machine and writes `e2e_results.json`) and the `-E2E` switch, added 28 tests (149 to 177: fake-module wiring, e2e-script logic, static delivery checks, report safety), and rewrote `TEST_REPORT.md` with an honest status table.

## Known limitations and unverified items
See `KNOWN_LIMITATIONS.md`. Headlines: SGP4, FastAPI, pytest, `start_ofde.ps1` and all Windows steps were **not executed** (no network or PowerShell in the build sandbox); pinned versions and SGP4 reference digits unverified; the demo pair's real SGP4 miss distance unknown until run.

## Contents (top level)
`ofde/`, `frontend/`, `tests/`, `tools/`, `data/`, `.vscode/`, `README.md`, `ARCHITECTURE.md`, `SCIENTIFIC_METHOD.md`, `API_REFERENCE.md`, `DATA_DICTIONARY.md`, `KNOWN_LIMITATIONS.md`, `TEST_REPORT.md`, `PRESENTER_GUIDE.md`, `TROUBLESHOOTING.md`, `DELIVERY_MANIFEST.md`, `requirements.txt`, `requirements-dev.txt`, `.env.example`, `.gitignore`, `start_ofde.ps1`.
Excluded: `.venv`, caches, `*.sqlite3`, `.env`, `data/sgp4_verification.json`, `node_modules` (not used).
