"""Explicit unit conversions. All internal orbital distances are km, speeds km/s, time in s or UTC."""
import math

KM_PER_M = 1e-3
SECONDS_PER_DAY = 86400.0
TWO_PI = 2.0 * math.pi


def m_to_km(m: float) -> float:
    return m * KM_PER_M


def km_to_m(km: float) -> float:
    return km / KM_PER_M


def deg_to_rad(d: float) -> float:
    return math.radians(d)


def rad_to_deg(r: float) -> float:
    return math.degrees(r)


def rev_per_day_to_rad_per_s(n: float) -> float:
    return n * TWO_PI / SECONDS_PER_DAY


def rev_per_day_to_period_min(n: float) -> float:
    if n <= 0:
        raise ValueError("mean motion must be positive")
    return 1440.0 / n
