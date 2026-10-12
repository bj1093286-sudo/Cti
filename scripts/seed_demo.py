"""데모 데이터 생성: 상담원, 최근 70일 통화, 사용자(admin/viewer), 동기화 폴더 샘플 파일.

사용: python -m scripts.seed_demo [--reset]
"""
from __future__ import annotations

import argparse
import random
from datetime import date, datetime, timedelta

from cti import auth
from cti.app import Config
from cti.db import connect

AGENTS = [("김민지", "1001"), ("이서준", "1002"), ("박지우", "1003"),
          ("최하은", "1004"), ("정도윤", "1005"), ("강수아", "1006")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="기존 DB를 지우고 다시 생성")
    ap.add_argument("--days", type=int, default=70)
    args = ap.parse_args()

    cfg = Config.from_env()
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    if args.reset and cfg.db_path.exists():
        cfg.db_path.unlink()
    conn = connect(cfg.db_path)
    rnd = random.Random(42)

    if conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0] == 0:
        conn.executemany("INSERT INTO agents(name, extension) VALUES (?, ?)", AGENTS)
    agents = [r[0] for r in conn.execute("SELECT id FROM agents")]
    skill = {a: rnd.uniform(0.7, 1.3) for a in agents}
    customers = [f"010{rnd.randint(10000000, 99999999)}" for _ in range(900)]

    conn.execute("DELETE FROM calls")
    rows = []
    today = date.today()
    hour_w = [0, 0, 0, 0, 0, 0, 0, 0.2, 0.6, 1.0, 1.1, 0.9, 0.4, 0.8, 1.0, 1.0, 0.9, 0.6, 0.2, 0.1, 0, 0, 0, 0]
    for back in range(args.days, -1, -1):
        d = today - timedelta(days=back)
        weekend = d.weekday() >= 5
        for a in agents:
            if weekend and rnd.random() < 0.8:
                continue
            n = int(rnd.gauss(38, 8) * skill[a] * (0.3 if weekend else 1))
            for _ in range(max(n, 0)):
                h = rnd.choices(range(24), weights=hour_w)[0]
                ts = datetime(d.year, d.month, d.day, h, rnd.randint(0, 59), rnd.randint(0, 59))
                if d == today and ts > datetime.now():
                    continue
                dur = rnd.randint(1, 9) if rnd.random() < 0.12 else int(rnd.lognormvariate(5.0, 0.6))
                rows.append((a, rnd.choice(customers), rnd.choice(["in", "in", "out"]),
                             ts.isoformat(sep=" "), dur))
    conn.executemany(
        "INSERT INTO calls(agent_id, customer_number, direction, started_at, duration_sec) "
        "VALUES (?, ?, ?, ?, ?)", rows)
    conn.commit()

    auth.create_user(conn, "admin", "admin1234", "admin")
    auth.create_user(conn, "viewer", "viewer1234", "viewer")

    for a in agents:
        folder = cfg.sync_root / str(a)
        folder.mkdir(parents=True, exist_ok=True)
        for i in range(rnd.randint(2, 6)):
            (folder / f"rec_{a}_{i:03d}.wav").write_bytes(rnd.randbytes(rnd.randint(2_000, 40_000)))

    print(f"상담원 {len(agents)}명, 통화 {len(rows)}건 생성 → {cfg.db_path}")
    print("로그인: admin / admin1234 (관리자), viewer / viewer1234 (조회)")


if __name__ == "__main__":
    main()
