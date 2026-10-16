import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from db import get_db  # noqa: E402


@pytest.fixture
def app(tmp_path):
    return create_app(str(tmp_path / "t.sqlite"), seed=False)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    with app.app_context():
        yield get_db()


def insert_user(db, name, role="host") -> int:
    cur = db.execute("insert into users(name, role) values (?, ?)", (name, role))
    db.commit()
    return cur.lastrowid


def insert_slot(db, user_id, date, start, end, on_call=0) -> int:
    cur = db.execute(
        "insert into availability(user_id, date, start_min, end_min, on_call) values (?, ?, ?, ?, ?)",
        (user_id, date, start, end, on_call),
    )
    db.commit()
    return cur.lastrowid


def insert_group(db, name, date, start, end) -> int:
    cur = db.execute(
        "insert into groups(name, date, start_min, end_min) values (?, ?, ?, ?)",
        (name, date, start, end),
    )
    db.commit()
    return cur.lastrowid


def login_as(client, user_id):
    return client.post(f"/switch/{user_id}", follow_redirects=False)


@pytest.fixture(name="insert_user")
def _insert_user_fixture(db):
    return lambda name, role="host": insert_user(db, name, role)


@pytest.fixture(name="insert_slot")
def _insert_slot_fixture(db):
    return lambda user_id, date, start, end, on_call=0: insert_slot(db, user_id, date, start, end, on_call)


@pytest.fixture(name="insert_group")
def _insert_group_fixture(db):
    return lambda name, date, start, end: insert_group(db, name, date, start, end)
