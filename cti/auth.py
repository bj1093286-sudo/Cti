"""간단한 사용자/세션 관리 (역할: admin, viewer)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta

SESSION_TTL = timedelta(hours=12)
_ITER = 200_000


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITER)
    return f"pbkdf2_sha256${_ITER}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters))
    return hmac.compare_digest(dk.hex(), digest)


def create_user(conn: sqlite3.Connection, username: str, password: str, role: str) -> None:
    conn.execute(
        "INSERT INTO users(username, password_hash, role) VALUES (?, ?, ?) "
        "ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash, role = excluded.role",
        (username, hash_password(password), role),
    )
    conn.commit()


def login(conn: sqlite3.Connection, username: str, password: str) -> str | None:
    row = conn.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,)).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        return None
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + SESSION_TTL).isoformat(timespec="seconds")
    conn.execute("INSERT INTO sessions(token, user_id, expires_at) VALUES (?, ?, ?)",
                 (token, row["id"], expires))
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (datetime.now().isoformat(timespec="seconds"),))
    conn.commit()
    return token


def logout(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()


def user_for_token(conn: sqlite3.Connection, token: str | None) -> dict | None:
    if not token:
        return None
    row = conn.execute(
        """
        SELECT u.id, u.username, u.role FROM sessions s JOIN users u ON u.id = s.user_id
        WHERE s.token = ? AND s.expires_at >= ?
        """,
        (token, datetime.now().isoformat(timespec="seconds")),
    ).fetchone()
    return dict(row) if row else None
