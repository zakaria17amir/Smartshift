CREATE TABLE IF NOT EXISTS users (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('manager', 'host'))
);

CREATE TABLE IF NOT EXISTS availability (
    id        INTEGER PRIMARY KEY,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date      TEXT NOT NULL,
    start_min INTEGER NOT NULL,
    end_min   INTEGER NOT NULL,
    on_call   INTEGER NOT NULL DEFAULT 0,
    CHECK (end_min > start_min)
);

CREATE TABLE IF NOT EXISTS groups (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL,
    date      TEXT NOT NULL,
    start_min INTEGER NOT NULL,
    end_min   INTEGER NOT NULL,
    size      INTEGER,
    CHECK (end_min > start_min)
);

CREATE TABLE IF NOT EXISTS assignments (
    group_id   INTEGER PRIMARY KEY REFERENCES groups(id) ON DELETE CASCADE,
    user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    source     TEXT NOT NULL CHECK (source IN ('auto', 'manual')),
    reason     TEXT NOT NULL DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS work_logs (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id   INTEGER REFERENCES groups(id) ON DELETE SET NULL,
    date       TEXT NOT NULL,
    hours      REAL NOT NULL CHECK (hours > 0),
    note       TEXT NOT NULL DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_availability_user_date ON availability(user_id, date);
CREATE INDEX IF NOT EXISTS idx_groups_date ON groups(date);
CREATE INDEX IF NOT EXISTS idx_work_logs_user_date ON work_logs(user_id, date);
