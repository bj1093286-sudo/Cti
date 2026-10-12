import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from cti.app import Config, make_handler


class SetupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Config(root / "t.db", root / "s", root / "b")))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown(); self.httpd.server_close(); self.tmp.cleanup()

    def req(self, method, path, body=None):
        c = HTTPConnection("127.0.0.1", self.httpd.server_address[1])
        c.request(method, path, json.dumps(body) if body is not None else None,
                  {"Content-Type": "application/json"} if body is not None else {})
        r = c.getresponse(); data = json.loads(r.read() or b"{}"); cookie = r.getheader("Set-Cookie"); c.close()
        return r.status, data, cookie

    def test_first_run_setup_once(self):
        status, s, _ = self.req("GET", "/api/status")
        self.assertEqual((status, s["needs_setup"], s["storage"]), (200, True, "local"))
        self.assertEqual(self.req("POST", "/api/setup", {"username": "a b", "password": "miso1234"})[0], 400)
        self.assertEqual(self.req("POST", "/api/setup", {"username": "misomiso", "password": "short"})[0], 400)
        status, u, cookie = self.req("POST", "/api/setup", {"username": "misomiso", "password": "miso1234"})
        self.assertEqual((status, u["username"], u["role"]), (200, "misomiso", "admin"))
        self.assertIn("cti_session=", cookie)
        self.assertFalse(self.req("GET", "/api/status")[1]["needs_setup"])
        # 계정이 생긴 뒤에는 누구도 다시 만들 수 없음
        self.assertEqual(self.req("POST", "/api/setup", {"username": "hacker", "password": "12345678"})[0], 409)
        self.assertEqual(self.req("POST", "/api/login", {"username": "misomiso", "password": "miso1234"})[0], 200)


if __name__ == "__main__":
    unittest.main()
