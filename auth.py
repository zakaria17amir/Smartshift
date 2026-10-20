import sqlite3
from functools import wraps

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for

from db import get_db

bp = Blueprint("auth", __name__)

ROLE_HOME = {"host": "/me", "manager": "/manager"}
DEMO_PASSWORD = "1234"  # simulated accounts; the brief allows no real auth service


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
    return render_template("switch_user.html", users=users, selected=request.args.get("user", type=int), demo_password=DEMO_PASSWORD)


def _sign_in(user_id: int):
    user = get_db().execute("select id, name, role from users where id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)
    session.clear()
    session["user_id"] = user["id"]
    flash(f"Signed in as {user['name']}", "ok")
    return redirect(role_home(user))


@bp.post("/login")
def login():
    uid = request.form.get("user_id", type=int)
    if request.form.get("password", "") != DEMO_PASSWORD:
        flash("That password isn't right. Demo accounts use 1234.", "error")
        return redirect(url_for("auth.switch_page", user=uid))
    return _sign_in(uid or 0)


@bp.post("/switch/<int:user_id>")
def switch_to(user_id: int):
    return _sign_in(user_id)


@bp.post("/switch")
def switch_out():
    session.clear()
    return redirect(url_for("auth.switch_page"))
