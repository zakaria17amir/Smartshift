from datetime import date

from flask import Flask

import timeutil
from db import close_db, get_db, init_db, seed_demo


def create_app(db_path: str = "smartshift.sqlite", seed: bool = True) -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "smartshift-dev-not-secret"
    app.config["DATABASE"] = db_path

    app.teardown_appcontext(close_db)
    app.add_template_filter(timeutil.fmt_time, "hhmm")
    app.add_template_filter(timeutil.fmt_date, "nice_date")
    app.add_template_filter(timeutil.fmt_date_long, "long_date")

    init_db(app)
    if seed:
        with app.app_context():
            seed_demo(get_db(), timeutil.week_monday(date.today().isoformat()))

    @app.get("/")
    def index():
        return "SmartShift"

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
