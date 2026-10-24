# Test report (final completion pass)

All results below were produced in the build sandbox (Python 3.12.3, Linux). **This environment has no network** (DNS fails; `pip download sgp4` was retried in this pass and failed again), no `sgp4`, `fastapi`, `uvicorn`, `httpx`, `pytest`, and no PowerShell. **Nothing was run on Windows.** Therefore the critical items the project still lacks are *not* verified and are listed as "not run" below. They are not claimed.

## Headline

| Critical check | Status |
|---|---|
| Real SGP4 propagation / `tools/verify_sgp4.py` / reference cases | **NOT RUN** (package not installable here) |
| FastAPI app and `tests/test_fastapi_app.py` | **NOT RUN** (skipped: fastapi/httpx not installable here) |
| Dependency installation and pin compatibility | **NOT RUN** (no network) |
| Real-backend end-to-end (`tools/e2e_real_backend.py`) | **Partly run**: harness runs; with no sgp4 it correctly **FAILS** at "real sgp4 package available". Full workflow only exercised against the test fixture |
| `start_ofde.ps1` / Windows / VS Code | **NOT RUN** (static checks only) |
| Everything else (validation, UTC, TCA search, scenarios, metrics, persistence, exports, reports, API, UI flow) | Run and passing against the analytic test fixture |

## Command and result

```
python3 -W error::ResourceWarning -m unittest discover -s tests -t . -v
python3 -m compileall -q ofde tools tests
```
**Ran 177 tests: OK, skipped=9** (168 passed, 0 failed, 9 skipped). `compileall`: OK.

Passing tests fall in three groups; do not conflate them:

| Group | Tests | What it proves |
|---|---|---|
| A. Real code against analytic fixtures (no external library) | 149 | Logic of validation, TCA search (closed-form cases), scenarios, metrics, SQLite, exports, reports, API, e2e-script logic incl. server restart on same DB |
| B. **Fake-module wiring tests** (`test_sgp4_adapter_wiring_fake`, `test_fastapi_wiring_fake`) | 18 | Our adapter/wrapper code: arguments passed to sgp4, all SGP4 error codes mapped, non-finite states rejected, marker lifecycle, `verify_sgp4.py` pass/fail/exit codes, FastAPI route registration and request-to-response flow. **NOT evidence about the real sgp4 or FastAPI** |
| C. Requires real packages | 10 total, **9 skipped**, 1 passed | `test_sgp4_required` (6 skipped, 1 "clear error when missing" passed), `test_fastapi_app` (3 skipped) |

| Module | Tests | Result |
|---|---|---|
| test_tle | 18 | pass |
| test_timeutil_units | 12 | pass |
| test_ingest | 14 | pass |
| test_tca | 20 | pass |
| test_metrics | 15 | pass |
| test_scenarios | 13 | pass |
| test_service_workflow | 22 | pass (now also asserts report print CSS and CSP, no `<script`) |
| test_server_stdlib | 6 | pass |
| test_round2_features | 17 | pass |
| test_tune_demo | 2 | pass |
| test_e2e_script | 3 | pass (full check list incl. restart persistence; a lossy backend is detected as FAIL; real-SGP4 expectation fails loudly when sgp4 is absent) |
| test_sgp4_adapter_wiring_fake | 14 | pass (fake module) |
| test_fastapi_wiring_fake | 4 | pass (fake module) |
| test_delivery_files | 7 | pass (static code inspection of the PowerShell script, VS Code configs, README, gitignore) |
| test_sgp4_required | 7 | 1 pass, **6 skipped** |
| test_fastapi_app | 3 | **3 skipped** |

## Other checks run this pass
* The frontend was not modified in this pass. The earlier `node --check` and Playwright/Chromium walkthrough (fixture propagator, not SGP4) therefore still describe it; they were not re-run.
* `python -m ofde --stdlib` started as a real subprocess by `tools/e2e_real_backend.py`; page and status endpoints answered; the harness stopped it and confirmed it became unreachable; exit code 1 with the sgp4 failure above.

## Defects found and fixed in this pass
1. PowerShell: with `$ErrorActionPreference = "Stop"`, Windows PowerShell 5.1 can abort on native-command stderr (pip/uvicorn warnings). All native calls now go through `Invoke-Native` (relaxed preference, returns the exit code, every non-zero code reaches a `Fail`/exit 1 branch). Also a clearer message for the Microsoft Store `python` stub. *Not executed on Windows.*
2. HTML reports had no print stylesheet and no content-security policy; both added (regression assertions in `test_service_workflow`).
3. `verify_sgp4.py` pass/fail/marker logic, the SGP4 error mapping and the version-mismatch invalidation of the verification marker were untested; now covered by wiring tests.
4. No automated check existed for the real-backend workflow; `tools/e2e_real_backend.py` added (and `-E2E` switch in `start_ofde.ps1`).
No assertions were weakened. Two of my own new tests failed on first run because of test miscounts (7 vs 8 native calls; a regex anchored to line start); the tests were corrected, the script was not changed to fit them.

## SGP4 reference values
`ofde/reference_cases.py` (Vallado SGP4-VER case 00005 at t = 0 and 360 min) was typed from memory and is **still unverified** against the sgp4 package's own test data. If `verify_sgp4.py` reports a large difference, first compare those digits with the package's tests (`sgp4/tests.py` data) before suspecting the library or the adapter. Do not edit the expected values only to make a check pass.

## Run on your laptop (in this order), then fill in the table
```powershell
cd C:\Projects\OFDE
powershell -NoProfile -ExecutionPolicy Bypass -File .\start_ofde.ps1 -E2E -NoBrowser
```
This installs dependencies, runs `pytest` (expect **0 skipped**), runs `tools\verify_sgp4.py`, runs `tools\e2e_real_backend.py` on FastAPI and the stdlib server (with a server restart), then starts the app. Optional browser check once the app is running: `python tools\ui_smoke_test.py` (needs `pip install playwright` and `playwright install chromium`).

| Date | Command | Passed / failed / skipped | Notes |
|---|---|---|---|
| | `pytest -v` | | |
| | `tools\verify_sgp4.py` | | |
| | `tools\e2e_real_backend.py` (fastapi, stdlib) | | |
| | `tools\ui_smoke_test.py` | | |
