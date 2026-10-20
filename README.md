# SmartShift

Host scheduling for a small activity venue: hosts enter availability and log hours, the manager imports bookings from Excel, generates a fair schedule, and overrides it when needed.

## Run locally

```
pip install -r requirements.txt
python app.py              # http://127.0.0.1:5000
```

Demo data is seeded on first start (1 manager, 5 hosts, 12 groups this week). Reset it with `del smartshift.sqlite`.

CSS is Tailwind v4, precompiled into `static/tailwind.css`. Only rebuild after editing templates or `static/src/input.css`:

```
npm install
npm run build:css
```

## Host online (fork first)

Before hosting, **fork this repo** to your own GitHub account so you own your copy:

1. Go to https://github.com/zakaria17amir/Smartshift
2. Click "Fork" in the top-right
3. Then use your fork URL (`https://github.com/YOUR-USERNAME/Smartshift`) in the steps below

### Glitch (easiest)

1. Go to https://glitch.com and sign in
2. Click "New project" → "Import from GitHub"
3. Enter your fork URL: `https://github.com/YOUR-USERNAME/Smartshift`
4. Glitch builds and runs it automatically at `https://your-project-name.glitch.me`
5. First run seeds the demo DB (1 manager, 5 hosts, 12 groups)

### Replit

1. Go to https://replit.com and sign in
2. Click "Create Repl" → "Import from GitHub"
3. Enter your fork URL: `https://github.com/YOUR-USERNAME/Smartshift`
4. Click "Run" in the top-right
5. Replit gives you a web URL

### Notes

- Both platforms run the Flask dev server. For real traffic, change `app.run(debug=True)` to `app.run()` in `app.py` and use Gunicorn.
- SQLite works on both platforms, but they wipe the DB on container restart. For persistence, use PostgreSQL (change `db.py` to use `psycopg2` or Supabase).
- The password is still `1234` for all demo accounts. Change `DEMO_PASSWORD` in `auth.py` before exposing publicly.

## Files

| File | Role |
|---|---|
| `app.py` | `create_app()`, blueprint registration, Jinja filters |
| `db.py`, `schema.sql` | SQLite connection, schema, demo seed |
| `auth.py` | simulated sign-in, `require_role` guard (403 for the wrong role) |
| `host.py` | `/me` — my week, availability, on-call, hours, history |
| `manager.py` | `/manager` — week grid, availability overview, import, generate, override, hours, add/delete group; `/api/bookings` |
| `scheduler.py` | pure scheduling algorithm (`schedule`, `check_assignment`, `compute_stats`) |
| `importer.py` | pasted TSV/CSV and `.xlsx` → group rows with per-row errors |
| `grid.py`, `templates/_week_grid.html` | week grid layout |

## Demo script (section 8 of the brief)

Sign-in window: pick a name, password `1234` for every demo account (simulated auth, as the brief allows).

1. Sign in as **Anna Szabó** → Availability: add Monday 18:00–20:00, mark Friday on call, remove a slot. Work history: log hours. Sign in as **Bence**: Anna's data is not visible; `/manager` gives 403.
2. Sign in as **Dóra Kiss** (manager) → Import: paste rows from Excel (header `Group Date Start End`). Import the same rows again: they are skipped.
3. Week → **Generate schedule**. Schedule tab shows who got what and why; Monday 09:00/10:00/12:30 go to one host (four-hour rule), Monday 17:00 and Thursday 20:30 are unassigned (nobody available). Override a row — rule breaks are warned, not blocked. Regenerate: hand-set rows stay.
4. Hours tab: everyone's logged hours and this week's workload/load. Add a group on Saturday with "Assign now": the on-call host is preferred. `POST /api/bookings` does the same from an external site:
   `curl -X POST http://127.0.0.1:5000/api/bookings -H "Content-Type: application/json" -d "{\"name\":\"Walk-in\",\"date\":\"2026-10-24\",\"start\":\"11:00\",\"end\":\"12:30\"}"`
5. Users tab: add a new host, change someone to manager, remove a user (their hours/assignments stay in the system).
