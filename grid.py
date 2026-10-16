"""Week grid layout: turns dated intervals into CSS grid row/column placements."""
from timeutil import fmt_time, overlaps

START_HOUR, END_HOUR = 7, 22


def _row(minute: int, up: bool) -> int:
    m = min(max(minute, START_HOUR * 60), END_HOUR * 60) - START_HOUR * 60
    r = (m + 29) // 30 if up else m // 30
    return 2 + r  # row 1 is the day header


def build_grid(days: list[str], items: list[dict]) -> dict:
    """items: {date,start,end,label,sublabel,kind,colour,href}; kind in band|block|unassigned|oncall."""
    col = {d: i + 2 for i, d in enumerate(days)}
    placed = []
    for it in items:
        if it["date"] not in col:
            continue
        r0, r1 = _row(it["start"], False), _row(it["end"], True)
        if r1 <= r0:
            r1 = r0 + 1
        placed.append({**it, "col": col[it["date"]], "r0": r0, "r1": r1, "lane": 0, "lanes": 1})
    blocks = [p for p in placed if p["kind"] in ("block", "unassigned")]
    for p in blocks:
        clash = [q for q in blocks if q is not p and q["date"] == p["date"] and overlaps(p["start"], p["end"], q["start"], q["end"])]
        if clash:
            used = {q["lane"] for q in clash if q.get("_done")}
            p["lane"] = 0 if 0 not in used else 1
            p["lanes"] = 2
            for q in clash:
                q["lanes"] = 2
        p["_done"] = True
    rows = [(2 + i, fmt_time(START_HOUR * 60 + i * 30) if i % 2 == 0 else "") for i in range((END_HOUR - START_HOUR) * 2)]
    return {"days": days, "items": placed, "rows": rows, "last_row": 2 + (END_HOUR - START_HOUR) * 2}
