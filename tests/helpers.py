import os
import struct
import time
from pathlib import Path


def write_wav(path: Path, seconds: float, rate: int = 8000, old: bool = True) -> Path:
    """8비트 모노 PCM WAV. old=True 면 수정 시각을 과거로 돌려 '동기화 완료' 상태로 만든다."""
    data = bytes([128]) * int(seconds * rate)
    hdr = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    hdr += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate, 1, 8)
    hdr += b"data" + struct.pack("<I", len(data))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(hdr + data)
    if old:
        t = time.time() - 3600
        os.utime(path, (t, t))
    return path


def write_m4a(path: Path, seconds: float, timescale: int = 44100, version: int = 0) -> Path:
    """ftyp + mdat + moov/mvhd 만 있는 최소 MP4 (moov가 뒤에 있는 흔한 구조)."""
    def box(typ, body):
        return struct.pack(">I4s", 8 + len(body), typ) + body
    dur = int(seconds * timescale)
    if version == 1:
        mvhd = bytes([1, 0, 0, 0]) + struct.pack(">QQIQ", 0, 0, timescale, dur) + bytes(80)
    else:
        mvhd = bytes(4) + struct.pack(">IIII", 0, 0, timescale, dur) + bytes(80)
    data = box(b"ftyp", b"M4A \x00\x00\x00\x00") + box(b"mdat", bytes(1000)) + box(b"moov", box(b"mvhd", mvhd))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    t = time.time() - 3600
    os.utime(path, (t, t))
    return path
