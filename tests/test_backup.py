import tempfile
import unittest
import zipfile
from pathlib import Path

from cti import backup
from cti.db import connect


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.sync, self.bak = root / "sync", root / "backup"
        self.conn = connect(":memory:")
        self.conn.execute("INSERT INTO agents(id, name) VALUES (1, '가')")
        self.conn.commit()
        f = self.sync / "1"
        (f / "sub").mkdir(parents=True)
        (f / "a.wav").write_bytes(b"x" * 100)
        (f / "sub" / "b.wav").write_bytes(b"y" * 50)

    def tearDown(self):
        self.tmp.cleanup()

    def test_backup_and_clear(self):
        r = backup.backup_and_clear(self.conn, 1, self.sync, self.bak, "admin")
        self.assertEqual(r["file_count"], 2)
        self.assertEqual(r["total_bytes"], 150)
        with zipfile.ZipFile(r["archive_path"]) as zf:
            self.assertEqual(sorted(zf.namelist()), ["a.wav", "sub/b.wav"])
        folder = self.sync / "1"
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

    def test_folder_status(self):
        s = backup.folder_status(self.conn, 1, self.sync)
        self.assertEqual((s["file_count"], s["total_bytes"]), (2, 150))


if __name__ == "__main__":
    unittest.main()
