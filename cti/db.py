"""SQLite 스키마와 연결."""
from __future__ import annotations

import secrets
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL,
    extension TEXT,
    sync_dir  TEXT UNIQUE,      -- SYNC_ROOT 아래 최상위 폴더 이름(비어 있으면 name)
    active    INTEGER NOT NULL DEFAULT 1
);

-- 아웃바운드 전용: 모든 통화는 상담원이 고객에게 건 발신 통화다.
-- 녹취 파일 1개 = 통화 1건. 고객 전화번호 원문은 저장하지 않는다(개인정보 최소화).
CREATE TABLE IF NOT EXISTS calls (
    id               INTEGER PRIMARY KEY,
    agent_id         INTEGER NOT NULL REFERENCES agents(id),
    customer_key     TEXT,      -- 전화번호 HMAC(중복 제외 집계용, 복원 불가)
    customer_masked  TEXT,      -- 표시용 '010-****-5678'
    started_at       TEXT NOT NULL,  -- 로컬 시각 'YYYY-MM-DD HH:MM:SS'
    duration_sec     INTEGER NOT NULL DEFAULT 0,
    duration_source  TEXT,      -- 'header' | 'size'
    source_key       TEXT UNIQUE,    -- '<상담원 폴더>/<파일 경로>'의 HMAC (중복 적재 방지, 파일명에 번호가 있어 원문 미저장)
    file_bytes       INTEGER
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

DEFAULT_SETTINGS = {
    "min_call_sec": "10",
    # 헤더에서 길이를 못 읽는 형식은 '파일 크기 / 비트레이트'로 통화시간을 추정한다.
    "fallback_kbps": "128",
}


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
    # 전화번호 해시용 비밀키 — DB마다 한 번 생성. API로 노출하지 않는다.
    conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES ('customer_hash_key', ?)",
                 (secrets.token_hex(32),))
    conn.commit()
    return conn


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else DEFAULT_SETTINGS.get(key)


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def get_setting_int(conn: sqlite3.Connection, key: str) -> int:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return int(row["value"] if row else DEFAULT_SETTINGS[key])
