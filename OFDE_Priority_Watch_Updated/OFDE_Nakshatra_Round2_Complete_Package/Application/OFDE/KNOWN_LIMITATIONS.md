# Known limitations

## Verification
* The real SGP4 path, FastAPI server, pytest runner, `tools/e2e_real_backend.py` end to end, `start_ofde.ps1`, and the pinned versions were **not executed** in the build environment (no network, no PowerShell; re-checked in the final pass). Run `start_ofde.ps1 -E2E` and record the results in `TEST_REPORT.md`.
* 18 passing tests use *fake* `sgp4`/`fastapi` modules to test our own wiring; they are not evidence about the real libraries.
* `start_ofde.ps1` logic is checked only by static inspection tests; Windows PowerShell 5.1 and 7 behaviour is untested.
* `ofde/reference_cases.py` digits (Vallado SGP4-VER case 00005) were transcribed from memory and are **unverified**; a failure there should first prompt a comparison with the sgp4 package's own test data.
* The demo pair's close pass was phased with a two-body design aid; its real SGP4 miss distance is unknown until you run it (`tools/tune_demo_sgp4.py` re-phases it with SGP4).

## Scientific
* TLEs are fitted mean elements, not measurements; accuracy degrades with age. Warnings at more than 7 days from the window start and at more than 1 day between the two epochs are heuristics, not standards.
* No covariance: **no collision probability, no Monte Carlo, no uncertainty propagation**. Sweeps are hypothetical what-if experiments.
* The closest approach is the minimum inside the analysed window, not a proven global minimum; features narrower than the grid step could be missed.
* Dwell time assumes one contiguous dip around the TCA.
* Only SGP4/SDP4 effects; no manoeuvres. TEME frame only.
* Threat Transfer, FEI and Decision Sensitivity are project-defined, not standards; FEI parameters are conventions.

## Functional
* TLE/3LE text only (no CSV/OMM import, no live downloads).
* One pair per analysis; no catalogue screening.
* The hero orbit scene is illustrative. The encounter-geometry plot is computed.
* Each inline analysis creates a small stored "Workspace input" dataset (kept for provenance).
* No PDF generation: print the HTML report to PDF from the browser.
* Single local user; no authentication (intentionally out of scope).

## Not for operational use
Research and education prototype only.
