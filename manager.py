from datetime import date

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, send_from_directory, url_for

from auth import require_role
from db import get_db
from grid import build_grid
from host import week_ctx, week_param
from importer import parse_text, parse_xlsx
from scheduler import Group, Slot, check_assignment, compute_stats, schedule
from timeutil import fmt_date, fmt_time, hours, parse_date, parse_time, week_days, week_monday

bp = Blueprint("manager", __name__, url_prefix="/manager")


def hosts():
    return get_db().execute("select * from users where role = 'host' order by name").fetchall()


def groups_in_week(monday: str):
    d = week_days(monday)
    return get_db().execute(
        "select g.*, a.user_id, a.source, a.reason, u.name as host_name from groups g "
        "left join assignments a on a.group_id = g.id left join users u on u.id = a.user_id "
        "where g.date between ? and ? order by g.date, g.start_min, g.end_min, g.id", (d[0], d[-1])).fetchall()


def slots_between(d0: str, d1: str) -> list[Slot]:
    return [Slot(r["user_id"], r["date"], r["start_min"], r["end_min"], bool(r["on_call"])) for r in
            get_db().execute("select * from availability where date between ? and ?", (d0, d1))]


def to_group(r) -> Group:
    return Group(r["id"], r["date"], r["start_min"], r["end_min"], r["name"])


def first(name: str) -> str:
    return name.split()[0]


@bp.get("")
@require_role("manager")
def index():
    monday = week_param()
    rows = groups_in_week(monday)
    items = [{"date": g["date"], "start": g["start_min"], "end": g["end_min"], "label": g["name"],
              "sublabel": first(g["host_name"]) if g["host_name"] else "Unassigned",
              "kind": "block" if g["user_id"] else "unassigned", "colour": (g["user_id"] or 0) % 6,
              "href": url_for("manager.schedule_page", week=monday) + f"#g{g['id']}"} for g in rows]
    n_un = sum(1 for g in rows if not g["user_id"])
    return render_template("manager/week.html", active="week", w=week_ctx(monday), grid=build_grid(week_days(monday), items),
                           n_groups=len(rows), n_un=n_un)


@bp.get("/availability")
@require_role("manager")
def availability():
    monday = week_param()
    days = week_days(monday)
    slots = get_db().execute("select * from availability where date between ? and ? order by start_min", (days[0], days[-1])).fetchall()
    table = {h["id"]: {d: [s for s in slots if s["user_id"] == h["id"] and s["date"] == d] for d in days} for h in hosts()}
    oncall = [f"{first(h['name'])} ({fmt_date(s['date'])[:3]})" for h in hosts() for d in days for s in table[h["id"]][d] if s["on_call"]]
    return render_template("manager/availability.html", active="availability", w=week_ctx(monday), hosts=hosts(), table=table, oncall=oncall)


@bp.route("/import", methods=["GET", "POST"])
@require_role("manager")
def import_page():
    result = None
    if request.method == "POST":
        text = request.form.get("data", "").strip()
        f = request.files.get("file")
        if f and f.filename:
            data = f.read()
            rows, errs = parse_xlsx(data) if f.filename.lower().endswith(".xlsx") else parse_text(data.decode("utf-8-sig", errors="replace"))
        elif text:
            rows, errs = parse_text(text)
        else:
            flash("Paste spreadsheet rows or choose a file first.", "error")
            return render_template("manager/import.html", active="import", result=None)
        db = get_db()
        added = skipped = 0
        first_week = None
        for r in rows:
            if db.execute("select 1 from groups where name = ? and date = ? and start_min = ?", (r.name, r.date, r.start)).fetchone():
                skipped += 1
                continue
            db.execute("insert into groups(name, date, start_min, end_min, size) values (?,?,?,?,?)", (r.name, r.date, r.start, r.end, r.size))
            added += 1
            first_week = min(first_week or r.date, r.date)
        db.commit()
        msg = f"Imported {added} group{'' if added == 1 else 's'}."
        if skipped:
            msg += f" {skipped} {'was' if skipped == 1 else 'were'} already in the schedule and {'was' if skipped == 1 else 'were'} skipped."
        result = {"msg": msg, "errors": errs, "week": week_monday(first_week) if first_week else None}
    return render_template("manager/import.html", active="import", result=result)


@bp.get("/import/example.<ext>")
@bp.get("/import/example_<suffix>.<ext>")
@require_role("manager")
def example_file(ext: str, suffix: str = ""):
    if ext not in ("xlsx", "csv") or suffix not in ("", "next_week"):
        abort(404)
    return send_from_directory("examples", f"groups_example{'_' + suffix if suffix else ''}.{ext}", as_attachment=True)


