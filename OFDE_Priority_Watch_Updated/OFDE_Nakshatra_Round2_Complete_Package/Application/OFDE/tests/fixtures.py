"""TEST-ONLY propagators with closed-form answers. They are never reachable from the application
(only injected through OfdeService(propagator_factory=...) in tests) and are labelled category='test-fixture'."""
import math
from datetime import datetime

from ofde.propagation import Propagator, PropagationError
from ofde.timeutil import UTC

MU = 398600.4418


class LinearPropagator(Propagator):
    """r(t) = r0 + v * (t - t_ref). Static if v = 0."""
    name, version, category = "test-fixture linear", "0", "test-fixture"

    def __init__(self, r0, v, t_ref: datetime, fail_after_s=None):
        self.r0, self.v, self.t_ref, self.fail_after_s = r0, v, t_ref, fail_after_s

    def state_at(self, t):
        dt = (t - self.t_ref).total_seconds()
        if self.fail_after_s is not None and dt > self.fail_after_s:
            raise PropagationError("SGP4_ERROR", "fixture failure injected")
        return tuple(self.r0[i] + self.v[i] * dt for i in range(3)), tuple(self.v)


class CirclePropagator(Propagator):
    """Planar circular motion r*(cos(phi0+w t), sin(phi0+w t), 0) with t measured from t_ref."""
    name, version, category = "test-fixture circle", "0", "test-fixture"

    def __init__(self, radius_km, omega_rad_s, phi0_rad, t_ref: datetime):
        self.r, self.w, self.p0, self.t_ref = radius_km, omega_rad_s, phi0_rad, t_ref

    def state_at(self, t):
        dt = (t - self.t_ref).total_seconds()
        ph = self.p0 + self.w * dt
        return ((self.r * math.cos(ph), self.r * math.sin(ph), 0.0),
                (-self.r * self.w * math.sin(ph), self.r * self.w * math.cos(ph), 0.0))


def circle_from_tle(tle) -> CirclePropagator:
    """Fixture 'physics': circular orbit in the xy-plane from mean motion, mean anomaly + arg. of perigee.
    Inclination, RAAN, eccentricity and B* are ignored (so perturbing them has exactly zero effect)."""
    n_rad_s = tle.mean_motion_rev_per_day * 2 * math.pi / 86400.0
    radius = (MU / n_rad_s ** 2) ** (1.0 / 3.0)
    return CirclePropagator(radius, n_rad_s, math.radians(tle.mean_anomaly_deg + tle.arg_perigee_deg), tle.epoch)


def fixture_status():
    return {"available": True, "version": "fixture", "error": None,
            "verification": {"verified": False, "reason": "test fixture propagator"}}


def utc(y, mo, d, h=0, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC)
