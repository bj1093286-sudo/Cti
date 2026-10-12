"""녹취 파일의 재생 길이(초) 계산.

정확한 길이를 헤더에서 읽을 수 있는 형식은 헤더를 쓰고(WAV, M4A/MP4/3GP, MP3),
그 외 형식이나 헤더가 손상된 파일은 '파일 크기 / 비트레이트'로 추정한다.
"""
from __future__ import annotations

import struct
from pathlib import Path

AUDIO_EXTS = {".wav", ".m4a", ".mp4", ".3gp", ".3ga", ".aac", ".mp3", ".amr", ".ogg", ".opus", ".wma"}


def duration_sec(path: Path, fallback_kbps: int) -> tuple[float, str]:
    """(초, 'header' | 'size')."""
    ext = path.suffix.lower()
    reader = {".wav": _wav, ".m4a": _mp4, ".mp4": _mp4, ".3gp": _mp4, ".3ga": _mp4, ".mp3": _mp3}.get(ext)
    if reader is not None:
        try:
            with path.open("rb") as f:
                sec = reader(f, path.stat().st_size)
            if sec is not None and sec >= 0:
                return sec, "header"
        except (OSError, struct.error, ValueError):
            pass
    size = path.stat().st_size
    return size * 8 / (max(fallback_kbps, 1) * 1000), "size"


# ---------- WAV ----------
def _wav(f, size: int) -> float | None:
    head = f.read(12)
    if len(head) < 12 or head[:4] not in (b"RIFF", b"RF64") or head[8:12] != b"WAVE":
        return None
    byte_rate = None
    while True:
        ch = f.read(8)
        if len(ch) < 8:
            return None
        cid, csize = ch[:4], struct.unpack("<I", ch[4:])[0]
        if cid == b"fmt ":
            fmt = f.read(csize)
            byte_rate = struct.unpack("<I", fmt[8:12])[0]
            if csize % 2:
                f.read(1)
        elif cid == b"data":
            if not byte_rate:
                return None
            data = csize
            # 녹음 중 끊긴 파일은 크기 필드가 0 또는 0xFFFFFFFF — 실제 남은 바이트로 계산
            if data in (0, 0xFFFFFFFF) or f.tell() + data > size:
                data = size - f.tell()
            return data / byte_rate
        else:
            f.seek(csize + (csize % 2), 1)


# ---------- MP4 / M4A / 3GP ----------
def _boxes(f, end: int):
    while f.tell() + 8 <= end:
        start = f.tell()
        hdr = f.read(8)
        size, typ = struct.unpack(">I4s", hdr)
        hlen = 8
        if size == 1:
            size = struct.unpack(">Q", f.read(8))[0]
            hlen = 16
        elif size == 0:
            size = end - start
        if size < hlen:
            return
        yield typ, start + hlen, start + size
        f.seek(start + size)


def _mp4(f, size: int) -> float | None:
    for typ, body, end in _boxes(f, size):
        if typ != b"moov":
            continue
        f.seek(body)
        for t2, b2, _ in _boxes(f, end):
            if t2 != b"mvhd":
                continue
            f.seek(b2)
            version = f.read(4)[0]
            if version == 1:
                f.seek(16, 1)
                timescale, duration = struct.unpack(">IQ", f.read(12))
            else:
                f.seek(8, 1)
                timescale, duration = struct.unpack(">II", f.read(8))
            return duration / timescale if timescale else None
        return None
    return None


# ---------- MP3 ----------
_MP3_BITRATES = {  # (MPEG1?, layer) -> kbps 표
    (True, 3): [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    (False, 3): [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
}
_MP3_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def _mp3(f, size: int) -> float | None:
    start = 0
    head = f.read(10)
    if head[:3] == b"ID3":
        start = 10 + ((head[6] << 21) | (head[7] << 14) | (head[8] << 7) | head[9])
    f.seek(start)
    buf = f.read(64 * 1024)
    for i in range(len(buf) - 4):
        if buf[i] != 0xFF or (buf[i + 1] & 0xE0) != 0xE0:
            continue
        b1, b2, b3 = buf[i + 1], buf[i + 2], buf[i + 3]
        ver, layer = (b1 >> 3) & 3, (b1 >> 1) & 3
        br_idx, sr_idx = b2 >> 4, (b2 >> 2) & 3
        if ver == 1 or layer != 1 or br_idx in (0, 15) or sr_idx == 3:  # Layer III 만
            continue
        mpeg1 = ver == 3
        kbps = _MP3_BITRATES[(mpeg1, 3)][br_idx]
        sr = _MP3_RATES[ver][sr_idx]
        spf = 1152 if mpeg1 else 576
        # VBR(Xing/Info) 헤더가 있으면 프레임 수로 정확히 계산
        mono = (b3 >> 6) == 3
        side = (17 if mono else 32) if mpeg1 else (9 if mono else 17)
        x = buf[i + 4 + side: i + 4 + side + 12]
        if x[:4] in (b"Xing", b"Info") and struct.unpack(">I", x[4:8])[0] & 1:
            return struct.unpack(">I", x[8:12])[0] * spf / sr
        return (size - start - i) * 8 / (kbps * 1000)
    return None
