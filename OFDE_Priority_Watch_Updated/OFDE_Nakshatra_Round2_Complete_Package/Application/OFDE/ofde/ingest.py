"""Dataset import: parse TLE/3LE text into validated records, never silently repairing data."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .tle import parse_tle, Issue
from .timeutil import format_utc

VALID_ORIGINS = ("real", "synthetic", "manual")
UNITS_FRAME_ASSUMPTIONS = (
    "TLE mean elements (SGP4/SDP4 conventions): angles in degrees, mean motion in rev/day, B* in 1/earth-radii, "
    "epoch in UTC. Propagated output frame: TEME, km and km/s."
)
STALE_DAYS_WARNING = 7.0  # heuristic threshold, not a standard


class ImportErrorOFDE(ValueError):
    pass


def parse_tle_text(text: str) -> tuple[list[dict], list[dict]]:
    """Return (accepted_records, rejected_records). Handles 2-line and 3-line (name) sets."""
    accepted, rejected = [], []
    if not isinstance(text, str) or not text.strip():
        raise ImportErrorOFDE("Input is empty; paste TLE text or choose a file")
    lines = [(i + 1, ln.rstrip("\r\n")) for i, ln in enumerate(text.splitlines())]
    lines = [(n, ln) for n, ln in lines if ln.strip()]
    i = 0
    pending_name: Optional[str] = None
    while i < len(lines):
        n, ln = lines[i]
        if ln.startswith("1 ") and i + 1 < len(lines) and lines[i + 1][1].startswith("2 "):
            l1, l2 = ln, lines[i + 1][1]
            tle, issues = parse_tle(l1, l2, pending_name)
            rec = {"source_lines": [n, lines[i + 1][0]], "name": pending_name, "line1": l1, "line2": l2,
                   "issues": [x.to_dict() for x in issues]}
            if tle is None:
                rejected.append(rec)
            else:
                rec["tle"] = tle
                accepted.append(rec)
            pending_name = None
            i += 2
        elif ln.startswith("1 ") or ln.startswith("2 "):
            rejected.append({"source_lines": [n], "name": pending_name, "line1": ln, "line2": None,
                             "issues": [Issue("error", "UNPAIRED_LINE",
                                              f"Line {n} looks like a TLE line but is not followed/preceded by its partner line", n).to_dict()]})
            pending_name = None
            i += 1
        else:
            name = ln[2:].strip() if ln.startswith("0 ") else ln.strip()
            if pending_name is not None:
                rejected.append({"source_lines": [n - 1], "name": pending_name, "line1": None, "line2": None,
                                 "issues": [Issue("error", "NAME_WITHOUT_ELEMENTS",
                                                  f"Name line {pending_name!r} is not followed by TLE lines", n - 1).to_dict()]})
            pending_name = name
            i += 1
    if pending_name is not None:
        rejected.append({"source_lines": [lines[-1][0]], "name": pending_name, "line1": None, "line2": None,
                         "issues": [Issue("error", "NAME_WITHOUT_ELEMENTS", f"Name line {pending_name!r} is not followed by TLE lines").to_dict()]})
    return accepted, rejected


def build_dataset(text: str, *, filename: Optional[str], source_description: str, origin: str,
                  object_metadata: Optional[dict] = None, cases: Optional[list] = None,
                  name: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    """Validate text and build a dataset dict (JSON-serialisable). Original text is preserved verbatim."""
    if origin not in VALID_ORIGINS:
        raise ImportErrorOFDE(f"origin must be one of {VALID_ORIGINS}, got {origin!r}")
    if not source_description or not str(source_description).strip():
        raise ImportErrorOFDE("A source description is required for provenance")
    accepted, rejected = parse_tle_text(text)
    now = now or datetime.now(timezone.utc)
    meta = object_metadata or {}
    objects, seen = [], {}
    for rec in accepted:
        t = rec["tle"]
        oid = t.catalog_number
        issues = list(rec["issues"])
        if oid in seen:
            issues.append(Issue("warning", "DUPLICATE_CATALOG",
                                f"Catalog number {oid} appears more than once; later record kept as {oid}#{seen[oid] + 1}").to_dict())
            seen[oid] += 1
            oid = f"{oid}#{seen[oid]}"
        else:
            seen[oid] = 1
        m = meta.get(t.catalog_number, {})
        objects.append({
            "object_id": oid,
            "name": t.name or m.get("name") or None,           # None = unknown (not empty string / zero)
            "object_type": m.get("object_type"),               # None = unknown; TLEs do not carry object type
            "metadata": {k: v for k, v in m.items() if k not in ("name", "object_type")},
            "tle": t.to_dict(),
            "provenance": {"origin": origin, "source": source_description, "filename": filename,
                           "imported_utc": format_utc(now), "source_lines": rec["source_lines"]},
            "issues": issues,
        })
    rejected_out = [{k: v for k, v in r.items() if k != "tle"} for r in rejected]
    n_err = len(rejected_out)
    outcome = "rejected" if not objects else ("accepted_with_rejections" if n_err else "accepted")
    case_list = []
    ids = {o["object_id"] for o in objects}
    for c in (cases or []):
        if c.get("object_a") in ids and c.get("object_b") in ids and c["object_a"] != c["object_b"]:
            case_list.append(c)
    return {
        "name": name or filename or "Unnamed dataset",
        "filename": filename, "format": "TLE (2-line / 3-line)", "origin": origin,
        "source_description": source_description, "imported_utc": format_utc(now),
        "units_frame_assumptions": UNITS_FRAME_ASSUMPTIONS,
        "validation": {"outcome": outcome, "accepted": len(objects), "rejected": n_err,
                       "warnings": sum(1 for o in objects for i in o["issues"] if i["severity"] == "warning")},
        "objects": objects, "rejected": rejected_out, "cases": case_list,
        "original_text": text,   # preserved verbatim for reproducibility
    }
