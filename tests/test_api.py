import json
import tempfile
import threading
import unittest
from datetime import date
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from cti import auth
from cti.app import Config, make_handler
from cti.db import connect


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cfg = Config(root / "t.db", root / "sync", root / "backup", today=lambda: date(2026, 10, 12))
        conn = connect(cfg.db_path)
        conn.execute("INSERT INTO agents(id, name) VALUES (1, '가')")
        conn.execute("INSERT INTO calls(agent_id, customer_number, started_at, duration_sec) "
                     "VALUES (1, 'A', '2026-10-12 10:00:00', 60)")
        conn.commit()
        auth.create_user(conn, "admin", "pw-admin", "admin")
        auth.create_user(conn, "viewer", "pw-viewer", "viewer")
        conn.close()
        (cfg.sync_root / "1").mkdir(parents=True)
        (cfg.sync_root / "1" / "r.wav").write_bytes(b"z" * 10)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cfg))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def req(self, method, path, body=None, token=None):
        c = HTTPConnection("127.0.0.1", self.port)
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Cookie"] = f"cti_session={token}"
        c.request(method, path, json.dumps(body) if body is not None else None, headers)
        r = c.getresponse()
        data = r.read()
        cookie = r.getheader("Set-Cookie")
        c.close()
        try:
            data = json.loads(data)
        except ValueError:
            pass
        return r.status, data, cookie

    def login(self, user, pw):
        status, _, cookie = self.req("POST", "/api/login", {"username": user, "password": pw})
        self.assertEqual(status, 200)
        return cookie.split(";")[0].split("=", 1)[1]

    def test_requires_login(self):
        self.assertEqual(self.req("GET", "/api/dashboard")[0], 401)

    def test_bad_login(self):
        self.assertEqual(self.req("POST", "/api/login", {"username": "admin", "password": "x"})[0], 401)

    def test_dashboard(self):
        t = self.login("viewer", "pw-viewer")
        status, d, _ = self.req("GET", "/api/dashboard?preset=today", token=t)
        self.assertEqual(status, 200)
        self.assertEqual(d["kpis"]["total_calls"]["value"], 1)
        self.assertEqual(d["prev_period"]["start"], "2026-10-11")

    def test_bad_params(self):
        t = self.login("viewer", "pw-viewer")
        self.assertEqual(self.req("GET", "/api/dashboard?preset=nope", token=t)[0], 400)
        self.assertEqual(self.req("GET", "/api/dashboard?preset=custom&start=x&end=y", token=t)[0], 400)
        self.assertEqual(self.req("GET", "/api/dashboard?agent_id=abc", token=t)[0], 400)

    def test_viewer_cannot_see_or_run_backup(self):
        t = self.login("viewer", "pw-viewer")
        status, d, _ = self.req("GET", "/api/agents/1?preset=today", token=t)
        self.assertEqual(status, 200)
        self.assertNotIn("sync_folder", d)
        self.assertNotIn("backups", d)
        self.assertEqual(self.req("POST", "/api/agents/1/backup", {}, token=t)[0], 403)

    def test_admin_backup_flow(self):
        t = self.login("admin", "pw-admin")
        status, d, _ = self.req("GET", "/api/agents/1?preset=today", token=t)
        self.assertEqual(d["sync_folder"]["file_count"], 1)
        status, r, _ = self.req("POST", "/api/agents/1/backup", {}, token=t)
        self.assertEqual(status, 200, r)
        self.assertEqual(r["sync_folder"]["file_count"], 0)
        self.assertEqual(len(r["backups"]), 1)
        # 다시 실행하면 빈 폴더라 409
        self.assertEqual(self.req("POST", "/api/agents/1/backup", {}, token=t)[0], 409)

    def test_static_and_traversal(self):
        self.assertEqual(self.req("GET", "/")[0], 200)
        self.assertEqual(self.req("GET", "/static/app.js")[0], 200)
        self.assertEqual(self.req("GET", "/static/../cti/app.py")[0], 404)


if __name__ == "__main__":
    unittest.main()
