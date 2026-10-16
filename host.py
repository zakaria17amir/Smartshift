from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from auth import current_user, require_role
from db import get_db
from grid import build_grid
from timeutil import fmt_date, fmt_time, hours, overlaps, parse_date, parse_time, shift_week, week_days, week_monday

bp = Blueprint("host", __name__, url_prefix="/me")


def week_param() -> str:
    w = request.args.get("week") or request.form.get("week")
    try:
        return week_monday(parse_date(w)) if w else week_monday(date.today().isoformat())
    except ValueError:
        return week_monday(date.today().isoformat())


def week_ctx(monday: str) -> dict:
    return {"monday": monday, "days": week_days(monday), "prev": shift_week(monday, -1), "next": shift_week(monday, 1),
            "title": f"Week of {fmt_date(monday)[4:]} {monday[:4]}"}


def my_groups(uid: int, monday: str):
    days = week_days(monday)
    return get_db().execute(
        "select g.*, a.source from groups g join assignments a on a.group_id = g.id "
        "where a.user_id = ? and g.date between ? and ? order by g.date, g.start_min", (uid, days[0], days[-1])).fetchall()


def my_slots(uid: int, monday: str):
    days = week_days(monday)
    return get_db().execute("select * from availability where user_id = ? and date between ? and ? order by date, start_min",
                            (uid, days[0], days[-1])).fetchall()


def grid_items(groups, slots):
    items = [{"date": s["date"], "start": s["start_min"], "end": s["end_min"], "kind": "oncall" if s["on_call"] else "band"} for s in slots]
    items += [{"date": g["date"], "start": g["start_min"], "end": g["end_min"], "label": g["name"], "sublabel": "", "kind": "block",
               "colour": current_user()["id"] % 6, "href": None} for g in groups]
    return items


@bp.get("")
@require_role("host")
def index():
    uid = current_user()["id"]
    monday = week_param()
    groups = my_groups(uid, monday)
    slots = my_slots(uid, monday)
    logged = {r[0] for r in get_db().execute("select group_id from work_logs where user_id = ? and group_id is not null", (uid,))}
    today = date.today().isoformat()
    by_day = {}
    for g in groups:
        by_day.setdefault(g["date"], []).append(g)
    return render_template("host/week.html", active="week", w=week_ctx(monday), grid=build_grid(week_days(monday), grid_items(groups, slots)),
                           by_day=by_day, logged=logged, today=today, hours=hours)


@bp.get("/availability")
@require_role("host")
def availability():
    uid = current_user()["id"]
    monday = week_param()
    slots = my_slots(uid, monday)
    by_day = {d: [s for s in slots if s["date"] == d] for d in week_days(monday)}
    return render_template("host/availability.html", active="availability", w=week_ctx(monday),
                           grid=build_grid(week_days(monday), grid_items(my_groups(uid, monday), slots)), by_day=by_day)


def _validated_interval(uid: int, day: str, start_s: str, end_s: str, ignore_id: int | None = None):
    start, end = parse_time(start_s), parse_time(end_s)
    if end <= start:
        raise ValueError(f"End time {fmt_time(end)} is not after start time {fmt_time(start)}.")
    for s in get_db().execute("select * from availability where user_id = ? and date = ? and on_call = 0", (uid, day)):
        if s["id"] != ignore_id and overlaps(start, end, s["start_min"], s["end_min"]):
            raise ValueError(f"You're already available {fmt_time(s['start_min'])}–{fmt_time(s['end_min'])} that day. Edit that entry instead.")
    return start, end


@bp.post("/availability")
@require_role("host")
def add_availability():
    uid = current_user()["id"]
    try:
        day = parse_date(request.form.get("date", ""))
        start, end = _validated_interval(uid, day, request.form.get("start", ""), request.form.get("end", ""))
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("host.availability", week=week_param()))
    db = get_db()
    db.execute("insert into availability(user_id, date, start_min, end_min) values (?,?,?,?)", (uid, day, start, end))
    db.commit()
    flash(f"Added availability {fmt_date(day)} {fmt_time(start)}–{fmt_time(end)}.", "ok")
    return redirect(url_for("host.availability", week=week_monday(day)))


