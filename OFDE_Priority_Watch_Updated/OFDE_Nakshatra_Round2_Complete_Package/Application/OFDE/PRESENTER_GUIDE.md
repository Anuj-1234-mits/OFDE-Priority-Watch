# Presenter guide

## 60-second pitch
"Today, a conjunction tool shows you one predicted close approach between two space objects. But that prediction depends on the input data and our assumptions. OFDE takes two TLEs, computes the closest approach with the standard SGP4 model, and then lets you change one assumption at a time and watch how the answer moves. Every scenario states exactly what changed, and the tool is strict about what is computed, what is synthetic, and what cannot be concluded. We do not claim a collision probability: TLEs have no covariance, so we say so. The idea is to move from one predicted future to a comparison of plausible outcomes."

## 3-minute demonstration
1. **Mission page (20 s).** Point to the chips: backend connected, SGP4 status, DEMO data. Say the orbit scene is illustrative.
2. **Load demo pair (15 s).** Click *Load synthetic demo pair*: two fictitious objects. Live validation shows epochs, inclination, period. (Optionally corrupt a digit: the error appears with the reason.)
3. **Run (30 s).** *Add example scenarios and sweep*, then *Run analysis*. Results are labelled COMPUTED.
4. **Read the result (45 s).** Miss distance and time of closest approach, relative speed, the separation curve zoomed on the valley, the encounter-geometry plot (computed from propagated states).
5. **Compare (45 s).** Scenario table: inputs changed, Threat Transfer, TCA shift, FEI rank. Sensitivity charts: how fragile is the answer.
6. **Honesty and export (25 s).** "What this result says and does not", then History: HTML report, CSV, JSON, saved in SQLite.

If anything shows "unverified", say so: verification runs on the demo laptop with `tools\verify_sgp4.py`.

## The problem
Close-approach predictions are treated as single numbers, but they depend on input age, element accuracy and modelling assumptions. Decision-makers need to see how conclusions change, not just one value.

## Why scenario comparison adds value
It shows which assumptions the result is sensitive to, with every changed input listed, and it avoids over-reading one number. It is a transparent what-if tool, **not** probabilistic uncertainty analysis (not implemented).

## Architecture in one breath
Single-file dashboard (HTML/JS/SVG, no external assets) talks to a Python backend: TLE validation, `sgp4` propagation, grid search plus golden-section refinement for the closest approach, scenario engine, metrics, SQLite history, HTML/CSV/JSON export. FastAPI if installed, standard-library server otherwise.

## What the calculation does
Both objects are propagated with SGP4 at identical UTC times in TEME (km, km/s). Separation is sampled every step, each dip is bracketed and refined to 1 ms, and the smallest is reported as the closest approach inside the window. It is flagged if it sits at the window edge.

## Implemented and verified vs not
| Feature | Status |
|---|---|
| TLE validation, UTC handling, TCA search, scenarios, metrics, SQLite, exports, API, UI flow | Implemented, **tested** in the build sandbox (177 tests, of which 18 are fake-module wiring tests; see `TEST_REPORT.md`) |
| Real SGP4 propagation | Implemented, **verify on your laptop** (`verify_sgp4.py`); say "verified" only if it passed |
| FastAPI server, `start_ofde.ps1`, Windows run | Implemented, **not yet run** by us |
| Monte Carlo, collision probability | **Not implemented** (and not claimed) |

## Honest answers to likely questions
* *Is this a collision probability?* No. Miss distance is not probability. TLEs have no covariance.
* *Is the demo real?* No: four fictitious objects, labelled DEMO. We tuned its phasing only so a close pass exists; it is not a prediction of any real event.
* *How do you know SGP4 is right?* We use the published library and check it on-machine against a reference case and consistency tests. Our search is validated against closed-form geometry. Reference digits were typed from memory and flagged as such.
* *What are Threat Transfer and FEI?* Our own definitions (formulas on the Method page), not standards. FEI only ranks scenarios against each other.
* *Sensitivity vs uncertainty?* Sensitivity changes an input by a chosen amount; uncertainty needs a covariance and a distribution. We do the first.
* *Why is the hero orbit scene there?* Illustrative only; the encounter plot is the computed one.
* *Why a 30 s step?* LEO periods are about 90 minutes; the refinement then locates the minimum to 1 ms. Halve the step to check.
* *How old can TLEs be?* We warn beyond 7 days and when the two epochs differ by more than 1 day (heuristics).

## Short, reliable demo sequence (about 3 minutes)
1. `start_ofde.ps1` (already run beforehand; app open at http://127.0.0.1:8000). Point at the chips: backend connected, SGP4 verified (only if it is), DEMO data.
2. Mission page, **Load synthetic demo pair**. Live validation turns green for both TLEs.
3. **Add example scenarios and sweep**, **Run analysis**. Read the COMPUTED cards: miss distance, TCA, relative speed.
4. Separation curve and encounter geometry; scenario table (Threat Transfer, FEI); sensitivity chart.
5. History: open the saved analysis, export HTML and CSV; mention it survives a restart.
6. Close with what is not claimed: no collision probability, no Monte Carlo, synthetic objects.

## Backup demo plan
1. SGP4/FastAPI install fails: `python -m ofde --stdlib` (no extra packages). If SGP4 itself is missing the app refuses to compute: show the tests, code, the Method page and the clearly labelled illustrative example, and say plainly that propagation was not run.
2. No internet at the venue: install beforehand; the app loads no external resources. Wheels can be cached: `pip download -r requirements.txt -d wheels`, then `pip install --no-index --find-links wheels -r requirements.txt`.
3. Odd state: History is in `ofde.sqlite3`; *Datasets > Reset demo data* clears it.
4. Keep screenshots of a good run on the laptop (take them once SGP4 is verified).

## Next steps beyond the prototype
Covariance-based analysis from CDM/ephemeris data, validated probability of collision, catalogue-wide screening, fresher data feeds, comparison against an independent conjunction tool, optional PDF reports.
