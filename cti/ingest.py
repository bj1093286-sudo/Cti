"""동기화 폴더의 녹취 파일을 읽어 통화 기록으로 적재한다.

폴더 구조:  SYNC_ROOT/<상담원 이름>/.../<녹취 파일>
- 최상위 폴더 이름 = 상담원 (처음 보는 이름이면 상담원을 자동 등록)
- 파일 이름 = 고객 전화번호 + 통화 시작 일시
- 통화시간 = 오디오 헤더의 재생 길이(없으면 파일 크기로 추정)

개인정보: 전화번호 원문은 DB에 저장하지 않는다. 중복 제외 집계용 HMAC 키와
'010-****-5678' 형태의 표시용 마스킹 값만 저장한다.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .audio import AUDIO_EXTS, duration_sec
from .db import get_setting, get_setting_int, set_setting

# 동기화 중(아직 쓰는 중)인 파일을 건드리지 않도록, 최근 수정된 파일은 다음 회차로 미룬다.
MIN_FILE_AGE_SEC = 60

# 일시: 20261012_103015 / 2026-10-12 10-30-15 / 20261012103015 / 261012_103015
_DT_PATTERNS = [
    re.compile(r"(?<!\d)(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})[-_ T.]?(\d{2})[-_:.h]?(\d{2})[-_:.m]?(\d{2})(?!\d)"),
    re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})[-_ ](\d{2})(\d{2})(\d{2})(?!\d)"),
]
# 전화번호: 010-1234-5678, 01012345678, 02-123-4567, +82 10 1234 5678
_PHONE = re.compile(r"(?<![\d+])(?:\+?82[-. ]?)?(0?1[016789]|0\d{1,2})[-. ]?(\d{3,4})[-. ]?(\d{4})(?!\d)")


@dataclass
class Parsed:
    started_at: datetime
    phone: str | None  # 숫자만, 국내 형식(0으로 시작)
    masked: str | None  # 표시용 '010-****-5678'


def parse_filename(name: str) -> Parsed | None:
    stem = Path(name).stem
    started = None
    for pat in _DT_PATTERNS:
        for m in pat.finditer(stem):
            y, mo, d, h, mi, s = (int(g) for g in m.groups())
            if y < 100:
                y += 2000
            try:
                started = datetime(y, mo, d, h, mi, s)
            except ValueError:
                continue
            stem = stem[:m.start()] + " " + stem[m.end():]  # 일시 숫자가 전화번호로 잡히지 않게 제거
            break
        if started:
            break
    if started is None:
        return None
    m = _PHONE.search(stem)
    if not m:
        return Parsed(started, None, None)
    area, mid, last = m.groups()
    if not area.startswith("0"):  # +82 10 ... → 010
        area = "0" + area
    return Parsed(started, area + mid + last, f"{area}-****-{last}")


def _hmac(conn: sqlite3.Connection, text: str) -> str:
    key = get_setting(conn, "customer_hash_key").encode()
    return hmac.new(key, text.encode(), hashlib.sha256).hexdigest()[:32]


def customer_key(conn: sqlite3.Connection, digits: str) -> str:
    return _hmac(conn, "phone:" + digits)


def source_key(conn: sqlite3.Connection, rel_path: str) -> str:
    return _hmac(conn, "file:" + rel_path)


def mask_name(name: str) -> str:
    """로그·화면에 보이는 파일 이름에서 전화번호 가운데를 가린다."""
    return _PHONE.sub(lambda m: f"{m.group(1)}-****-{m.group(3)}", name)


def _agent_for_folder(conn: sqlite3.Connection, folder: str) -> int:
    row = conn.execute("SELECT id FROM agents WHERE sync_dir = ? OR (sync_dir IS NULL AND name = ?)",
                       (folder, folder)).fetchone()
    if row:
        return row["id"]
    return conn.execute("INSERT INTO agents(name, sync_dir) VALUES (?, ?)", (folder, folder)).lastrowid


def stable_files(folder: Path, now: float | None = None) -> tuple[list[Path], int]:
    """(최근 MIN_FILE_AGE_SEC 이내에 수정되지 않은 파일, 미룬 파일 수)."""
    now = time.time() if now is None else now
    ready, recent = [], 0
    for f in sorted(folder.rglob("*")):
        if not f.is_file() or f.name.startswith("."):
            continue
        if now - f.stat().st_mtime < MIN_FILE_AGE_SEC:
            recent += 1
        else:
            ready.append(f)
    return ready, recent


_lock = threading.Lock()  # 자동 적재·수동 적재·백업 전 적재가 겹치지 않게


def ingest_folder(conn: sqlite3.Connection, folder: Path, now: float | None = None) -> dict:
    """상담원 폴더 하나를 적재. 이미 적재된 파일(source_key)은 건너뛴다."""
    with _lock:
        return _ingest_folder(conn, folder, now)


def _ingest_folder(conn: sqlite3.Connection, folder: Path, now: float | None) -> dict:
    agent_id = _agent_for_folder(conn, folder.name)
    kbps = get_setting_int(conn, "fallback_kbps")
    files, recent = stable_files(folder, now)
    known = {r[0] for r in conn.execute("SELECT source_key FROM calls WHERE agent_id = ?", (agent_id,))}
    stats = {"added": 0, "already": 0, "recent": recent, "not_audio": 0, "failed": []}
    for f in files:
        if f.suffix.lower() not in AUDIO_EXTS:
            stats["not_audio"] += 1
            continue
        rel = f"{folder.name}/{f.relative_to(folder).as_posix()}"
        key = source_key(conn, rel)
        if key in known:
            stats["already"] += 1
            continue
        p = parse_filename(f.name)
        if p is None:
            stats["failed"].append(mask_name(rel))
            continue
        sec, how = duration_sec(f, kbps)
        conn.execute(
            """
            INSERT OR IGNORE INTO calls(agent_id, customer_key, customer_masked, started_at,
                                        duration_sec, duration_source, source_key, file_bytes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (agent_id,
             customer_key(conn, p.phone) if p.phone else None,
             p.masked,
             p.started_at.isoformat(sep=" "),
             round(sec), how, key, f.stat().st_size),
        )
        stats["added"] += 1
    conn.commit()
    return stats


def ingest_all(conn: sqlite3.Connection, sync_root: Path, now: float | None = None) -> dict:
    total = {"added": 0, "already": 0, "recent": 0, "not_audio": 0, "failed": [], "agents": 0}
    if sync_root.is_dir():
        for folder in sorted(p for p in sync_root.iterdir() if p.is_dir() and not p.name.startswith(".")):
            s = ingest_folder(conn, folder, now)
            total["agents"] += 1
            for k in ("added", "already", "recent", "not_audio"):
                total[k] += s[k]
            total["failed"] += s["failed"]
    record_result(conn, total)
    return total


def record_result(conn: sqlite3.Connection, stats: dict) -> None:
    summary = {**stats, "failed_count": len(stats["failed"]), "failed": stats["failed"][:20],
               "at": datetime.now().isoformat(sep=" ", timespec="seconds")}
    set_setting(conn, "last_ingest", json.dumps(summary, ensure_ascii=False))
    conn.commit()


def last_result(conn: sqlite3.Connection) -> dict | None:
    raw = get_setting(conn, "last_ingest")
    return json.loads(raw) if raw else None
