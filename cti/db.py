"""SQLite 스키마와 연결."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL,
    extension TEXT,
    sync_dir  TEXT,             -- 상담원별 동기화 폴더(비어 있으면 SYNC_ROOT/<id>)
    active    INTEGER NOT NULL DEFAULT 1
);

-- 아웃바운드 전용: 모든 통화는 상담원이 고객에게 건 발신 통화다.
CREATE TABLE IF NOT EXISTS calls (
    id              INTEGER PRIMARY KEY,
    agent_id        INTEGER NOT NULL REFERENCES agents(id),
    customer_number TEXT,
    started_at      TEXT NOT NULL,  -- 로컬 시각 'YYYY-MM-DD HH:MM:SS'
    duration_sec    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_calls_started ON calls(started_at);
CREATE INDEX IF NOT EXISTS idx_calls_agent_started ON calls(agent_id, started_at);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'viewer'))
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backups (
    id           INTEGER PRIMARY KEY,
    agent_id     INTEGER NOT NULL REFERENCES agents(id),
    created_at   TEXT NOT NULL,
    archive_path TEXT NOT NULL,
    file_count   INTEGER NOT NULL,
    total_bytes  INTEGER NOT NULL,
    performed_by TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {"min_call_sec": "10"}


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    return conn


def get_setting_int(conn: sqlite3.Connection, key: str) -> int:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return int(row["value"] if row else DEFAULT_SETTINGS[key])
