import io
import json
import unittest
import urllib.error
from unittest import mock

from cti import app
from cti.db import connect, set_setting

URL = "https://script.google.com/macros/s/AKfycbx_TEST-123/exec"


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class SyncNowTest(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")

    def tearDown(self):
        self.conn.close()

    def test_needs_url(self):
        with self.assertRaises(app.ApiError) as cm:
            app.drive_sync_now(self.conn)
        self.assertIn("웹 앱 URL", str(cm.exception))

    def test_webapp_url_shape(self):
        self.assertTrue(app.WEBAPP_RE.fullmatch(URL))
        self.assertTrue(app.WEBAPP_RE.fullmatch("https://script.google.com/a/macros/miso.kr/s/AKfy-x_1/exec"))
        self.assertFalse(app.WEBAPP_RE.fullmatch("https://evil.example.com/macros/s/x/exec"))

    def test_calls_webapp_with_token(self):
        set_setting(self.conn, "drive_webapp_url", URL)
        seen = {}

        def fake(url, timeout):
            seen["url"] = url
            return Resp(json.dumps({"ok": True, "added": 3, "backups": 1, "more": False}).encode())
        with mock.patch("urllib.request.urlopen", fake):
            r = app.drive_sync_now(self.conn)
        self.assertEqual((r["added"], r["backups"]), (3, 1))
        self.assertIn("token=" + app.drive_token(self.conn), seen["url"])

    def test_busy_and_errors(self):
        set_setting(self.conn, "drive_webapp_url", URL)
        with mock.patch("urllib.request.urlopen", lambda u, timeout: Resp(b'{"ok": false, "busy": true, "error": "x"}')):
            with self.assertRaises(app.ApiError) as cm:
                app.drive_sync_now(self.conn)
            self.assertEqual(cm.exception.status, 409)
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            with self.assertRaises(app.ApiError) as cm:
                app.drive_sync_now(self.conn)
            self.assertEqual(cm.exception.status, 502)
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError()):
            self.assertTrue(app.drive_sync_now(self.conn)["pending"])


if __name__ == "__main__":
    unittest.main()
