"""Representable wheel-speed targets; preserve signs and zero wheels."""
# @(#)roomberry_wheel_speed.py 3.2.pulse.1 2026/11/12 16:09:50
from math import ceil, isfinite

MIN_WHEEL_SPEED = 42


def wheel_speeds(values):
    values = tuple(float(v) for v in values)
    if not all(isfinite(v) and abs(v) <= 500 for v in values):
        raise ValueError('Wheel speeds must be finite and within500mm/s')
    return tuple((1 if v > 0 else -1)*max(MIN_WHEEL_SPEED, ceil(abs(v)-1e-9)) if v else 0 for v in values)
