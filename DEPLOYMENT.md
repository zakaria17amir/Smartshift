# Free hosting

SmartShift is a Flask app with SQLite. For production, swap `smartshift.sqlite` for PostgreSQL and use a WSGI server like Gunicorn.

## Easiest free option: Glitch

1. Go to https://glitch.com and sign in
2. Click "New project" → "Import from GitHub"
3. Enter `https://github.com/zakaria17amir/Smartshift`
4. Glitch builds and runs it automatically at `https://your-project-name.glitch.me`
5. First run seeds the demo DB (1 manager, 5 hosts, 12 groups)

## Alternative: Replit

1. Go to https://replit.com and sign in
2. Click "Create Repl" → "Import from GitHub"
3. Enter `https://github.com/zakaria17amir/Smartshift`
4. Click "Run" in the top-right
5. Replit gives you a web URL

## Notes

- Both platforms run the Flask dev server. For real traffic, change `app.run(debug=True)` to `app.run()` in `app.py` and use Gunicorn.
- SQLite works on both platforms, but they wipe the DB on container restart. For persistence, use PostgreSQL (change `db.py` to use `psycopg2` or Supabase).
- The password is still `1234` for all demo accounts. Change `DEMO_PASSWORD` in `auth.py` before exposing publicly.
