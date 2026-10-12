"""사용자 계정 만들기 / 비밀번호 바꾸기.

사용:
  python -m scripts.create_user              # 대화형으로 계정 추가(같은 아이디면 비밀번호·권한 변경)
  python -m scripts.create_user --if-none    # 계정이 하나도 없을 때만 관리자 계정 만들기(첫 실행용)
"""
from __future__ import annotations

import argparse
import getpass
import sys

from cti import auth
from cti.app import Config
from cti.db import connect

MIN_PASSWORD = 8


def ask_password() -> str:
    while True:
        pw = getpass.getpass(f"비밀번호({MIN_PASSWORD}자 이상, 입력해도 화면에 안 보입니다): ")
        if len(pw) < MIN_PASSWORD:
            print(f"  {MIN_PASSWORD}자 이상으로 입력하세요.")
            continue
        if getpass.getpass("비밀번호 한 번 더: ") != pw:
            print("  두 비밀번호가 다릅니다. 다시 입력하세요.")
            continue
        return pw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--if-none", action="store_true", help="계정이 없을 때만 관리자 계정 생성")
    args = ap.parse_args()

    cfg = Config.from_env()
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(cfg.db_path)
    has_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0
    if args.if_none and has_users:
        return 0

    try:
        if args.if_none:
            print("처음 실행입니다. 관리자 계정을 만듭니다.")
            username, role = (input("관리자 아이디: ").strip() or "admin"), "admin"
        else:
            username = input("아이디: ").strip()
            role = "admin" if input("관리자 권한을 줄까요? (y/N): ").strip().lower() == "y" else "viewer"
        if not username:
            print("아이디를 입력하세요.")
            return 1
        auth.create_user(conn, username, ask_password(), role)
    except (KeyboardInterrupt, EOFError):
        print("\n취소했습니다.")
        return 1
    print(f"계정 '{username}'({'관리자' if role == 'admin' else '조회'})을(를) 저장했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
