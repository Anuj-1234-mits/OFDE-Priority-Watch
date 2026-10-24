"""TLE parsing, strict validation (length, line numbers, checksums, ranges), and safe modification.

Nothing is silently repaired. The only normalisation is removal of trailing whitespace/newlines,
which is reported as a warning. Original text is always retained by the caller.
Reference format: https://celestrak.org/NORAD/documentation/tle-fmt.php
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .timeutil import tle_epoch_to_datetime, format_utc


@dataclass
class Issue:
    severity: str  # "error" | "warning" | "info"
    code: str
    message: str
    line: Optional[int] = None

    def to_dict(self):
        return {"severity": self.severity, "code": self.code, "message": self.message, "line": self.line}


@dataclass
class Tle:
    name: Optional[str]
    line1: str
    line2: str
    catalog_number: str
    classification: str
    intl_designator: str
    epoch: datetime
    ndot: float            # rev/day^2 (as given in TLE: first derivative of mean motion / 2)
    nddot: float           # rev/day^3 (second derivative / 6)
    bstar: float           # 1/earth-radii
    ephemeris_type: str
    element_set: str
    inclination_deg: float
    raan_deg: float
    eccentricity: float
    arg_perigee_deg: float
    mean_anomaly_deg: float
    mean_motion_rev_per_day: float
    rev_number: str
    issues: list = field(default_factory=list)

    @property
    def period_min(self) -> float:
        return 1440.0 / self.mean_motion_rev_per_day

    @property
    def is_deep_space(self) -> bool:
        return self.period_min >= 225.0

    def to_dict(self):
        return {
            "name": self.name, "line1": self.line1, "line2": self.line2,
            "catalog_number": self.catalog_number, "classification": self.classification,
            "intl_designator": self.intl_designator, "epoch_utc": format_utc(self.epoch),
            "ndot_rev_per_day2": self.ndot, "nddot_rev_per_day3": self.nddot, "bstar_per_earth_radius": self.bstar,
            "ephemeris_type": self.ephemeris_type, "element_set": self.element_set,
            "inclination_deg": self.inclination_deg, "raan_deg": self.raan_deg,
            "eccentricity": self.eccentricity, "arg_perigee_deg": self.arg_perigee_deg,
            "mean_anomaly_deg": self.mean_anomaly_deg, "mean_motion_rev_per_day": self.mean_motion_rev_per_day,
            "period_min": self.period_min, "rev_number": self.rev_number, "deep_space": self.is_deep_space,
        }


def checksum(line: str) -> int:
    """Modulo-10 checksum over the first 68 characters: digits count as their value, '-' as 1."""
    total = 0
    for ch in line[:68]:
        if ch.isdigit():
            total += int(ch)
        elif ch == "-":
            total += 1
    return total % 10


_EXP_RE = re.compile(r"^([+-]?)(\d{5})([+-]\d)$")


def parse_implied_exp(field_text: str) -> float:
    """Parse TLE 'implied decimal point, exponent' fields such as ' 28098-4' -> 0.28098e-4."""
    s = field_text.strip()
    m = _EXP_RE.match(s)
    if not m:
        raise ValueError(f"bad exponent field {field_text!r}")
    sign = -1.0 if m.group(1) == "-" else 1.0
    return sign * int(m.group(2)) * 1e-5 * 10.0 ** int(m.group(3))


def format_implied_exp(value: float) -> str:
    """Format as the 8-character TLE exponent field (sign, 5 digits, exponent sign+digit)."""
    if value == 0:
        return " 00000+0"
    sign = "-" if value < 0 else " "
    mag = abs(value)
    exp = 0
    while mag >= 1.0:
        mag /= 10.0
        exp += 1
    while mag < 0.1:
        mag *= 10.0
        exp -= 1
    digits = round(mag * 1e5)
    if digits >= 100000:
        digits = 10000
        exp += 1
    if not (-9 <= exp <= 9):
        raise ValueError(f"value {value} cannot be represented in TLE exponent field")
    return f"{sign}{digits:05d}{'-' if exp < 0 else '+'}{abs(exp)}"


def _fnum(text: str, name: str, line: int, issues: list) -> Optional[float]:
    try:
        v = float(text)
        if v != v or v in (float("inf"), float("-inf")):
            raise ValueError
        return v
    except ValueError:
        issues.append(Issue("error", "BAD_NUMBER", f"Field {name} {text!r} is not a valid number", line))
        return None


def parse_tle(line1: str, line2: str, name: Optional[str] = None) -> tuple[Optional[Tle], list]:
    """Validate and parse a TLE. Returns (Tle or None, issues). Tle is None if any error exists."""
    issues: list[Issue] = []
    lines = []
    for i, ln in enumerate([line1, line2], start=1):
        stripped = ln.rstrip("\r\n")
        if stripped != stripped.rstrip():
            issues.append(Issue("warning", "TRAILING_WHITESPACE_REMOVED",
                                f"Line {i} had trailing whitespace; removed for parsing (original retained)", i))
            stripped = stripped.rstrip()
        lines.append(stripped)
    l1, l2 = lines
    for i, ln in enumerate(lines, start=1):
        if len(ln) != 69:
            issues.append(Issue("error", "BAD_LENGTH", f"Line {i} has {len(ln)} characters; a TLE line must have exactly 69", i))
        if not ln.startswith(f"{i} "):
            issues.append(Issue("error", "BAD_LINE_NUMBER", f"Line {i} must start with '{i} '", i))
    if any(x.severity == "error" for x in issues):
        return None, issues
    for i, ln in enumerate(lines, start=1):
        if not ln[68].isdigit():
            issues.append(Issue("error", "BAD_CHECKSUM_CHAR", f"Line {i} checksum character {ln[68]!r} is not a digit", i))
        elif int(ln[68]) != checksum(ln):
            issues.append(Issue("error", "CHECKSUM_MISMATCH",
                                f"Line {i} checksum is {ln[68]} but computed checksum is {checksum(ln)}", i))
    cat1, cat2 = l1[2:7], l2[2:7]
    if cat1 != cat2:
        issues.append(Issue("error", "CATALOG_MISMATCH", f"Catalog numbers differ between lines ({cat1!r} vs {cat2!r})"))
    if any(x.severity == "error" for x in issues):
        return None, issues

    try:
        yy = int(l1[18:20])
        day = float(l1[20:32])
        epoch = tle_epoch_to_datetime(yy, day)
    except ValueError as exc:
        issues.append(Issue("error", "BAD_EPOCH", f"Invalid epoch: {exc}", 1))
        return None, issues
    ndot = _fnum(l1[33:43], "ndot", 1, issues)
    try:
        nddot = parse_implied_exp(l1[44:52])
        bstar = parse_implied_exp(l1[53:61])
    except ValueError as exc:
        issues.append(Issue("error", "BAD_EXP_FIELD", str(exc), 1))
        nddot = bstar = None
    inc = _fnum(l2[8:16], "inclination", 2, issues)
    raan = _fnum(l2[17:25], "RAAN", 2, issues)
    ecc_txt = l2[26:33]
    if ecc_txt.isdigit():
        ecc = float("0." + ecc_txt)
    else:
        ecc = None
        issues.append(Issue("error", "BAD_ECC", f"Eccentricity field {ecc_txt!r} must be 7 digits", 2))
    argp = _fnum(l2[34:42], "argument of perigee", 2, issues)
    ma = _fnum(l2[43:51], "mean anomaly", 2, issues)
    n = _fnum(l2[52:63], "mean motion", 2, issues)
    if any(x.severity == "error" for x in issues):
        return None, issues

    def rng(val, lo, hi, nm, hi_incl=False):
        ok = lo <= val <= hi if hi_incl else lo <= val < hi
        if not ok:
            issues.append(Issue("error", "OUT_OF_RANGE", f"{nm} = {val} outside [{lo}, {hi}{']' if hi_incl else ')'}", 2))

    rng(inc, 0.0, 180.0, "inclination (deg)", True)
    rng(raan, 0.0, 360.0, "RAAN (deg)")
    rng(argp, 0.0, 360.0, "argument of perigee (deg)")
    rng(ma, 0.0, 360.0, "mean anomaly (deg)")
    if n <= 0:
        issues.append(Issue("error", "OUT_OF_RANGE", f"mean motion = {n} rev/day must be positive", 2))
    if any(x.severity == "error" for x in issues):
        return None, issues

    cls = l1[7]
    if cls not in "USC":
        issues.append(Issue("warning", "ODD_CLASSIFICATION", f"Classification {cls!r} is not U, C or S", 1))
    if l1[62] != "0":
        issues.append(Issue("warning", "EPHEMERIS_TYPE", f"Ephemeris type {l1[62]!r} is not 0 (SGP4/SDP4 expect 0)", 1))
    tle = Tle(name=name.strip() if name else None, line1=l1, line2=l2, catalog_number=cat1.strip(), classification=cls,
              intl_designator=l1[9:17].strip(), epoch=epoch, ndot=ndot, nddot=nddot, bstar=bstar,
              ephemeris_type=l1[62], element_set=l1[64:68].strip(), inclination_deg=inc, raan_deg=raan,
              eccentricity=ecc, arg_perigee_deg=argp, mean_anomaly_deg=ma, mean_motion_rev_per_day=n,
              rev_number=l2[63:68].strip())
    if tle.is_deep_space:
        issues.append(Issue("info", "DEEP_SPACE", f"Period {tle.period_min:.0f} min >= 225 min: deep-space (SDP4) model applies"))
    tle.issues = issues
    return tle, issues


def with_checksum(line_without_checksum: str) -> str:
    base = line_without_checksum[:68].ljust(68)
    return base + str(checksum(base))


def format_tle(*, catalog: int, intl_designator: str, epoch: datetime, ndot: float, nddot: float, bstar: float,
               element_set: int, inclination_deg: float, raan_deg: float, eccentricity: float,
               arg_perigee_deg: float, mean_anomaly_deg: float, mean_motion_rev_per_day: float,
               rev_number: int, classification: str = "U") -> tuple[str, str]:
    """Build a syntactically valid TLE (with correct checksums) from elements.
    Used only to create *synthetic* demo data."""
    from .timeutil import datetime_to_tle_epoch
    yy, day = datetime_to_tle_epoch(epoch)
    ndot_txt = f"{abs(ndot):.8f}".lstrip("0")
    ndot_txt = ("-" if ndot < 0 else " ") + ndot_txt
    l1 = (f"1 {catalog:05d}{classification} {intl_designator:<8s} {yy:02d}{day:012.8f} {ndot_txt:>10s} "
          f"{format_implied_exp(nddot)} {format_implied_exp(bstar)} 0 {element_set:4d}")
    ecc7 = f"{round(eccentricity * 1e7):07d}"
    l2 = (f"2 {catalog:05d} {inclination_deg:8.4f} {raan_deg:8.4f} {ecc7} {arg_perigee_deg:8.4f} "
          f"{mean_anomaly_deg:8.4f} {mean_motion_rev_per_day:11.8f}{rev_number:5d}")
    return with_checksum(l1), with_checksum(l2)
