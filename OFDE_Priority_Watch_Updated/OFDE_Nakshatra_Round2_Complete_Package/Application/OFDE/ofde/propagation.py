"""Propagation interface and the SGP4 adapter.

OFDE does NOT implement SGP4 itself. It wraps the pinned `sgp4` package (Brandon Rhodes, based on
Vallado et al.). If the package is missing, propagation is *unavailable*; nothing is substituted.
Output frame of SGP4: TEME, positions in km, velocities in km/s.
"""
from __future__ import annotations

import json
import math
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from .timeutil import UTC
from .tle import Tle

FRAME = "TEME"
VERIFICATION_MARKER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sgp4_verification.json")

SGP4_ERRORS = {
    1: "mean eccentricity outside 0 <= e < 1",
    2: "mean motion less than 0.0",
    3: "perturbed eccentricity outside 0 <= e <= 1",
    4: "semi-latus rectum < 0",
    5: "epoch elements are sub-orbital",
    6: "satellite has decayed (altitude below Earth's surface)",
}


class PropagationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class PropagationUnavailable(PropagationError):
    def __init__(self, message: str):
        super().__init__("PROPAGATION_UNAVAILABLE", message)


class Propagator(ABC):
    name = "abstract"
    version = "n/a"
    frame = FRAME
    category = "computed"   # "computed" only for real propagators; tests may use other labels

    @abstractmethod
    def state_at(self, t: datetime) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """Return (position_km, velocity_km_s) in self.frame at UTC time t."""


def sgp4_status() -> dict:
    """Report whether the sgp4 package is importable, its version, and local verification status."""
    try:
        import sgp4  # noqa: F401
        from sgp4.api import Satrec  # noqa: F401
        try:
            from importlib.metadata import version
            ver = version("sgp4")
        except Exception:
            ver = getattr(sgp4, "__version__", "unknown")
        status = {"available": True, "version": ver, "error": None}
    except Exception as exc:  # ImportError or broken install
        status = {"available": False, "version": None, "error": f"{type(exc).__name__}: {exc}"}
    status["verification"] = read_verification_marker(status.get("version"))
    return status


def read_verification_marker(installed_version: Optional[str]) -> dict:
    """The marker is written only by tools/verify_sgp4.py after its checks pass on this machine."""
    if not os.path.exists(VERIFICATION_MARKER):
        return {"verified": False, "reason": "tools/verify_sgp4.py has not been run successfully on this machine"}
    try:
        with open(VERIFICATION_MARKER, "r", encoding="utf-8") as fh:
            m = json.load(fh)
    except Exception as exc:
        return {"verified": False, "reason": f"verification marker unreadable: {exc}"}
    if m.get("passed") is not True:
        return {"verified": False, "reason": "verification marker does not record a pass"}
    if installed_version and m.get("sgp4_version") != installed_version:
        return {"verified": False, "reason": f"marker is for sgp4 {m.get('sgp4_version')}, installed is {installed_version}; re-run verification"}
    return {"verified": True, "checked_utc": m.get("checked_utc"), "sgp4_version": m.get("sgp4_version"), "checks": m.get("checks")}


class Sgp4Propagator(Propagator):
    name = "SGP4 (sgp4 Python package, WGS-72 constants)"
    category = "computed"

    def __init__(self, tle: Tle):
        try:
            from sgp4.api import Satrec, WGS72
        except Exception as exc:
            raise PropagationUnavailable(
                "The 'sgp4' package is not installed or failed to import "
                f"({type(exc).__name__}: {exc}). Install with: pip install -r requirements.txt") from exc
        self._tle = tle
        try:
            self._sat = Satrec.twoline2rv(tle.line1, tle.line2, WGS72)
        except Exception as exc:
            raise PropagationError("TLE_REJECTED_BY_SGP4", f"sgp4 rejected the TLE for object {tle.catalog_number}: {exc}") from exc
        self.version = sgp4_status()["version"]

    def state_at(self, t: datetime):
        from sgp4.api import jday
        t = t.astimezone(UTC)
        jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1e6)
        err, r, v = self._sat.sgp4(jd, fr)
        if err != 0:
            raise PropagationError("SGP4_ERROR",
                                   f"SGP4 error {err} for object {self._tle.catalog_number} at {t.isoformat()}: {SGP4_ERRORS.get(err, 'unknown')}")
        if not all(math.isfinite(x) for x in (*r, *v)):
            raise PropagationError("NON_FINITE_STATE", f"Non-finite state for object {self._tle.catalog_number} at {t.isoformat()}")
        return tuple(r), tuple(v)


def default_propagator_factory(tle: Tle) -> Propagator:
    return Sgp4Propagator(tle)
