"""Time and date helpers. Times are minutes since midnight, dates are ISO strings."""

import re
from datetime import date, datetime, timedelta

_TIME_RE = re.compile(r"^(\d{1,2})[:.](\d{2})$")
_DATE_RES = (
    (re.compile(r"^(\d{4})[-.](\d{1,2})[-.](\d{1,2})\.?$"), ("y", "m", "d")),
    (re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})\.?$"), ("d", "m", "y")),
)
_SLASH_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def parse_time(s: str) -> int:
    text = str(s).strip()
    m = _TIME_RE.match(text)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if h < 24 and mi < 60:
            return h * 60 + mi
    raise ValueError(f"Time '{s}' should look like 09:00")


def fmt_time(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def parse_date(s) -> str:
    if isinstance(s, datetime):
        return s.date().isoformat()
    if isinstance(s, date):
        return s.isoformat()
    text = str(s).strip()
    parts = None
    for rx, order in _DATE_RES:
        m = rx.match(text)
        if m:
            parts = dict(zip(order, (int(g) for g in m.groups())))
            break
    if parts is None:
        m = _SLASH_RE.match(text)
        if m:
            a, b, y = (int(g) for g in m.groups())
            # Ambiguous slashes: only read as M/D/Y when the first part cannot be a month.
            if a > 12:
                parts = {"d": a, "m": b, "y": y}
            elif b > 12:
                parts = {"m": a, "d": b, "y": y}
            else:
                parts = {"d": a, "m": b, "y": y}
    if parts is None:
        raise ValueError(f"Date '{s}' should look like 2026-10-20")
    try:
        return date(parts["y"], parts["m"], parts["d"]).isoformat()
    except ValueError:
        raise ValueError(f"Date '{s}' should look like 2026-10-20") from None


def fmt_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"


def fmt_date_long(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B')} {d.year}"


def week_monday(iso: str) -> str:
    d = date.fromisoformat(iso)
    return (d - timedelta(days=d.weekday())).isoformat()


def week_days(monday_iso: str) -> list[str]:
    d = date.fromisoformat(monday_iso)
    return [(d + timedelta(days=i)).isoformat() for i in range(7)]


def shift_week(monday_iso: str, n: int) -> str:
    return (date.fromisoformat(monday_iso) + timedelta(weeks=n)).isoformat()


def overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def hours(start: int, end: int) -> float:
    return (end - start) / 60
