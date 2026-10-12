"""Postgres(Vercel 운영 DB)에서도 SQLite 와 똑같이 동작하는지 확인.

CTI_TEST_DATABASE_URL 이 있을 때만 실행된다. 예:
  CTI_TEST_DATABASE_URL=postgresql://postgres@/cti_test?host=/tmp/cti-pg&port=54329
"""
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

from cti import auth, backup, dashboard, demo, ingest
from cti.db import connect
from cti.periods import resolve
from tests.helpers import write_wav

URL = os.environ.get("CTI_TEST_DATABASE_URL")


def fresh_pg():
    import psycopg
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    import cti.db
    cti.db._pg_ready.discard(URL)
    return connect(URL)


@unittest.skipUnless(URL, "CTI_TEST_DATABASE_URL 없음")
class PostgresParityTest(unittest.TestCase):
    maxDiff = None

    def test_dashboard_matches_sqlite(self):
        pg, lite = fresh_pg(), connect(":memory:")
        for c in (pg, lite):
            demo.seed(c, days=20)
        today = date.today()
        for preset in ("today", "this_week", "this_month"):
            cur, prev = resolve(preset, today)
            for agent in (None, 2):
                a = dashboard.build(pg, cur, prev, agent)
                b = dashboard.build(lite, cur, prev, agent)
                self.assertEqual(a, b, (preset, agent))
        pg_n = pg.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
        self.assertEqual(pg_n, lite.execute("SELECT COUNT(*) FROM calls").fetchone()[0])
        a = dashboard.agent_detail(pg, 1, resolve("this_month", today)[0], 10)
        b = dashboard.agent_detail(lite, 1, resolve("this_month", today)[0], 10)
        for d in (a, b):
            for r in d["recent_calls"]:
                r.pop("id")
        self.assertEqual(a, b)
        pg.close()
        lite.close()

    def test_ingest_backup_auth(self):
        pg = fresh_pg()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sync"
            write_wav(root / "가" / "통화 녹음 010-1111-2222_261012_090000.wav", 12)
            write_wav(root / "가" / "통화 녹음 16004112_260724_140102.wav", 3)
            s = ingest.ingest_all(pg, root)
            self.assertEqual(s["added"], 2)
            self.assertEqual(ingest.ingest_all(pg, root)["already"], 2)  # 중복 적재 없음
            agent_id = pg.execute("SELECT id FROM agents WHERE name = '가'").fetchone()[0]
            r = backup.backup_and_clear(pg, agent_id, root, Path(tmp) / "bk", "admin")
            self.assertEqual(r["file_count"], 2)
            self.assertIsInstance(r["id"], int)
            self.assertEqual(len(backup.history(pg, agent_id)), 1)
        auth.create_user(pg, "admin", "pw-123456", "admin")
        auth.create_user(pg, "admin", "pw-654321", "admin")  # 같은 아이디 → 비밀번호 변경
        self.assertIsNone(auth.login(pg, "admin", "pw-123456"))
        token = auth.login(pg, "admin", "pw-654321")
        self.assertEqual(auth.user_for_token(pg, token)["role"], "admin")
        auth._fails.clear()
        pg.close()


@unittest.skipUnless(URL, "CTI_TEST_DATABASE_URL 없음")
class PostgresCallsTest(unittest.TestCase):
    def test_search_matches_sqlite(self):
        from cti import calls
        recs = [{"id": f"f{i}", "agent": ["가", "나"][i % 2], "size": 1000, "durationMs": i * 7000,
                 "name": f"통화 녹음 010-1111-{2000 + i % 3}_2610{10 + i % 3}_0900{i:02d}.mp4"} for i in range(30)]
        pg, lite = fresh_pg(), connect(":memory:")
        for c in (pg, lite):
            ingest.ingest_records(c, recs)
        for kw in ({"q": "010-1111-2001"}, {"q": "2002"}, {"q": "나"}, {"min_sec": 100}, {}):
            a = calls.search(pg, None, limit=7, **kw)
            b = calls.search(lite, None, limit=7, **kw)
            strip = lambda r: [(i["started_at"], i["agent_name"], i["customer_masked"], i["duration_sec"]) for i in r["items"]]
            self.assertEqual((a["total"], strip(a)), (b["total"], strip(b)), kw)
            if a["next_cursor"]:
                a2 = calls.search(pg, None, limit=7, cursor=a["next_cursor"], **kw)
                b2 = calls.search(lite, None, limit=7, cursor=b["next_cursor"], **kw)
                self.assertEqual(strip(a2), strip(b2), kw)
        pg.close(); lite.close()


if __name__ == "__main__":
    unittest.main()
