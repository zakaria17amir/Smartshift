import sqlite3
from functools import wraps

from flask import Blueprint, abort, flash, g, redirect, render_template, session, url_for

from db import get_db

bp = Blueprint("auth", __name__)

ROLE_HOME = {"host": "/me", "manager": "/manager"}


def current_user() -> sqlite3.Row | None:
    if "current_user" not in g:
        uid = session.get("user_id")
        g.current_user = (
            get_db().execute("select id, name, role from users where id = ?", (uid,)).fetchone()
            if uid is not None
            else None
        )
    return g.current_user


def role_home(user: sqlite3.Row) -> str:
    return ROLE_HOME[user["role"]]


def require_role(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if user is None:
                return redirect(url_for("auth.switch_page"))
            if user["role"] not in roles:
                return render_template("403.html"), 403
            return view(*args, **kwargs)

        return wrapped

    return decorator


@bp.get("/")
def switch_page():
    user = current_user()
    if user is not None:
        return redirect(role_home(user))
    users = get_db().execute(
        "select id, name, role from users order by role = 'manager' desc, name"
    ).fetchall()
    return render_template("switch_user.html", users=users)


@bp.post("/switch/<int:user_id>")
def switch_to(user_id: int):
    user = get_db().execute("select id, name, role from users where id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)
    session.clear()
    session["user_id"] = user["id"]
    flash(f"Signed in as {user['name']}", "ok")
    return redirect(role_home(user))


@bp.post("/switch")
def switch_out():
    session.clear()
    return redirect(url_for("auth.switch_page"))