def run_schedule(monday: str, keep_manual: bool):
    db = get_db()
    days = week_days(monday)
    rows = groups_in_week(monday)
    groups = [to_group(r) for r in rows]
    locked = {r["id"]: r["user_id"] for r in rows if keep_manual and r["source"] == "manual" and r["user_id"]}
    res = schedule(groups, slots_between(days[0], days[-1]), locked)
    db.execute("delete from assignments where group_id in (select id from groups where date between ? and ?)" +
               (" and source = 'auto'" if keep_manual else ""), (days[0], days[-1]))
    for a in res.assignments:
        if a.locked:
            continue
        db.execute("insert or replace into assignments(group_id, user_id, source, reason) values (?,?,?,?)", (a.group_id, a.user_id, "auto", a.reason))
    db.commit()
    return res


@bp.post("/schedule/generate")
@require_role("manager")
def generate():
    monday = week_param()
    res = run_schedule(monday, request.form.get("keep_manual") == "1")
    n_un = len(res.unassigned)
    flash(f"Schedule generated: {len(res.assignments) - n_un} groups assigned, {n_un} unassigned. Load spread {res.load_spread:.2f}.", "ok")
    return redirect(url_for("manager.schedule_page", week=monday))


@bp.get("/schedule")
@require_role("manager")
def schedule_page():
    monday = week_param()
    days = week_days(monday)
    rows = groups_in_week(monday)
    slots = slots_between(days[0], days[-1])
    by_day = {}
    warnings = {}
    for r in rows:
        by_day.setdefault(r["date"], []).append(r)
        if r["user_id"] and r["source"] == "manual":
            others = [to_group(o) for o in rows if o["user_id"] == r["user_id"] and o["id"] != r["id"] and o["date"] == r["date"]]
            warnings[r["id"]] = check_assignment(to_group(r), [s for s in slots if s.user_id == r["user_id"]], others, name=first(r["host_name"]))
    return render_template("manager/schedule.html", active="schedule", w=week_ctx(monday), by_day=by_day, hosts=hosts(), warnings=warnings)


@bp.post("/schedule/<int:group_id>")
@require_role("manager")
def override(group_id: int):
    db = get_db()
    g = db.execute("select * from groups where id = ?", (group_id,)).fetchone()
    if g is None:
        abort(404)
    uid = request.form.get("user_id") or None
    db.execute("insert or replace into assignments(group_id, user_id, source, reason) values (?,?,'manual','Set by manager')", (group_id, uid))
    db.commit()
    if uid:
        host = db.execute("select name from users where id = ?", (uid,)).fetchone()
        flash(f"{g['name']} is now hosted by {host['name']}.", "ok")
        others = [to_group(o) for o in groups_in_week(week_monday(g["date"])) if o["user_id"] == int(uid) and o["id"] != group_id and o["date"] == g["date"]]
        warns = check_assignment(to_group(g), [s for s in slots_between(g["date"], g["date"]) if s.user_id == int(uid)], others, name=first(host["name"]))
        if warns:
            flash(" ".join(warns) + " The assignment is saved anyway.", "error")
    else:
        flash(f"{g['name']} is now unassigned.", "ok")
    return redirect(url_for("manager.schedule_page", week=week_monday(g["date"])) + f"#g{group_id}")


@bp.get("/users")
@require_role("manager")
def users_page():
    users = get_db().execute("select * from users order by role = 'manager' desc, name").fetchall()
    return render_template("manager/users.html", active="users", users=users)


@bp.post("/users")
@require_role("manager")
def add_user():
    name = request.form.get("name", "").strip()
    role = request.form.get("role", "host")
    if not name:
        flash("Name is required.", "error")
        return redirect(url_for("manager.users_page"))
    if role not in ("manager", "host"):
        role = "host"
    db = get_db()
    db.execute("insert into users(name, role) values (?, ?)", (name, role))
    db.commit()
    flash(f"Added {name} as {role}.", "ok")
    return redirect(url_for("manager.users_page"))


