import sqlite3

import pytest

from app import create_app
from db import get_db, seed_demo


def test_app_boots_and_schema(client, db):
    assert client.get("/").status_code == 200
    names = {r[0] for r in db.execute("select name from sqlite_master where type='table'")}
    assert {"users", "availability", "groups", "assignments", "work_logs"} <= names


def test_seed_counts(tmp_path):
    app = create_app(str(tmp_path / "s.sqlite"), seed=True)
    with app.app_context():
        db = get_db()
        assert db.execute("select count(*) from users where role='host'").fetchone()[0] == 5
        assert db.execute("select count(*) from users where role='manager'").fetchone()[0] == 1
        assert db.execute("select count(*) from groups").fetchone()[0] == 12
        assert db.execute("select count(*) from availability where on_call=1").fetchone()[0] == 2
        assert db.execute("select count(*) from work_logs").fetchone()[0] == 4
        assert db.execute("select count(*) from assignments").fetchone()[0] == 0
        seed_demo(db, "2026-10-19")  # idempotent
        assert db.execute("select count(*) from users").fetchone()[0] == 6


def test_seed_dates_relative_to_monday(db):
    seed_demo(db, "2026-10-19")
    group_dates = {r[0] for r in db.execute("select distinct date from groups")}
    assert group_dates == {"2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-24"}
    log_dates = {r[0] for r in db.execute("select distinct date from work_logs")}
    assert log_dates == {"2026-10-12", "2026-10-14", "2026-10-15"}
    on_call = db.execute("select start_min, end_min from availability where on_call=1").fetchall()
    assert all((r["start_min"], r["end_min"]) == (0, 1440) for r in on_call)


def test_init_db_is_idempotent(app):
    from db import init_db

    with app.app_context():
        uid = get_db().execute("insert into users(name, role) values ('X', 'host')").lastrowid
        get_db().commit()
    init_db(app)
    with app.app_context():
        assert get_db().execute("select id from users where id=?", (uid,)).fetchone() is not None


def test_schema_constraints(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("insert into users(name, role) values ('Bad', 'admin')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("insert into availability(user_id, date, start_min, end_min) values (999, '2026-10-19', 540, 600)")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("insert into groups(name, date, start_min, end_min) values ('G', '2026-10-19', 600, 600)")


def test_delete_cascades(db, insert_user, insert_group):
    uid = insert_user("Host")
    gid = insert_group("Tour", "2026-10-19", 540, 660)
    db.execute("insert into assignments(group_id, user_id, source) values (?, ?, 'manual')", (gid, uid))
    db.execute("insert into work_logs(user_id, group_id, date, hours) values (?, ?, '2026-10-19', 2.0)", (uid, gid))
    db.commit()
    db.execute("delete from groups where id=?", (gid,))
    db.commit()
    assert db.execute("select count(*) from assignments").fetchone()[0] == 0
    assert db.execute("select group_id from work_logs").fetchone()[0] is None


def test_template_filters(app):
    env = app.jinja_env
    assert env.filters["hhmm"](570) == "09:30"
    assert env.filters["nice_date"]("2026-10-20") == "Tue 20 Oct"
    assert env.filters["long_date"]("2026-10-20") == "Tuesday 20 October 2026"


def test_conftest_helpers(db, insert_user, insert_slot, insert_group):
    uid = insert_user("Someone", role="manager")
    assert db.execute("select role from users where id=?", (uid,)).fetchone()[0] == "manager"
    sid = insert_slot(uid, "2026-10-19", 540, 660, on_call=1)
    assert db.execute("select on_call from availability where id=?", (sid,)).fetchone()[0] == 1
    gid = insert_group("Tour", "2026-10-19", 540, 660)
    assert db.execute("select size from groups where id=?", (gid,)).fetchone()[0] is None
