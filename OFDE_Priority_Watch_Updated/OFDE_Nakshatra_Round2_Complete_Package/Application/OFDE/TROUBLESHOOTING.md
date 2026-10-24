# Troubleshooting

| Problem | Fix |
|---|---|
| `.\.venv\Scripts\Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate again |
| `py` not found | Install Python 3.10 to 3.12 from python.org (tick "Add to PATH"), or use `python` |
| `No matching distribution found for sgp4==2.23` (or fastapi/uvicorn/pytest/httpx pin) | The pins were not verified. Run `pip index versions sgp4`, edit the pin in `requirements.txt`, reinstall, re-run tests and `tools\verify_sgp4.py` |
| `sgp4` build errors on Windows | Use a recent Python with wheels available; `python -m pip install --upgrade pip` first |
| Dashboard: "Backend not reachable" | Start `powershell -ExecutionPolicy Bypass -File .\start_ofde.ps1` or `python -m ofde` from the project folder, then **Retry connection**. Opening `frontend/index.html` directly also works if the backend runs on port 8000 |
| Dashboard: "Propagation unavailable" | `sgp4` is not installed in the environment running the backend (activate the venv). API returns 503 `PROPAGATION_UNAVAILABLE`; nothing is faked |
| "SGP4 present but not verified" | Run `python tools\verify_sgp4.py`. If a check fails by a large amount, compare `ofde/reference_cases.py` with the sgp4 package's own tests before suspecting the library |
| `verify_sgp4.py` fails reference case | The reference digits were typed from memory. Compare to `sgp4/tests.py` data; correct the digits if wrong |
| Port 8000 busy | Use `--port 8010` and open that port |
| `ModuleNotFoundError: ofde` | Run commands from the project root (the folder containing `ofde\`) |
| `Address already in use` / stale server | Close the old PowerShell window or `Get-Process python \| Stop-Process` |
| Analysis says minimum at window edge | Extend duration or move the start; the pass is outside the window |
| Window start error | Use ISO 8601 with Z, for example `2026-10-24T00:00:00Z` |
| TLE import rejected | Read the listed reason (length 69, checksum, catalog mismatch). OFDE never repairs data; fix the source text |
| Odd database state | Press **Reset demo data**, or stop the server and delete `ofde.sqlite3` |
| Report downloads instead of opening | By design (attachment). Open the saved HTML in a browser; print to PDF from there |
| Tests skipped | Skips mean a dependency is missing (`sgp4`, `fastapi`, `httpx`). Install `requirements-dev.txt` and re-run: expect no skips |

| `e2e_real_backend.py` reports `[FAIL] real sgp4 package available` | `sgp4` is not installed in the environment used: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` |
| `e2e_real_backend.py` prints `[WARN] demo pair has no meaningful close pass` | The synthetic pair's SGP4 pass is outside the window or far: `python tools\tune_demo_sgp4.py --write`, then `python tools\verify_sgp4.py`. This is synthetic data, never a real prediction |
| `python` opens the Microsoft Store | Turn off the python.exe App execution alias (Settings > Apps > Advanced app settings > App execution aliases) or use `py -3` after installing from python.org |
| `start_ofde.ps1` stops with FAIL | Read the message: it names the step (Python, venv, pip, tests, SGP4 verification, port). Fix that step and rerun; `-AllowUnverified` / `-SkipTests` exist but are not recommended |
| `Set-ExecutionPolicy` prompt | Use the per-process form only: `powershell -NoProfile -ExecutionPolicy Bypass -File .\start_ofde.ps1`; never change the machine-wide policy |
