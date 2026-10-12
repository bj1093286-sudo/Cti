"""상담원 동기화 폴더 백업 후 비우기.

절차
1. 폴더 안의 파일 목록을 고정(스냅샷)한다.
2. 스냅샷 파일들을 BACKUP_ROOT/<상담원ID>/<타임스탬프>.zip 으로 압축한다.
3. zip 무결성 검사(testzip)와 파일 수 확인이 통과한 경우에만
   스냅샷에 포함된 파일만 삭제한다(작업 중 새로 들어온 파일은 남긴다).
4. 백업 이력을 기록한다.
"""
from __future__ import annotations

import sqlite3
import threading
import zipfile
from datetime import datetime
from pathlib import Path

_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


class BackupError(Exception):
    pass


def _agent_lock(agent_id: int) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(agent_id, threading.Lock())


def sync_dir_for(agent: sqlite3.Row, sync_root: Path) -> Path:
    """상담원 동기화 폴더. SYNC_ROOT 밖의 경로는 거부한다(오설정으로 엉뚱한 폴더 삭제 방지)."""
    raw = agent["sync_dir"] or str(agent["id"])
    path = (sync_root / raw).resolve()
    root = sync_root.resolve()
    if path == root or root not in path.parents:
        raise BackupError(f"동기화 폴더가 SYNC_ROOT 하위가 아닙니다: {path}")
    return path


def folder_status(conn: sqlite3.Connection, agent_id: int, sync_root: Path) -> dict:
    agent = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    if agent is None:
        raise BackupError("상담원을 찾을 수 없습니다.")
    try:
        folder = sync_dir_for(agent, sync_root)
    except BackupError as e:
        return {"path": None, "error": str(e), "file_count": 0, "total_bytes": 0}
    files = [f for f in folder.rglob("*") if f.is_file()] if folder.is_dir() else []
    return {
        "path": str(folder),
        "exists": folder.is_dir(),
        "file_count": len(files),
        "total_bytes": sum(f.stat().st_size for f in files),
    }


def history(conn: sqlite3.Connection, agent_id: int, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, created_at, archive_path, file_count, total_bytes, performed_by
        FROM backups WHERE agent_id = ? ORDER BY created_at DESC, id DESC LIMIT ?
        """,
        (agent_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def backup_and_clear(conn: sqlite3.Connection, agent_id: int, sync_root: Path,
                     backup_root: Path, performed_by: str) -> dict:
    agent = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    if agent is None:
        raise BackupError("상담원을 찾을 수 없습니다.")
    folder = sync_dir_for(agent, sync_root)

    lock = _agent_lock(agent_id)
    if not lock.acquire(blocking=False):
        raise BackupError("이미 이 상담원의 백업이 진행 중입니다.")
    try:
        if not folder.is_dir():
            raise BackupError(f"동기화 폴더가 없습니다: {folder}")
        files = sorted(f for f in folder.rglob("*") if f.is_file())
        if not files:
            raise BackupError("동기화 폴더가 이미 비어 있습니다.")

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest_dir = backup_root / str(agent_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        archive = dest_dir / f"{stamp}.zip"
        n = 1
        while archive.exists():
            archive = dest_dir / f"{stamp}-{n}.zip"
            n += 1

        total = 0
        try:
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
                for f in files:
                    total += f.stat().st_size
                    zf.write(f, f.relative_to(folder).as_posix())
            with zipfile.ZipFile(archive) as zf:
                if zf.testzip() is not None or len(zf.namelist()) != len(files):
                    raise BackupError("백업 파일 검증에 실패했습니다.")
        except Exception:
            archive.unlink(missing_ok=True)
            raise

        for f in files:
            f.unlink()
        # 비어 있는 하위 폴더 정리(루트 폴더는 유지)
        for d in sorted((d for d in folder.rglob("*") if d.is_dir()), key=lambda p: len(p.parts),
                        reverse=True):
            try:
                d.rmdir()
            except OSError:
                pass

        created = datetime.now().isoformat(sep=" ", timespec="seconds")
        cur = conn.execute(
            """
            INSERT INTO backups(agent_id, created_at, archive_path, file_count, total_bytes, performed_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (agent_id, created, str(archive), len(files), total, performed_by),
        )
        conn.commit()
        return {"id": cur.lastrowid, "created_at": created, "archive_path": str(archive),
                "file_count": len(files), "total_bytes": total, "performed_by": performed_by}
    finally:
        lock.release()
