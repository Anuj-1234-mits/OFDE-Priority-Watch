"""Reference cases for validating the SGP4 integration.

IMPORTANT PROVENANCE NOTE: These values are the widely published SGP4 verification case for satellite 00005
(Vallado et al., "Revisiting Spacetrack Report #3", SGP4-VER test set, tcppver.out). They were transcribed
from memory by the OFDE author-assistant in a sandbox WITHOUT network access, so they could not be
cross-checked here. If the check below fails by a large amount, first compare these digits with the sgp4
package's own test data (sgp4/tests.py) or the Vallado SGP4-VER files before suspecting the library.
Frame: TEME. Units: km, km/s. tsince in minutes from the TLE epoch.
"""
CASE_00005_LINE1 = "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753"
CASE_00005_LINE2 = "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667"
CASE_00005_STATES = [
    # tsince_min, (x, y, z) km, (vx, vy, vz) km/s
    (0.0, (7022.46529266, -1400.08296755, 0.03995155), (1.893841015, 6.405893759, 4.534807250)),
    (360.0, (-7154.03120202, -3783.17682504, -3536.19412294), (4.741887409, -4.151817765, -2.093935425)),
]
POSITION_TOL_KM = 1e-4
VELOCITY_TOL_KM_S = 1e-6

# Published ISS sample TLE used for self-consistency checks (format reference from public documentation).
ISS_LINE1 = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
ISS_LINE2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"
