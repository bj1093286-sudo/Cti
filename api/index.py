"""Vercel 서버리스 진입점 — /api/* 요청을 처리한다(정적 파일은 Vercel이 직접 제공).

Vercel 은 이 파일에서 최상위 `class handler(BaseHTTPRequestHandler)` 를 찾는다.
"""
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cti.app import Config, bootstrap, make_handler  # noqa: E402

_cfg = Config.from_env()
bootstrap(_cfg)
_AppHandler = make_handler(_cfg)


class handler(_AppHandler, BaseHTTPRequestHandler):
    pass
