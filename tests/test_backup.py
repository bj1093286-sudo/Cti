import tempfile
import unittest
import zipfile
from pathlib import Path

from cti import backup
from cti.db import connect
from tests.helpers import write_wav


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.sync, self.bak = root / "sync", root / "backup"
        self.conn = connect(":memory:")
        self.conn.execute("INSERT INTO agents(id, name) VALUES (1, '가')")
        self.conn.commit()
        f = self.sync / "가"
        self.a = write_wav(f / "01012345678_20261012_090000.wav", 2)
        self.b = write_wav(f / "sub" / "memo.wav", 1)  # 이름 해석 불가 → 백업만

    def tearDown(self):
        self.tmp.cleanup()

    def test_backup_and_clear(self):
        size = self.a.stat().st_size + self.b.stat().st_size
        r = backup.backup_and_clear(self.conn, 1, self.sync, self.bak, "admin")
        self.assertEqual((r["file_count"], r["total_bytes"]), (2, size))
        self.assertEqual((r["ingested"], r["unparsed"], r["left_recent"]), (1, 1, 0))
        # 비우기 전에 통화 기록으로 적재됨
        row = self.conn.execute("SELECT agent_id, started_at, duration_sec FROM calls").fetchone()
        self.assertEqual(tuple(row), (1, "2026-10-12 09:00:00", 2))
        with zipfile.ZipFile(r["archive_path"]) as zf:
            self.assertEqual(sorted(zf.namelist()), ["01012345678_20261012_090000.wav", "sub/memo.wav"])
        folder = self.sync / "가"
        self.assertTrue(folder.is_dir())  # 폴더 자체는 유지
        self.assertEqual(list(folder.iterdir()), [])
        hist = backup.history(self.conn, 1)
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["performed_by"], "admin")

    def test_empty_folder_refused(self):
        backup.backup_and_clear(self.conn, 1, self.sync, self.bak, "admin")
        with self.assertRaises(backup.BackupError):
            backup.backup_and_clear(self.conn, 1, self.sync, self.bak, "admin")
        self.assertEqual(len(backup.history(self.conn, 1)), 1)

    def test_path_outside_sync_root_refused(self):
        self.conn.execute("UPDATE agents SET sync_dir = '../../etc' WHERE id = 1")
        with self.assertRaises(backup.BackupError):
            backup.backup_and_clear(self.conn, 1, self.sync, self.bak, "admin")
        self.assertIn("error", backup.folder_status(self.conn, 1, self.sync))

    def test_files_still_syncing_are_left(self):
        fresh = write_wav(self.sync / "가" / "01099998888_20261012_100000.wav", 1, old=False)
        r = backup.backup_and_clear(self.conn, 1, self.sync, self.bak, "admin")
        self.assertEqual((r["file_count"], r["left_recent"]), (2, 1))
        self.assertTrue(fresh.exists())
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0], 1)

    def test_delete_permission_denied_still_records_backup(self):
        from unittest import mock
        with mock.patch.object(Path, "unlink", side_effect=PermissionError("denied")):
            r = backup.backup_and_clear(self.conn, 1, self.sync, self.bak, "admin")
        self.assertEqual((r["file_count"], r["delete_failed"]), (2, 2))
        self.assertTrue(Path(r["archive_path"]).exists())
        self.assertTrue(self.a.exists())
        self.assertEqual(len(backup.history(self.conn, 1)), 1)

    def test_folder_status(self):
        s = backup.folder_status(self.conn, 1, self.sync)
        self.assertEqual(s["file_count"], 2)


if __name__ == "__main__":
    unittest.main()
