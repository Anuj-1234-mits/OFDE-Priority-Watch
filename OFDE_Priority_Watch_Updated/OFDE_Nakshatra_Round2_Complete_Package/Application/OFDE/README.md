# Orbital Future Decision Engine (OFDE)

*From one predicted future to a comparison of plausible outcomes.*

Team Fantastic 4: Anuj Singh (leader), Sarthak Gavnekar, Nitin Chherke, Chirag Lalwani. Nakshatra, Software track.

OFDE is a **research and education decision-support prototype**. It is **not** a certified collision-avoidance system and it **does not calculate collision probability**.

## What it does

Enter two TLEs, find the closest approach in a time window with real SGP4 propagation, compare what-if scenarios and sensitivity sweeps (every changed input is listed), and export JSON, CSV and a printable HTML report. Results are saved in SQLite and survive restarts.

## Read this first: verification status

The package was built and tested in a sandbox **without internet** (re-checked in the final completion pass), so `sgp4`, FastAPI and pytest could not be installed there. The real SGP4 path, the FastAPI server, `pytest`, the real-backend end-to-end check, and `start_ofde.ps1` were **never executed**. 177 tests pass there (9 skipped); 18 of them test our wiring with fake modules and are not SGP4/FastAPI evidence. Until you run the steps below on Windows, OFDE labels results *unverified*; if `sgp4` is missing it refuses to compute and never substitutes values. Details: `TEST_REPORT.md`, `DELIVERY_MANIFEST.md`.

## 1. Extract and open in VS Code

1. Right-click `OFDE_Nakshatra_Round2_Final.zip`, **Extract All...** to a short path such as `C:\Projects\`. This creates `C:\Projects\OFDE`.
2. Open VS Code, **File > Open Folder...**, choose the `OFDE` folder (the one containing `README.md`). Open a terminal with **Terminal > New Terminal** (PowerShell).
3. VS Code may suggest the free *Python* extension; accept it.

## 2. Check Python

```powershell
py -3 --version        # needs 3.10, 3.11 or 3.12.  If 'py' is unknown, try: python --version
```

Node.js is **not required**. The dashboard is a single HTML file served by the backend.

## 3. One-command start (recommended)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start_ofde.ps1
```

`-ExecutionPolicy Bypass` applies to this single process only; nothing system-wide changes. The script checks Python, creates `.venv`, installs dependencies, **runs the tests, verifies SGP4**, optionally runs the real-backend end-to-end check (`-E2E`), then starts the app and opens your browser. It stops at the first failure with a message. Useful switches: `-E2E` (also run `tools\e2e_real_backend.py`), `-SkipTests`, `-AllowUnverified` (continue if SGP4 verification fails; results stay labelled unverified), `-Port 8010`, `-NoBrowser`.

Open: **http://127.0.0.1:8000**. Stop with **Ctrl+C** in that terminal.

In VS Code you can also press **Ctrl+Shift+B** (default build task "OFDE: setup, test, verify and start") or use **Terminal > Run Task...**.

## 4. Manual steps (same result)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1          # blocked? run:  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
python -m pip install -r requirements-dev.txt
python -m pytest -v                    # expect 0 skipped once sgp4/fastapi/httpx are installed
python tools\verify_sgp4.py            # expect ALL CHECKS PASSED
python tools\e2e_real_backend.py       # real-backend workflow: analysis, restart persistence, exports, error paths
python -m ofde                         # starts FastAPI (or the stdlib server if FastAPI is missing)
```

You can skip activation entirely by calling `.\.venv\Scripts\python.exe` instead of `python`.

Optional config: copy `.env.example` to `.env` (host, port, database path). No `.env` is needed.

## 5. Demo in one minute

1. Open http://127.0.0.1:8000, click **Load synthetic demo pair** (hero button).
2. On **Analyze**, click **Add example scenarios and sweep**, then **Run analysis**.
3. Read the COMPUTED cards, the separation curve, scenario table, sensitivity charts; open **History** for exports.

Full talk track: `PRESENTER_GUIDE.md`.

## 6. Troubleshooting (short)

| Symptom | Fix |
|---|---|
| `.ps1 cannot be loaded because running scripts is disabled` | use the `-ExecutionPolicy Bypass -File` command above (process-scoped) |
| `py` / `python` not found | install Python 3.10-3.12 from python.org with "Add to PATH", reopen the terminal |
| `No matching distribution found for sgp4==...` | pins are unverified: `pip index versions sgp4`, edit `requirements.txt`, rerun |
| Port 8000 busy | `.\start_ofde.ps1 -Port 8010` and open that port |
| Dashboard says backend offline / CORS error | start the backend (`python -m ofde`); the page talks to `http://127.0.0.1:8000`; do not change host without updating the URL |
| "Propagation unavailable" | `sgp4` missing in the environment running the server: `pip install -r requirements.txt` |
| "SGP4 ... not verified" | `python tools\verify_sgp4.py`; on a large mismatch compare `ofde/reference_cases.py` digits with the sgp4 package's own tests |
| npm errors | not applicable: there is no npm step |

More: `TROUBLESHOOTING.md`.

## Project layout

```
ofde/        backend (tle, ingest, propagation, tca, scenarios, metrics, storage, report, service, servers, config)
frontend/    index.html (whole dashboard, no external assets)
tests/       177 tests (+ analytic test-only fixtures)
tools/       verify_sgp4.py, e2e_real_backend.py, tune_demo_sgp4.py, generate_demo.py, ui_smoke_test.py
data/        demo_synthetic.json (SYNTHETIC), DESIGN_NOTES.md
.vscode/     settings, tasks, launch configs
start_ofde.ps1, requirements*.txt, .env.example, .gitignore
```

Docs: `ARCHITECTURE.md`, `SCIENTIFIC_METHOD.md`, `API_REFERENCE.md`, `DATA_DICTIONARY.md`, `KNOWN_LIMITATIONS.md`, `TEST_REPORT.md`, `PRESENTER_GUIDE.md`, `DELIVERY_MANIFEST.md`, `TROUBLESHOOTING.md`.

## Sources and licences

`sgp4` Python package (Brandon Rhodes; built on Vallado et al.): licence believed MIT, confirm with `pip show sgp4`. TLE format: https://celestrak.org/NORAD/documentation/tle-fmt.php. The demo dataset is **synthetic** (fictitious objects, placeholder catalog numbers 90001-90004); it contains no real orbital data, so there is no source or retrieval date to cite.
