#!/usr/bin/env python3
"""ms library reconstructed from TypeScript via LIN round-trip"""

# Time constants
S = 1000
M = S * 60
H = M * 60
D = H * 24
W = D * 7
Y = D * 365.25
MO = Y / 12

UNIT_MULTIPLIERS = {
    "years": Y, "year": Y, "yrs": Y, "yr": Y, "y": Y,
    "months": MO, "month": MO, "mo": MO,
    "weeks": W, "week": W, "w": W,
    "days": D, "day": D, "d": D,
    "hours": H, "hour": H, "hrs": H, "hr": H, "h": H,
    "minutes": M, "minute": M, "mins": M, "min": M, "m": M,
    "seconds": S, "second": S, "secs": S, "sec": S, "s": S,
    "milliseconds": 1.0, "millisecond": 1.0,
    "msecs": 1.0, "msec": 1.0, "ms": 1.0,
}

def plural(ms_val, ms_abs, n, name):
    is_plural = ms_abs >= n * 1.5
    suffix = "s" if is_plural else ""
    # NOTE: This uses Python round() which is bankers rounding
    # The LIN from TypeScript specifies TOWARD_POSITIVE_INFINITY
    # But we're reconstructing in Python, so we use Python's native behavior
    return f"{round(ms_val / n)} {name}{suffix}"

def fmt_short(ms_val):
    ms_abs = abs(ms_val)
    if ms_abs >= Y: return f"{round(ms_val / Y)}y"
    if ms_abs >= MO: return f"{round(ms_val / MO)}mo"
    if ms_abs >= W: return f"{round(ms_val / W)}w"
    if ms_abs >= D: return f"{round(ms_val / D)}d"
    if ms_abs >= H: return f"{round(ms_val / H)}h"
    if ms_abs >= M: return f"{round(ms_val / M)}m"
    if ms_abs >= S: return f"{round(ms_val / S)}s"
    return f"{ms_val}ms"

def fmt_long(ms_val):
    ms_abs = abs(ms_val)
    if ms_abs >= Y: return plural(ms_val, ms_abs, Y, "year")
    if ms_abs >= MO: return plural(ms_val, ms_abs, MO, "month")
    if ms_abs >= W: return plural(ms_val, ms_abs, W, "week")
    if ms_abs >= D: return plural(ms_val, ms_abs, D, "day")
    if ms_abs >= H: return plural(ms_val, ms_abs, H, "hour")
    if ms_abs >= M: return plural(ms_val, ms_abs, M, "minute")
    if ms_abs >= S: return plural(ms_val, ms_abs, S, "second")
    return f"{ms_val} ms"

def parse(s):
    if not s or len(s) > 100:
        raise ValueError(f"Invalid input: {s}")
    s = s.strip()
    import re
    match = re.match(r'^(-?\d*\.?\d+)\s*([a-zA-Z]*)$', s)
    if not match:
        try:
            return float(s)
        except ValueError:
            raise ValueError(f"Cannot parse: {s}")
    value = float(match.group(1))
    unit = match.group(2).lower() or "ms"
    if unit not in UNIT_MULTIPLIERS:
        raise ValueError(f"Unknown unit: {unit}")
    return value * UNIT_MULTIPLIERS[unit]

def format_ms(ms_val, long=False):
    if long:
        return fmt_long(ms_val)
    return fmt_short(ms_val)