def _own_slot(slot_id: int):
    s = get_db().execute("select * from availability where id = ?", (slot_id,)).fetchone()
    if s is None:
        abort(404)
    if s["user_id"] != current_user()["id"]:
        abort(403)
    return s


@bp.post("/availability/<int:slot_id>")
@require_role("host")
def edit_availability(slot_id: int):
    s = _own_slot(slot_id)
    try:
        start, end = _validated_interval(s["user_id"], s["date"], request.form.get("start", ""), request.form.get("end", ""), ignore_id=slot_id)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("host.availability", week=week_monday(s["date"])))
    db = get_db()
    db.execute("update availability set start_min = ?, end_min = ? where id = ?", (start, end, slot_id))
    db.commit()
    flash(f"Updated availability {fmt_date(s['date'])} {fmt_time(start)}–{fmt_time(end)}.", "ok")
    return redirect(url_for("host.availability", week=week_monday(s["date"])))


@bp.post("/availability/<int:slot_id>/delete")
@require_role("host")
def delete_availability(slot_id: int):
    s = _own_slot(slot_id)
    db = get_db()
    db.execute("delete from availability where id = ?", (slot_id,))
    db.commit()
    flash(f"Removed availability {fmt_date(s['date'])} {fmt_time(s['start_min'])}–{fmt_time(s['end_min'])}.", "ok")
    return redirect(url_for("host.availability", week=week_monday(s["date"])))


@bp.post("/on-call")
@require_role("host")
def on_call():
    uid = current_user()["id"]
    day = parse_date(request.form["date"])
    db = get_db()
    db.execute("delete from availability where user_id = ? and date = ? and on_call = 1", (uid, day))
    if request.form.get("on") == "1":
        db.execute("insert into availability(user_id, date, start_min, end_min, on_call) values (?,?,0,1440,1)", (uid, day))
        flash(f"You're on call on {fmt_date(day)}.", "ok")
    else:
        flash(f"You're no longer on call on {fmt_date(day)}.", "ok")
    db.commit()
    return redirect(url_for("host.availability", week=week_monday(day)))


@bp.get("/history")
@require_role("host")
def history():
    uid = current_user()["id"]
    logs = get_db().execute(
        "select w.*, g.name as group_name from work_logs w left join groups g on g.id = w.group_id "
        "where w.user_id = ? order by w.date desc, w.id desc", (uid,)).fetchall()
    total = sum(l["hours"] for l in logs)
    days = len({l["date"] for l in logs})
    return render_template("host/history.html", active="history", logs=logs, total=total, days=days, today=date.today().isoformat())


@bp.post("/hours")
@require_role("host")
def log_hours():
    uid = current_user()["id"]
    try:
        day = parse_date(request.form.get("date", ""))
        hrs = float(request.form.get("hours", "").replace(",", "."))
        if hrs <= 0:
            raise ValueError
    except ValueError as e:
        flash(str(e) if str(e) else "Hours should be a number above 0, like 2.5.", "error")
        return redirect(url_for("host.history"))
    gid = request.form.get("group_id") or None
    db = get_db()
    db.execute("insert into work_logs(user_id, group_id, date, hours, note) values (?,?,?,?,?)",
               (uid, gid, day, hrs, request.form.get("note", "").strip()))
    db.commit()
    flash(f"Logged {hrs:g} h for {fmt_date(day)}.", "ok")
    return redirect(url_for("host.history"))


@bp.post("/hours/<int:log_id>/delete")
@require_role("host")
def delete_hours(log_id: int):
    db = get_db()
    row = db.execute("select user_id from work_logs where id = ?", (log_id,)).fetchone()
    if row is None:
        abort(404)
    if row["user_id"] != current_user()["id"]:
        abort(403)
    db.execute("delete from work_logs where id = ?", (log_id,))
    db.commit()
    flash("Removed the entry.", "ok")
    return redirect(url_for("host.history"))
