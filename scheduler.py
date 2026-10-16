"""Automatic group-to-host scheduling.

Pure functions, no database access. Times are minutes since midnight,
dates are ISO strings (see ``timeutil``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from timeutil import fmt_date, fmt_time, hours, overlaps

WEIGHTS = {"fair": 20.0, "near": 3.0, "near_lookahead": 1.5, "far": 2.0, "on_call": 5.0}
ON_CALL_CAPACITY_HOURS = 8.0
MAX_CONCURRENT = 2
NEAR_MINUTES = 240


@dataclass(frozen=True)
class Slot:
    user_id: int
    date: str
    start: int
    end: int
    on_call: bool = False


@dataclass(frozen=True)
class Group:
    id: int
    date: str
    start: int
    end: int
    name: str = ""


@dataclass
class Assignment:
    group_id: int
    user_id: int | None
    reason: str
    locked: bool = False


@dataclass
class Result:
    assignments: list[Assignment] = field(default_factory=list)
    stats: dict[int, dict] = field(default_factory=dict)

    @property
    def unassigned(self) -> list[Assignment]:
        return [a for a in self.assignments if a.user_id is None]

    @property
    def load_spread(self) -> float:
        loads = [s["load"] for s in self.stats.values() if s["capacity_hours"] > 0]
        if not loads:
            return 0.0
        return max(loads) - min(loads)


# --------------------------------------------------------------------------- #
# Basic predicates
# --------------------------------------------------------------------------- #

def can_cover(slot: Slot, g: Group) -> bool:
    """True when the slot is on the group's date and fully contains it."""
    return slot.date == g.date and slot.start <= g.start and slot.end >= g.end


def _max_concurrency(assigned: list[Group], g: Group) -> int:
    """Max number of groups (from ``assigned`` + ``g``) running at once during ``g``."""
    pool = [x for x in assigned if x.id != g.id and x.date == g.date
            and overlaps(x.start, x.end, g.start, g.end)] + [g]
    instants = {g.start} | {x.start for x in pool if g.start <= x.start < g.end}
    best = 0
    for t in instants:
        n = sum(1 for x in pool if x.start <= t < x.end)
        best = max(best, n)
    return best


def concurrency_ok(assigned: list[Group], g: Group, cap: int = MAX_CONCURRENT) -> bool:
    """True when adding ``g`` keeps the host at or under ``cap`` simultaneous groups."""
    return _max_concurrency(assigned, g) <= cap


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #

def _capacities(slots: list[Slot]) -> dict[int, float]:
    caps: dict[int, float] = {}
    for s in slots:
        add = ON_CALL_CAPACITY_HOURS if s.on_call else hours(s.start, s.end)
        caps[s.user_id] = caps.get(s.user_id, 0.0) + add
    return caps


def compute_stats(groups: list[Group], slots: list[Slot], assignments: dict[int, int]) -> dict[int, dict]:
    """Per-user workload summary.

    ``assignments`` maps group_id -> user_id. Every user who has any slot is
    included, even with zero groups; users who appear only in ``assignments``
    are included too (with zero capacity).
    """
    caps = _capacities(slots)
    by_id = {g.id: g for g in groups}
    stats: dict[int, dict] = {}
    for uid in sorted(set(caps) | set(assignments.values())):
        stats[uid] = {"groups": 0, "hours": 0.0, "capacity_hours": caps.get(uid, 0.0), "load": 0.0}
    for gid, uid in assignments.items():
        g = by_id.get(gid)
        if g is None or uid is None:
            continue
        st = stats[uid]
        st["groups"] += 1
        st["hours"] += hours(g.start, g.end)
    for st in stats.values():
        st["load"] = st["hours"] / st["capacity_hours"] if st["capacity_hours"] > 0 else 0.0
    return stats


# --------------------------------------------------------------------------- #
# Scheduling
# --------------------------------------------------------------------------- #

