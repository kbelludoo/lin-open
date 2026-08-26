"""ms_library.py - Python implementation of ms() duration conversion
Equivalent to vercel/ms TypeScript library
"""

import re
from typing import Union

# Time constants (milliseconds)
S = 1000
M = S * 60
H = M * 60
D = H * 24
W = D * 7
Y = D * 365.25
MO = Y / 12

# Regex pattern for parsing
PARSE_PATTERN = re.compile(
    r'^(?P<value>-?\d*\.?\d+) *(?P<unit>milliseconds?|msecs?|ms|seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w|months?|mo|years?|yrs?|y)?$',
    re.IGNORECASE
)

# Unit to milliseconds mapping
UNIT_MULTIPLIERS = {
    'years': Y, 'year': Y, 'yrs': Y, 'yr': Y, 'y': Y,
    'months': MO, 'month': MO, 'mo': MO,
    'weeks': W, 'week': W, 'w': W,
    'days': D, 'day': D, 'd': D,
    'hours': H, 'hour': H, 'hrs': H, 'hr': H, 'h': H,
    'minutes': M, 'minute': M, 'mins': M, 'min': M, 'm': M,
    'seconds': S, 'second': S, 'secs': S, 'sec': S, 's': S,
    'milliseconds': 1, 'millisecond': 1, 'msecs': 1, 'msec': 1, 'ms': 1,
}


def parse(s: str) -> float:
    """Parse a duration string and return milliseconds.
    
    Args:
        s: Duration string like '1m', '2h', '100ms', '1.5d'
        
    Returns:
        Duration in milliseconds
        
    Raises:
        ValueError: If string cannot be parsed
    """
    if not isinstance(s, str) or len(s) == 0 or len(s) > 100:
        raise ValueError(f"Value provided to ms.parse() must be a string with length between 1 and 99. value={s!r}")
    
    match = PARSE_PATTERN.match(s)
    if not match:
        return float('nan')
    
    value = float(match.group('value'))
    unit = (match.group('unit') or 'ms').lower()
    
    multiplier = UNIT_MULTIPLIERS.get(unit)
    if multiplier is None:
        raise ValueError(f'Unknown unit "{unit}" provided to ms.parse(). value={s!r}')
    
    return value * multiplier


def fmt_short(ms: float) -> str:
    """Format milliseconds to short string like '1m', '2h', '100ms'."""
    ms_abs = abs(ms)
    
    if ms_abs >= Y:
        return f"{round(ms / Y)}y"
    if ms_abs >= MO:
        return f"{round(ms / MO)}mo"
    if ms_abs >= W:
        return f"{round(ms / W)}w"
    if ms_abs >= D:
        return f"{round(ms / D)}d"
    if ms_abs >= H:
        return f"{round(ms / H)}h"
    if ms_abs >= M:
        return f"{round(ms / M)}m"
    if ms_abs >= S:
        return f"{round(ms / S)}s"
    return f"{ms}ms"


def fmt_long(ms: float) -> str:
    """Format milliseconds to long string like '1 minute', '2 hours'."""
    ms_abs = abs(ms)
    
    if ms_abs >= Y:
        return plural(ms, ms_abs, Y, 'year')
    if ms_abs >= MO:
        return plural(ms, ms_abs, MO, 'month')
    if ms_abs >= W:
        return plural(ms, ms_abs, W, 'week')
    if ms_abs >= D:
        return plural(ms, ms_abs, D, 'day')
    if ms_abs >= H:
        return plural(ms, ms_abs, H, 'hour')
    if ms_abs >= M:
        return plural(ms, ms_abs, M, 'minute')
    if ms_abs >= S:
        return plural(ms, ms_abs, S, 'second')
    return f"{ms} ms"


def plural(ms: float, ms_abs: float, n: float, name: str) -> str:
    """Pluralization helper."""
    is_plural = ms_abs >= n * 1.5
    suffix = 's' if is_plural else ''
    return f"{round(ms / n)} {name}{suffix}"


def format_ms(ms: float, long: bool = False) -> str:
    """Format milliseconds to string.
    
    Args:
        ms: Duration in milliseconds
        long: If True, use verbose format
        
    Returns:
        Formatted string
    """
    if not isinstance(ms, (int, float)) or not (ms == ms):  # ms == ms checks for NaN
        raise ValueError("Value provided to ms.format() must be of type number.")
    
    return fmt_long(ms) if long else fmt_short(ms)


def ms(value: Union[str, float], long: bool = False) -> Union[float, str]:
    """Parse or format a duration value.
    
    Args:
        value: String to parse or number to format
        long: If formatting, use verbose format
        
    Returns:
        Parsed milliseconds or formatted string
    """
    if isinstance(value, str):
        return parse(value)
    elif isinstance(value, (int, float)):
        return format_ms(value, long)
    else:
        raise ValueError(f"Value provided to ms() must be a string or number. value={value!r}")


# Export parse and format for compatibility
parse_str = parse
format_num = format_ms
