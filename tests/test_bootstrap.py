import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cti import auth
from cti.app import Config, bootstrap
from cti.db import connect


class BootstrapTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cfg = Config(root / "t.db", root / "sync", root / "bk")

    def tearDown(self):
        self.tmp.cleanup()
        auth._fails.clear()

    def login(self, u, p):
        conn = connect(self.cfg.db_path)
        try:
            return auth.login(conn, u, p)
        finally:
            conn.close()

    def test_env_admin_created_and_password_follows_env(self):
        with mock.patch.dict(os.environ, {"CTI_ADMIN_USER": "misomiso", "CTI_ADMIN_PASSWORD": "first-pass"}):
            bootstrap(self.cfg)
        self.assertTrue(self.login("misomiso", "first-pass"))
        with mock.patch.dict(os.environ, {"CTI_ADMIN_USER": "misomiso", "CTI_ADMIN_PASSWORD": "second-pass"}):
            bootstrap(self.cfg)
        self.assertIsNone(self.login("misomiso", "first-pass"))
        self.assertTrue(self.login("misomiso", "second-pass"))

    def test_demo_users_only_without_env(self):
        self.cfg.demo = True
        with mock.patch.dict(os.environ, {"CTI_ADMIN_PASSWORD": ""}):
            os.environ.pop("CTI_ADMIN_PASSWORD")
            bootstrap(self.cfg)
        self.assertTrue(self.login("admin", "admin1234"))


if __name__ == "__main__":
    unittest.main()