@bp.post("/users/<int:user_id>/role")
@require_role("manager")
def change_role(user_id: int):
    user = get_db().execute("select * from users where id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)
    new_role = request.form.get("role", "host")
    if new_role not in ("manager", "host"):
        flash("Invalid role.", "error")
        return redirect(url_for("manager.users_page"))
    db = get_db()
    db.execute("update users set role = ? where id = ?", (new_role, user_id))
    db.commit()
    flash(f"{user['name']} is now {new_role}.", "ok")
    return redirect(url_for("manager.users_page"))


@bp.post("/users/<int:user_id>/delete")
@require_role("manager")
def delete_user(user_id: int):
    user = get_db().execute("select * from users where id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)
    db = get_db()
    db.execute("delete from users where id = ?", (user_id,))
    db.commit()
    flash(f"Removed {user['name']}.", "ok")
    return redirect(url_for("manager.users_page"))


@bp.get("/hours")
@require_role("manager")
def hours_page():
    monday = week_param()
    days = week_days(monday)
    host_filter = request.args.get("host", type=int)
    q = "select w.*, u.name as host_name, g.name as group_name from work_logs w join users u on u.id = w.user_id left join groups g on g.id = w.group_id"
    logs = get_db().execute(q + (" where w.user_id = ?" if host_filter else "") + " order by w.date desc, w.id desc",
                            (host_filter,) if host_filter else ()).fetchall()
    rows = groups_in_week(monday)
    stats = compute_stats([to_group(r) for r in rows], slots_between(days[0], days[-1]), {r["id"]: r["user_id"] for r in rows if r["user_id"]})
    logged_week = {r[0]: r[1] for r in get_db().execute("select user_id, sum(hours) from work_logs where date between ? and ? group by user_id", (days[0], days[-1]))}
    workload = [{"name": h["name"], **stats.get(h["id"], {"groups": 0, "hours": 0.0, "capacity_hours": 0.0, "load": 0.0}),
                 "logged": logged_week.get(h["id"], 0.0)} for h in hosts()]
    return render_template("manager/hours.html", active="hours", w=week_ctx(monday), logs=logs, workload=workload, hosts=hosts(), host_filter=host_filter)


def add_group(name: str, day: str, start: int, end: int, size, assign_now: bool):
    db = get_db()
    cur = db.execute("insert into groups(name, date, start_min, end_min, size) values (?,?,?,?,?)", (name, day, start, end, size))
    gid = cur.lastrowid
    host_name = reason = None
    if assign_now:
        day_rows = get_db().execute("select g.id, a.user_id from groups g join assignments a on a.group_id = g.id where g.date = ? and a.user_id is not null", (day,)).fetchall()
        all_groups = [to_group(r) for r in db.execute("select * from groups where date = ?", (day,))]
        res = schedule(all_groups, slots_between(day, day), {r["id"]: r["user_id"] for r in day_rows}, last_minute=True)
        a = next(x for x in res.assignments if x.group_id == gid)
        db.execute("insert or replace into assignments(group_id, user_id, source, reason) values (?,?,'auto',?)", (gid, a.user_id, a.reason))
        reason = a.reason
        if a.user_id:
            host_name = db.execute("select name from users where id = ?", (a.user_id,)).fetchone()["name"]
    db.commit()
    return gid, host_name, reason


@bp.route("/groups/new", methods=["GET", "POST"])
@require_role("manager")
def group_new():
    if request.method == "POST":
        try:
            day = parse_date(request.form.get("date", ""))
            start, end = parse_time(request.form.get("start", "")), parse_time(request.form.get("end", ""))
            if end <= start:
                raise ValueError(f"End time {fmt_time(end)} is not after start time {fmt_time(start)}.")
            name = request.form.get("name", "").strip() or "Group"
        except ValueError as e:
            flash(str(e), "error")
            return render_template("manager/group_new.html", active="schedule", today=date.today().isoformat())
        gid, host_name, reason = add_group(name, day, start, end, request.form.get("size", type=int), request.form.get("assign_now") == "1")
        msg = f"Added {name} on {fmt_date(day)} {fmt_time(start)}–{fmt_time(end)}"
        if host_name:
            msg += f", hosted by {host_name}{' (on call)' if 'On-call' in (reason or '') else ''}."
        elif reason:
            msg += ". No one is available; it's marked unassigned."
        else:
            msg += "."
        flash(msg, "ok")
        return redirect(url_for("manager.schedule_page", week=week_monday(day)) + f"#g{gid}")
    return render_template("manager/group_new.html", active="schedule", today=date.today().isoformat())


@bp.post("/groups/<int:group_id>/delete")
@require_role("manager")
def group_delete(group_id: int):
    db = get_db()
    g = db.execute("select * from groups where id = ?", (group_id,)).fetchone()
    if g is None:
        abort(404)
    db.execute("delete from groups where id = ?", (group_id,))
    db.commit()
    flash(f"Removed {g['name']}.", "ok")
    return redirect(url_for("manager.schedule_page", week=week_monday(g["date"])))


api = Blueprint("api", __name__, url_prefix="/api")


@api.post("/bookings")
def booking():
    body = request.get_json(silent=True) or {}
    try:
        day = parse_date(str(body.get("date", "")))
        start, end = parse_time(str(body.get("start", ""))), parse_time(str(body.get("end", "")))
        if end <= start:
            raise ValueError("end must be after start")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    gid, host_name, reason = add_group(str(body.get("name") or "Group"), day, start, end, body.get("size"), True)
    return jsonify({"group_id": gid, "host": host_name, "reason": reason}), 201
