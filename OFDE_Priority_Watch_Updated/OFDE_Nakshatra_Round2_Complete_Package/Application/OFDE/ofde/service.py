"""Application service + framework-agnostic route table.

The same ROUTES and OfdeService.handle() are used by the FastAPI app (server_fastapi.py) and by the
stdlib fallback server (server_stdlib.py), so API behaviour is identical in both.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from . import __version__
from .ingest import build_dataset, parse_tle_text, ImportErrorOFDE
from .metrics import (DEFAULT_FEI_PARAMS, MetricError, fei_ranking, sensitivity_table, threat_transfer,
                      validate_fei_params)
from .propagation import PropagationError, PropagationUnavailable, default_propagator_factory, sgp4_status
from .report import report_html, scenarios_csv, sensitivity_csv
from .scenarios import PERTURBATION_SPECS, ScenarioError, run_scenario, validate_perturbations
from .storage import Storage, DEFAULT_DB
from .tca import AnalysisInputError
from .tle import parse_tle, Tle
from .timeutil import TimeParseError, format_utc, parse_utc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_PATH = os.path.join(ROOT, "data", "demo_synthetic.json")
FRONTEND_PATH = os.path.join(ROOT, "frontend", "index.html")
STALE_DAYS = 7.0

LIMITATIONS = [
    "TLE mean elements are not a perfect measurement of an object's true position; SGP4 accuracy degrades with TLE age.",
    "No state covariance is available from TLE input, so no uncertainty propagation, Monte Carlo analysis or collision probability is computed.",
    "Sensitivity experiments use hypothetical perturbations of TLE fields; they are not validated physical uncertainty estimates.",
    "The reported closest approach is the minimum within the analysed window, not a guaranteed global minimum.",
    "Threat Transfer, Future Exposure Index and Decision Sensitivity are project-defined metrics, not aerospace standards.",
    "Atmospheric density, manoeuvres, and unmodelled forces are not represented beyond what SGP4 and the TLE B* term capture.",
    "OFDE is a research and educational prototype and must not be used for operational collision-avoidance decisions.",
]


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass
class Route:
    method: str
    path: str       # FastAPI-style: /api/datasets/{dataset_id}
    handler: str
    name: str


ROUTES = [
    Route("GET", "/", "index", "index"),
    Route("GET", "/api/status", "status", "status"),
    Route("GET", "/api/datasets", "list_datasets", "list_datasets"),
    Route("POST", "/api/datasets/import", "import_dataset", "import_dataset"),
    Route("POST", "/api/datasets/demo", "load_demo", "load_demo"),
    Route("GET", "/api/datasets/{dataset_id}", "get_dataset", "get_dataset"),
    Route("POST", "/api/reset", "reset", "reset"),
    Route("GET", "/api/dashboard", "dashboard", "dashboard"),
    Route("GET", "/api/metrics/definitions", "metric_definitions", "metric_definitions"),
    Route("POST", "/api/analyses", "run_analysis", "run_analysis"),
    Route("GET", "/api/analyses", "list_analyses", "list_analyses"),
    Route("GET", "/api/priority-watch", "list_priority_watch", "list_priority_watch"),
    Route("POST", "/api/priority-watch", "create_priority_watch", "create_priority_watch"),
    Route("POST", "/api/priority-watch/{alert_id}/acknowledge", "acknowledge_priority_watch", "acknowledge_priority_watch"),
    Route("POST", "/api/priority-watch/{alert_id}/review", "review_priority_watch", "review_priority_watch"),
    Route("GET", "/api/analyses/{analysis_id}", "get_analysis", "get_analysis"),
    Route("GET", "/api/analyses/{analysis_id}/report.html", "report_html", "report_html"),
    Route("GET", "/api/analyses/{analysis_id}/report.csv", "report_csv", "report_csv"),
    Route("GET", "/api/analyses/{analysis_id}/sensitivity.csv", "sensitivity_csv", "sensitivity_csv"),
    Route("GET", "/api/analyses/{analysis_id}/export.json", "export_json", "export_json"),
    Route("POST", "/api/tle/validate", "validate_tle", "validate_tle"),
]


def _num(body: dict, key: str, default, lo=None, hi=None):
    v = body.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ServiceError(400, "INVALID_INPUT", f"{key} must be a finite number")
    if lo is not None and v < lo:
        raise ServiceError(400, "INVALID_INPUT", f"{key} must be >= {lo}")
    if hi is not None and v > hi:
        raise ServiceError(400, "INVALID_INPUT", f"{key} must be <= {hi}")
    return v


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha(obj) -> str:
    return hashlib.sha256(_canon(obj).encode()).hexdigest()


class OfdeService:
    def __init__(self, db_path: Optional[str] = None, propagator_factory: Callable = default_propagator_factory,
                 status_fn: Callable = sgp4_status, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.store = Storage(db_path or DEFAULT_DB)
        self.factory = propagator_factory
        self.status_fn = status_fn
        self.clock = clock

    # ---------------------------------------------------------------- transport
    def handle(self, route: Route, params: dict, query: dict, raw_body: Optional[bytes]):
        """Returns (status, content_type, body_bytes, extra_headers)."""
        try:
            body = None
            if route.method == "POST":
                if raw_body and raw_body.strip():
                    try:
                        body = json.loads(raw_body.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError) as exc:
                        raise ServiceError(400, "INVALID_JSON", f"Request body is not valid JSON: {exc}")
                    if not isinstance(body, dict):
                        raise ServiceError(400, "INVALID_JSON", "Request body must be a JSON object")
                else:
                    body = {}
            result = getattr(self, "h_" + route.handler)(params, query, body)
            if isinstance(result, tuple):
                ctype, data, headers = result
                return 200, ctype, data if isinstance(data, bytes) else data.encode("utf-8"), headers
            return 200, "application/json", json.dumps(result).encode("utf-8"), {}
        except ServiceError as e:
            return e.status, "application/json", json.dumps({"error": {"code": e.code, "message": e.message}}).encode(), {}
        except PropagationUnavailable as e:
            return 503, "application/json", json.dumps({"error": {"code": e.code, "message": e.message}}).encode(), {}
        except PropagationError as e:
            return 422, "application/json", json.dumps({"error": {"code": e.code, "message": e.message}}).encode(), {}
        except (AnalysisInputError, ScenarioError, MetricError, TimeParseError, ImportErrorOFDE) as e:
            return 400, "application/json", json.dumps({"error": {"code": type(e).__name__, "message": str(e)}}).encode(), {}
        except Exception as e:  # unexpected: do not leak internals, but do not hide the failure
            return 500, "application/json", json.dumps({"error": {"code": "INTERNAL_ERROR", "message": f"{type(e).__name__}: {e}"}}).encode(), {}

    # ---------------------------------------------------------------- handlers
    def h_index(self, p, q, b):
        try:
            with open(FRONTEND_PATH, "rb") as fh:
                return "text/html; charset=utf-8", fh.read(), {}
        except OSError:
            raise ServiceError(404, "NO_FRONTEND", "frontend/index.html not found")

    def h_status(self, p, q, b):
        st = self.status_fn()
        ds = self.store.list_datasets()
        return {"ofde_version": __version__, "python": platform.python_version(), "sgp4": st,
                "propagation_available": bool(st["available"]), "n_datasets": len(ds), "n_analyses": len(self.store.list_analyses()),
                "time_utc": format_utc(self.clock()),
                "notice": "Research/educational prototype. Not a certified collision-avoidance system."}

    def h_list_datasets(self, p, q, b):
        return {"datasets": self.store.list_datasets()}

    def h_get_dataset(self, p, q, b):
        ds = self._dataset(p["dataset_id"])
        ds = {k: v for k, v in ds.items() if k != "original_text"}
        return ds

    def _dataset(self, ds_id) -> dict:
        try:
            ds = self.store.get_dataset(int(ds_id))
        except (TypeError, ValueError):
            raise ServiceError(400, "INVALID_INPUT", "dataset_id must be an integer")
        if ds is None:
            raise ServiceError(404, "NOT_FOUND", f"Dataset {ds_id} not found")
        return ds

    def h_import_dataset(self, p, q, b):
        text = b.get("text")
        if not isinstance(text, str):
            raise ServiceError(400, "INVALID_INPUT", "'text' (TLE file contents) is required")
        origin = b.get("origin", "manual")
        ds = build_dataset(text, filename=b.get("filename"), source_description=b.get("source_description") or "",
                           origin=origin, name=b.get("name"), now=self.clock())
        if ds["validation"]["outcome"] == "rejected":
            raise ServiceError(422, "ALL_RECORDS_REJECTED", "No valid TLE records found: " + "; ".join(
                i["message"] for r in ds["rejected"] for i in r["issues"][:2])[:600])
        ds_id = self.store.add_dataset(format_utc(self.clock()), ds)
        ds["id"] = ds_id
        return {k: v for k, v in ds.items() if k != "original_text"}

    def h_load_demo(self, p, q, b):
        try:
            with open(DEMO_PATH, "r", encoding="utf-8") as fh:
                demo = json.load(fh)
        except OSError as exc:
            raise ServiceError(500, "DEMO_MISSING", f"Demo dataset file missing: {exc}")
        ds = build_dataset(demo["tle_text"], filename="demo_synthetic.json", source_description=demo["source_description"],
                           origin="synthetic", object_metadata=demo["objects"], cases=demo["cases"], name=demo["name"], now=self.clock())
        if ds["validation"]["outcome"] != "accepted":
            raise ServiceError(500, "DEMO_INVALID", "Bundled demo dataset failed validation; see data/ and run tests")
        ds_id = self.store.add_dataset(format_utc(self.clock()), ds)
        ds["id"] = ds_id
        return {k: v for k, v in ds.items() if k != "original_text"}

    def h_reset(self, p, q, b):
        self.store.reset()
        demo = self.h_load_demo(p, q, b) if (b or {}).get("reload_demo", True) else None
        return {"reset": True, "demo_dataset_id": demo["id"] if demo else None}

    def h_metric_definitions(self, p, q, b):
        return {
            "category": "project-defined metrics; not established aerospace standards",
            "threat_transfer": {"formula": "TT_km = d_baseline - d_alternative; TT_rel = TT_km / d_baseline; dTCA = t_alt - t_base",
                                "units": "km, dimensionless, s", "interpretation": "Positive TT_km: the alternative brings the objects closer than the baseline.",
                                "limitations": "Compares computed values only; both come from TLE-based propagation with no covariance."},
            "fei": {"formula": "FEI = 100*(w_d*c_d + w_t*c_t)/(w_d+w_t); c_d = d_ref/(d_ref+d); c_t = min(1, T/t_ref)",
                    "units": "dimensionless index 0-100", "default_params": DEFAULT_FEI_PARAMS,
                    "interpretation": "Higher means closer and longer inside radius R, relative to the other compared scenarios.",
                    "limitations": "Reference parameters are adjustable conventions. Not a probability or a universal risk score."},
            "decision_sensitivity": {"formula": "S_k = (y_k - y_0)/(p_k - p_0); plus least-squares slope over the sweep",
                                     "units": "km (or s) per unit of the perturbed parameter",
                                     "interpretation": "How strongly the output responds to a hypothetical input change.",
                                     "limitations": "Not an uncertainty estimate; ranges are user-chosen what-if values."},
            "limitations": LIMITATIONS,
            "perturbations": {k: {"unit": v[0], "description": v[1], "min": v[2], "max": v[3]} for k, v in PERTURBATION_SPECS.items()},
        }

    # ---------------------------------------------------------------- analysis
    def _tle_from_object(self, obj: dict) -> Tle:
        t, issues = parse_tle(obj["tle"]["line1"], obj["tle"]["line2"], obj.get("name"))
        if t is None:
            raise ServiceError(422, "STORED_TLE_INVALID", f"Stored TLE for {obj['object_id']} no longer validates")
        return t

    def _adhoc_dataset(self, b: dict) -> dict:
        """Create a stored two-object dataset from TLE text typed/pasted for objects A and B."""
        origin = b.get("origin", "manual")
        source = (b.get("source_description") or "").strip() or "Entered manually in the OFDE workspace (source not stated)"
        texts = {}
        for role in ("a", "b"):
            t = b.get("tle_" + role)
            if not isinstance(t, str) or not t.strip():
                raise ServiceError(400, "INVALID_INPUT", f"TLE for object {role.upper()} is required")
            accepted, rejected = parse_tle_text(t)
            if rejected or len(accepted) != 1:
                reasons = "; ".join(i["message"] for r in rejected for i in r["issues"][:2]) or \
                          f"expected exactly one TLE (found {len(accepted)})"
                raise ServiceError(422, "TLE_INVALID", f"Object {role.upper()}: {reasons}")
            texts[role] = t.strip()
        ds = build_dataset(texts["a"] + "\n" + texts["b"] + "\n", filename=None, source_description=source, origin=origin,
                           name="Workspace input", now=self.clock())
        na = ds["objects"][0]["name"] or ds["objects"][0]["object_id"]
        nb = ds["objects"][1]["name"] or ds["objects"][1]["object_id"]
        ds["name"] = f"Workspace input: {na} / {nb}"
        ds["id"] = self.store.add_dataset(format_utc(self.clock()), ds)
        return ds

    def h_validate_tle(self, p, q, b):
        """Validate TLE text without storing anything (used for live feedback in the UI)."""
        accepted, rejected = parse_tle_text(b.get("text") if isinstance(b.get("text"), str) else "")
        return {
            "valid": [{"name": r["tle"].name, "catalog_number": r["tle"].catalog_number, "epoch_utc": format_utc(r["tle"].epoch),
                       "inclination_deg": r["tle"].inclination_deg, "period_min": r["tle"].period_min,
                       "mean_motion_rev_per_day": r["tle"].mean_motion_rev_per_day,
                       "issues": r["issues"]} for r in accepted],
            "rejected": [{"name": r["name"], "source_lines": r["source_lines"], "issues": r["issues"]} for r in rejected],
        }

    def h_export_json(self, p, q, b):
        rec = self._analysis(p["analysis_id"])
        payload = {"ofde_export_version": 1, "exported_utc": format_utc(self.clock()), "analysis": rec}
        return "application/json", json.dumps(payload, indent=2), {"Content-Disposition": f'attachment; filename="ofde_analysis_{rec["id"]}.json"'}

    def h_run_analysis(self, p, q, b):
        if b.get("tle_a") is not None or b.get("tle_b") is not None:
            ds_new = self._adhoc_dataset(b)
            b = {**b, "dataset_id": ds_new["id"], "object_a": ds_new["objects"][0]["object_id"],
                 "object_b": ds_new["objects"][1]["object_id"]}
        ds = self._dataset(b.get("dataset_id"))
        objs = {o["object_id"]: o for o in ds["objects"]}
        ida, idb = b.get("object_a"), b.get("object_b")
        for oid in (ida, idb):
            if oid not in objs:
                raise ServiceError(400, "UNKNOWN_OBJECT", f"Object {oid!r} is not in dataset {ds['id']}")
        if ida == idb:
            raise ServiceError(400, "SAME_OBJECT", "Select two different objects")
        tle_a, tle_b = self._tle_from_object(objs[ida]), self._tle_from_object(objs[idb])
        start = parse_utc(b["start_utc"]) if b.get("start_utc") else max(tle_a.epoch, tle_b.epoch)
        duration = _num(b, "duration_s", 14400.0, 1e-6, 5 * 86400.0)
        step = _num(b, "step_s", 30.0, 0.01, 3600.0)
        tol = _num(b, "tol_s", 1e-3, 1e-6, 1.0)
        fei_params = validate_fei_params(b.get("fei"))
        alts = b.get("scenarios") or []
        if not isinstance(alts, list) or len(alts) > 12:
            raise ServiceError(400, "INVALID_INPUT", "'scenarios' must be a list of at most 12 alternatives")
        scen_defs = [{"id": "baseline", "name": "Baseline", "perturbations": validate_perturbations(None)}]
        for k, s in enumerate(alts, start=1):
            if not isinstance(s, dict):
                raise ServiceError(400, "INVALID_INPUT", "Each scenario must be an object")
            scen_defs.append({"id": f"alt{k}", "name": str(s.get("name") or f"Alternative {k}")[:80],
                              "perturbations": validate_perturbations(s.get("perturbations"))})
        sweeps = self._validate_sweeps(b.get("sensitivity") or [])
        request = {"dataset_id": ds["id"], "dataset_sha256": hashlib.sha256(ds["original_text"].encode()).hexdigest(),
                   "object_a": ida, "object_b": idb, "start_utc": format_utc(start), "duration_s": duration, "step_s": step,
                   "tol_s": tol, "scenarios": [{"name": s["name"], "perturbations": s["perturbations"]} for s in scen_defs[1:]],
                   "fei": fei_params, "sensitivity": sweeps}

        scenarios = []
        for sd in scen_defs:
            out = run_scenario(self.factory, tle_a, tle_b, start, duration, step, tol, sd["perturbations"], fei_params["radius_km"])
            out.update({"id": sd["id"], "name": sd["name"]})
            scenarios.append(out)
        base = scenarios[0]["result"]
        comparison = []
        for s in scenarios[1:]:
            diff = [{"object": t, **c} for t in ("a", "b") for c in s["changes"][t]]
            comparison.append({"id": s["id"], "name": s["name"], "inputs_changed": diff,
                               "threat_transfer": threat_transfer(base, s["result"])})
        fei = fei_ranking([{"id": s["id"], "name": s["name"], "miss_distance_km": s["result"]["miss_distance_km"],
                            "dwell_s": s["dwell"]["duration_s"] if s["dwell"] else None} for s in scenarios], fei_params)

        sensitivity = [self._run_sweep(sw, tle_a, tle_b, start, duration, step, tol) for sw in sweeps]

        warnings = []
        for role, t in (("A", tle_a), ("B", tle_b)):
            age = abs((start - t.epoch).total_seconds()) / 86400.0
            if age > STALE_DAYS:
                warnings.append(f"Object {role} TLE epoch is {age:.1f} days from the window start (> {STALE_DAYS:.0f} d heuristic): "
                                "propagation error grows with TLE age.")
            if t.is_deep_space:
                warnings.append(f"Object {role} is a deep-space orbit (period {t.period_min:.0f} min); SDP4 applies and results need extra care.")
        epoch_diff_s = (tle_b.epoch - tle_a.epoch).total_seconds()
        if abs(epoch_diff_s) > 86400.0:
            warnings.append(f"The two TLE epochs differ by {abs(epoch_diff_s) / 86400.0:.2f} days (> 1 d heuristic): the older element set is propagated further, so its error is larger.")
        if ds["origin"] == "synthetic":
            warnings.append("SYNTHETIC DEMONSTRATION DATA: results do not describe real objects or events.")
        for s in scenarios:
            for n in s["result"]["notes"]:
                warnings.append(f"[{s['name']}] {n}")
        ver = self.status_fn()
        if not ver["verification"].get("verified"):
            warnings.append("Propagation has not been verified on this machine (run tools/verify_sgp4.py). Treat results as unverified.")

        sw = {"ofde": __version__, "python": platform.python_version(), "sgp4_version": ver["version"],
              "sgp4_verification": ver["verification"]}
        ds_prov = {k: ds[k] for k in ("id", "name", "origin", "source_description", "filename", "format", "imported_utc",
                                      "units_frame_assumptions", "validation")}
        record = {
            "title": (b.get("title") or f"{ida} vs {idb} conjunction analysis")[:120],
            "created_utc": format_utc(self.clock()),
            "status": "computed", "dataset": ds_prov,
            "objects": {"a": objs[ida], "b": objs[idb]},
            "window": {"start_utc": format_utc(start), "duration_s": duration, "step_s": step, "tol_s": tol},
            "input_summary": {"epoch_a_utc": format_utc(tle_a.epoch), "epoch_b_utc": format_utc(tle_b.epoch),
                              "epoch_difference_s": epoch_diff_s,
                              "window_start_minus_epoch_a_days": (start - tle_a.epoch).total_seconds() / 86400.0,
                              "window_start_minus_epoch_b_days": (start - tle_b.epoch).total_seconds() / 86400.0},
            "scenarios": scenarios, "comparison": comparison, "fei": fei, "sensitivity": sensitivity,
            "warnings": warnings, "limitations": LIMITATIONS, "software": sw,
            "reproducibility": {"request": request, "request_sha256": _sha(request),
                                "result_sha256": _sha([[s["id"], s["result"], s["dwell"]] for s in scenarios])},
        }
        an_id = self.store.add_analysis(record["created_utc"], ds["id"], record["title"], record)
        record["id"] = an_id
        return record

    def _validate_sweeps(self, sweeps) -> list:
        if not isinstance(sweeps, list) or len(sweeps) > 4:
            raise ServiceError(400, "INVALID_INPUT", "'sensitivity' must be a list of at most 4 sweeps")
        out = []
        for sw in sweeps:
            tgt, par = sw.get("target"), sw.get("parameter")
            if tgt not in ("a", "b") or par not in PERTURBATION_SPECS:
                raise ServiceError(400, "INVALID_INPUT", f"Sweep needs target 'a'/'b' and parameter in {list(PERTURBATION_SPECS)}")
            base_val = 1.0 if par == "bstar_scale" else 0.0
            if "values" in sw:
                vals = sw["values"]
                if not isinstance(vals, list) or not (2 <= len(vals) <= 21):
                    raise ServiceError(400, "INVALID_INPUT", "Sweep 'values' must list 2 to 21 numbers")
            else:
                lo, hi, n = _num(sw, "min", None), _num(sw, "max", None), int(_num(sw, "n", 7, 2, 21))
                if hi <= lo:
                    raise ServiceError(400, "INVALID_INPUT", "Sweep max must exceed min")
                vals = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
            vals = [float(v) for v in vals]
            if not any(abs(v - base_val) < 1e-12 for v in vals):
                vals.append(base_val)
            vals = sorted(set(vals))
            for v in vals:
                validate_perturbations({tgt: {par: v}})
            out.append({"target": tgt, "parameter": par, "baseline_value": base_val, "values": vals})
        return out

    def _run_sweep(self, sw, tle_a, tle_b, start, duration, step, tol) -> dict:
        unit = PERTURBATION_SPECS[sw["parameter"]][0]
        miss_pts, tca_pts, errors = [], [], []
        for v in sw["values"]:
            try:
                if abs(v - sw["baseline_value"]) < 1e-12:
                    perts = {}
                else:
                    perts = {sw["target"]: {sw["parameter"]: v}}
                out = run_scenario(self.factory, tle_a, tle_b, start, duration, step, tol, perts)
                miss_pts.append({"p": v, "y": out["result"]["miss_distance_km"]})
                tca_pts.append({"p": v, "y": out["result"]["tca_offset_s"]})
            except (PropagationError, ScenarioError, AnalysisInputError) as exc:
                miss_pts.append({"p": v, "y": None})
                tca_pts.append({"p": v, "y": None})
                errors.append({"value": v, "error": str(exc)})
        return {"target": sw["target"], "parameter": sw["parameter"], "unit": unit,
                "miss_table": sensitivity_table(sw["parameter"], unit, sw["baseline_value"], miss_pts, "miss_distance", "km"),
                "tca_table": sensitivity_table(sw["parameter"], unit, sw["baseline_value"], tca_pts, "tca_offset", "s"),
                "errors": errors}

    def _analysis(self, an_id) -> dict:
        try:
            rec = self.store.get_analysis(int(an_id))
        except (TypeError, ValueError):
            raise ServiceError(400, "INVALID_INPUT", "analysis_id must be an integer")
        if rec is None:
            raise ServiceError(404, "NOT_FOUND", f"Analysis {an_id} not found")
        return rec

    def h_list_priority_watch(self, p, q, b):
        return {"alerts": self.store.list_priority_alerts(),
                "notice": "Priority labels are review workflow labels, not collision probabilities or certified risk estimates."}

    def h_create_priority_watch(self, p, q, b):
        priority = b.get("priority", "needs_attention")
        if priority not in ("critical", "needs_attention"):
            raise ServiceError(400, "INVALID_INPUT", "priority must be 'critical' or 'needs_attention'")
        reason = b.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ServiceError(400, "INVALID_INPUT", "A clear alert reason is required")
        if len(reason.strip()) > 1000:
            raise ServiceError(400, "INVALID_INPUT", "reason must be 1000 characters or fewer")
        label = b.get("restricted_label", "none")
        if label not in ("none", "restricted", "sensitive", "classified", "unknown"):
            raise ServiceError(400, "INVALID_INPUT", "restricted_label must be none, restricted, sensitive, classified, or unknown")
        analysis_id = b.get("analysis_id")
        if analysis_id in (None, ""):
            analysis_id = None
        else:
            try:
                analysis_id = int(analysis_id)
            except (TypeError, ValueError):
                raise ServiceError(400, "INVALID_INPUT", "analysis_id must be an integer")
            if self.store.get_analysis(analysis_id) is None:
                raise ServiceError(404, "NOT_FOUND", f"Analysis {analysis_id} not found")
        now = format_utc(self.clock())
        alert_id = self.store.add_priority_alert(now, analysis_id, priority, reason.strip(), label)
        return {"alert": self.store.get_priority_alert(alert_id),
                "notice": "Priority labels are review workflow labels, not collision probabilities or certified risk estimates."}

    def _update_priority_watch(self, alert_id, status):
        try:
            alert_id = int(alert_id)
        except (TypeError, ValueError):
            raise ServiceError(400, "INVALID_INPUT", "alert_id must be an integer")
        if self.store.get_priority_alert(alert_id) is None:
            raise ServiceError(404, "NOT_FOUND", f"Priority Watch alert {alert_id} not found")
        self.store.update_priority_alert(alert_id, status, format_utc(self.clock()))
        return {"alert": self.store.get_priority_alert(alert_id)}

    def h_acknowledge_priority_watch(self, p, q, b):
        alert = self.store.get_priority_alert(int(p["alert_id"])) if str(p.get("alert_id", "")).isdigit() else None
        if alert is None:
            raise ServiceError(404 if str(p.get("alert_id", "")).isdigit() else 400, "NOT_FOUND", "Priority Watch alert not found or invalid id")
        if alert["status"] == "reviewed_resolved":
            raise ServiceError(409, "ALREADY_RESOLVED", "A reviewed/resolved alert cannot be acknowledged again")
        return self._update_priority_watch(p["alert_id"], "acknowledged")

    def h_review_priority_watch(self, p, q, b):
        return self._update_priority_watch(p["alert_id"], "reviewed_resolved")

    def h_get_analysis(self, p, q, b):
        return self._analysis(p["analysis_id"])

    def h_list_analyses(self, p, q, b):
        ds_id = int(q["dataset_id"]) if q.get("dataset_id") else None
        return {"analyses": [self._summary(a) for a in self.store.list_analyses(ds_id)]}

    @staticmethod
    def _summary(a: dict) -> dict:
        rec = a["record"]
        base = rec["scenarios"][0]["result"]
        return {"id": a["id"], "created_utc": a["created_utc"], "dataset_id": a["dataset_id"], "title": a["title"],
                "object_a": rec["objects"]["a"]["object_id"], "object_b": rec["objects"]["b"]["object_id"],
                "n_scenarios": len(rec["scenarios"]), "baseline_miss_km": base["miss_distance_km"],
                "baseline_tca_utc": base["tca_utc"], "origin": rec["dataset"]["origin"]}

    def h_report_html(self, p, q, b):
        rec = self._analysis(p["analysis_id"])
        return "text/html; charset=utf-8", report_html(rec), {"Content-Disposition": f'attachment; filename="ofde_report_{rec["id"]}.html"'}

    def h_report_csv(self, p, q, b):
        rec = self._analysis(p["analysis_id"])
        return "text/csv; charset=utf-8", scenarios_csv(rec), {"Content-Disposition": f'attachment; filename="ofde_scenarios_{rec["id"]}.csv"'}

    def h_sensitivity_csv(self, p, q, b):
        rec = self._analysis(p["analysis_id"])
        return "text/csv; charset=utf-8", sensitivity_csv(rec), {"Content-Disposition": f'attachment; filename="ofde_sensitivity_{rec["id"]}.csv"'}

    # ---------------------------------------------------------------- dashboard
    def h_dashboard(self, p, q, b):
        """Totals and history aggregate ALL stored analyses; cases/objects/data quality describe the active dataset."""
        ds_id = q.get("dataset_id")
        datasets = self.store.list_datasets()
        if ds_id in (None, ""):
            ds_id = datasets[-1]["id"] if datasets else None
        active = self._dataset(ds_id) if ds_id is not None else None
        analyses = self.store.list_analyses(None)
        total_scen = sum(len(a["record"]["scenarios"]) for a in analyses)
        sel = None
        if q.get("analysis_id"):
            sel = next((a for a in analyses if a["id"] == int(q["analysis_id"])), None)
        elif analyses:
            sel = analyses[0]
        closest = None
        if sel:
            rec = sel["record"]
            s = min(rec["scenarios"], key=lambda x: x["result"]["miss_distance_km"])
            closest = {"analysis_id": sel["id"], "scenario": s["name"], "miss_distance_km": s["result"]["miss_distance_km"],
                       "tca_utc": s["result"]["tca_utc"], "object_a": rec["objects"]["a"]["object_id"],
                       "object_b": rec["objects"]["b"]["object_id"], "bracketed": s["result"]["bracketed"]}
        quality = None
        if active:
            n_issue_warn = sum(1 for o in active["objects"] for i in o["issues"] if i["severity"] == "warning")
            quality = {"origin": active["origin"], "source_description": active["source_description"],
                       "imported_utc": active["imported_utc"], "format": active["format"],
                       "outcome": active["validation"]["outcome"], "accepted": active["validation"]["accepted"],
                       "rejected": active["validation"]["rejected"], "warnings": n_issue_warn,
                       "object_types_unknown": sum(1 for o in active["objects"] if o["object_type"] is None)}
        mode_origin = sel["record"]["dataset"]["origin"] if sel else (active["origin"] if active else None)
        return {
            "active_dataset": None if not active else {"id": active["id"], "name": active["name"], "origin": active["origin"]},
            "mode_origin": mode_origin, "demo_mode": mode_origin == "synthetic",
            "total_analyses": len(analyses), "total_scenarios": total_scen,
            "cases_in_dataset": len(active["cases"]) if active else 0,
            "objects_in_dataset": len(active["objects"]) if active else 0,
            "closest_approach": closest, "selected_analysis_id": sel["id"] if sel else None,
            "scenario_summary": None if not sel else [
                {"name": s["name"], "miss_distance_km": s["result"]["miss_distance_km"]} for s in sel["record"]["scenarios"]],
            "data_quality": quality,
            "recent": [self._summary(a) for a in analyses[:8]],
        }
