import sqlite3
from pathlib import Path

from flask import current_app, g

from timeutil import shift_week, week_days

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = _connect(current_app.config["DATABASE"])
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    conn = _connect(app.config["DATABASE"])
    try:
        has_users = conn.execute(
            "select 1 from sqlite_master where type='table' and name='users'"
        ).fetchone()
        if has_users is None:
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            conn.commit()
    finally:
        conn.close()


_USERS = [
    (1, "Dóra Kiss", "manager"),
    (2, "Anna Szabó", "host"),
    (3, "Bence Tóth", "host"),
    (4, "Lili Nagy", "host"),
    (5, "Máté Varga", "host"),
    (6, "Zsófi Horváth", "host"),
]

# (user_id, day offset, start_min, end_min, on_call)
_AVAILABILITY = [
    *[(2, d, 8 * 60, 18 * 60, 0) for d in range(0, 5)],
    *[(3, d, 9 * 60, 17 * 60, 0) for d in (0, 2, 4)],
    (3, 5, 0, 1440, 1),
    *[(4, d, 8 * 60, 13 * 60, 0) for d in range(0, 4)],
    *[(5, d, 12 * 60, 20 * 60, 0) for d in (1, 3)],
    (5, 5, 9 * 60, 18 * 60, 0),
    (6, 5, 9 * 60, 18 * 60, 0),
    (6, 4, 0, 1440, 1),
]

# (name, day offset, start_min, end_min)
_GROUPS = [
    ("Morning yoga", 0, 9 * 60, 10 * 60 + 30),
    ("Castle tour", 0, 10 * 60, 12 * 60),
    ("Pottery workshop", 0, 12 * 60 + 30, 14 * 60),
    ("Evening wine tasting", 0, 17 * 60, 19 * 60),
    ("School visit", 1, 9 * 60, 11 * 60),
    ("Team building", 1, 14 * 60, 17 * 60),
    ("Kids science club", 2, 10 * 60, 11 * 60 + 30),
    ("Photography walk", 2, 15 * 60, 17 * 60),
    ("Cooking class", 3, 18 * 60, 20 * 60),
    ("Board game night", 3, 20 * 60 + 30, 22 * 60),
    ("Family escape room", 5, 10 * 60, 11 * 60 + 30),
    ("Birthday party", 5, 13 * 60, 15 * 60),
]

# (user_id, day offset relative to monday, hours, note)
_WORK_LOGS = [
    (2, -7, 3.0, "Castle tour"),
    (2, -5, 1.5, ""),
    (3, -7, 2.0, ""),
    (4, -4, 2.0, ""),
]


def seed_demo(db: sqlite3.Connection, monday_iso: str):
    if db.execute("select 1 from users limit 1").fetchone() is not None:
        return
    # Previous week + seeded week; offset -7..6 lands on index offset + 7.
    days = week_days(shift_week(monday_iso, -1)) + week_days(monday_iso)

    def day(offset: int) -> str:
        return days[offset + 7]

    db.executemany("insert into users(id, name, role) values (?, ?, ?)", _USERS)
    db.executemany(
        "insert into availability(user_id, date, start_min, end_min, on_call) values (?, ?, ?, ?, ?)",
        [(uid, day(d), s, e, oc) for uid, d, s, e, oc in _AVAILABILITY],
    )
    db.executemany(
        "insert into groups(name, date, start_min, end_min) values (?, ?, ?, ?)",
        [(name, day(d), s, e) for name, d, s, e in _GROUPS],
    )
    db.executemany(
        "insert into work_logs(user_id, date, hours, note) values (?, ?, ?, ?)",
        [(uid, day(d), h, note) for uid, d, h, note in _WORK_LOGS],
    )
    db.commit()