def schedule(groups: list[Group], slots: list[Slot], locked: dict[int, int] | None = None,
             *, last_minute: bool = False) -> Result:
    locked = dict(locked or {})
    caps = _capacities(slots)

    # user_id -> list of slots, user_id -> date -> list of assigned groups
    user_slots: dict[int, list[Slot]] = {}
    for s in slots:
        user_slots.setdefault(s.user_id, []).append(s)

    assigned_groups: dict[int, dict[str, list[Group]]] = {}
    hours_assigned: dict[int, float] = {}
    count_assigned: dict[int, int] = {}

    def _record(uid: int, g: Group) -> None:
        assigned_groups.setdefault(uid, {}).setdefault(g.date, []).append(g)
        hours_assigned[uid] = hours_assigned.get(uid, 0.0) + hours(g.start, g.end)
        count_assigned[uid] = count_assigned.get(uid, 0) + 1

    result_by_gid: dict[int, Assignment] = {}
    by_id = {g.id: g for g in groups}

    # 1. Pre-load locked assignments.
    for gid, uid in locked.items():
        g = by_id.get(gid)
        if g is None:
            continue
        _record(uid, g)
        result_by_gid[gid] = Assignment(gid, uid, "Set by manager", locked=True)

    ordered = sorted(groups, key=lambda g: (g.date, g.start, g.end, g.id))
    pending: set[int] = {g.id for g in ordered if g.id not in result_by_gid}

    # 2. Process groups in chronological order.
    for g in ordered:
        if g.id in result_by_gid:
            continue
        pending.discard(g.id)
        g_hours = hours(g.start, g.end)

        available: list[int] = []
        candidates: list[tuple[tuple[float, int, int], int, dict]] = []
        for uid, uslots in user_slots.items():
            covering = [s for s in uslots if can_cover(s, g)]
            if not covering:
                continue
            available.append(uid)
            same_day = assigned_groups.get(uid, {}).get(g.date, [])
            if not concurrency_ok(same_day, g):
                continue

            cap = caps.get(uid, 0.0)
            done = hours_assigned.get(uid, 0.0)
            if cap > 0:
                score = WEIGHTS["fair"] * (done + g_hours) / cap
            else:
                score = float("inf")

            only_on_call = all(s.on_call for s in covering)
            if only_on_call:
                score += -WEIGHTS["on_call"] if last_minute else WEIGHTS["on_call"]

            near_groups = [x for x in same_day if abs(x.start - g.start) < NEAR_MINUTES]
            far_groups = [x for x in same_day if abs(x.start - g.start) > NEAR_MINUTES]
            score -= WEIGHTS["near"] * len(near_groups)
            score += WEIGHTS["far"] * len(far_groups)

            lookahead = 0
            for oid in pending:
                o = by_id[oid]
                if o.date == g.date and abs(o.start - g.start) < NEAR_MINUTES \
                        and any(can_cover(s, o) for s in uslots):
                    lookahead += 1
            score -= WEIGHTS["near_lookahead"] * lookahead

            key = (score, count_assigned.get(uid, 0), uid)
            candidates.append((key, uid, {
                "near": near_groups, "on_call": only_on_call,
                "hours_after": done + g_hours, "capacity": cap,
            }))

        if not candidates:
            if available:
                reason = f"Everyone available already hosts {MAX_CONCURRENT} groups at this time."
            else:
                reason = (f"No one is available {fmt_time(g.start)}–{fmt_time(g.end)} "
                          f"on {fmt_date(g.date)}.")
            result_by_gid[g.id] = Assignment(g.id, None, reason)
            continue

        candidates.sort(key=lambda c: c[0])
        _, uid, info = candidates[0]
        reason = (f"Lowest workload: {info['hours_after']:.1f} h of "
                  f"{info['capacity']:.1f} h available.")
        if info["near"]:
            nearest = min(info["near"], key=lambda x: (abs(x.start - g.start), x.start))
            reason += f" Also hosts the {fmt_time(nearest.start)} group (under 4 h apart)."
        if info["on_call"]:
            reason += " On-call that day."
        _record(uid, g)
        result_by_gid[g.id] = Assignment(g.id, uid, reason)

    assignments = [result_by_gid[g.id] for g in groups]
    assign_map = {a.group_id: a.user_id for a in assignments if a.user_id is not None}
    return Result(assignments=assignments, stats=compute_stats(groups, slots, assign_map))


# --------------------------------------------------------------------------- #
# Manual override checks
# --------------------------------------------------------------------------- #

def check_assignment(g: Group, user_slots: list[Slot], user_groups: list[Group], *,
                     name: str = "This host") -> list[str]:
    """Warnings for manually assigning ``g`` to a host; ``[]`` when clean."""
    warnings: list[str] = []
    if not any(can_cover(s, g) for s in user_slots):
        warnings.append(f"{name} is not available {fmt_time(g.start)}–{fmt_time(g.end)} "
                        f"on {fmt_date(g.date)}.")
    others = [x for x in user_groups if x.id != g.id and x.date == g.date]
    n = _max_concurrency(others, g)
    if n > MAX_CONCURRENT:
        warnings.append(f"{name} would host {n} groups at the same time (limit is {MAX_CONCURRENT}).")
    return warnings
