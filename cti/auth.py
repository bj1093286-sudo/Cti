"""간단한 사용자/세션 관리 (역할: admin, viewer)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta

SESSION_TTL = timedelta(hours=12)
_ITER = 200_000

# 비밀번호 대입 방지: 같은 아이디로 연속 MAX_FAILS 회 틀리면 LOCK_SEC 동안 로그인 차단
MAX_FAILS = 5
LOCK_SEC = 300
_fails: dict[str, tuple[int, float]] = {}  # username -> (연속 실패 수, 마지막 실패 시각)
_fails_lock = threading.Lock()


class LoginLocked(Exception):
    pass


def _check_lock(username: str) -> None:
    with _fails_lock:
        n, at = _fails.get(username, (0, 0.0))
        if n >= MAX_FAILS and time.time() - at < LOCK_SEC:
            raise LoginLocked
        if n >= MAX_FAILS:  # 잠금 시간이 지나면 초기화
            _fails.pop(username, None)


def _record(username: str, ok: bool) -> None:
    with _fails_lock:
        if ok:
            _fails.pop(username, None)
        else:
            n, _ = _fails.get(username, (0, 0.0))
            _fails[username] = (n + 1, time.time())


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
    """성공하면 세션 토큰, 틀리면 None. 잠긴 아이디면 LoginLocked."""
    _check_lock(username)
    row = conn.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,)).fetchone()
    ok = row is not None and verify_password(password, row["password_hash"])
    _record(username, ok)
    if not ok:
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
