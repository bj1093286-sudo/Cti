import struct
import tempfile
import unittest
from pathlib import Path

from cti.audio import duration_sec
from tests.helpers import write_m4a, write_wav


class DurationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_wav_header(self):
        f = write_wav(self.dir / "a.wav", 12.5)
        self.assertEqual(duration_sec(f, 64), (12.5, "header"))

    def test_wav_truncated_size_field(self):
        f = write_wav(self.dir / "b.wav", 3)
        raw = bytearray(f.read_bytes())
        raw[40:44] = struct.pack("<I", 0xFFFFFFFF)  # 녹음 중 끊긴 파일
        f.write_bytes(raw)
        self.assertEqual(duration_sec(f, 64), (3.0, "header"))

    def test_m4a_mvhd_v0_and_v1(self):
        self.assertEqual(duration_sec(write_m4a(self.dir / "c.m4a", 95.0), 64), (95.0, "header"))
        self.assertEqual(duration_sec(write_m4a(self.dir / "d.m4a", 7.0, 1000, version=1), 64), (7.0, "header"))

    def test_mp3_cbr(self):
        # MPEG1 Layer III 128kbps 44.1kHz 프레임 헤더 + 데이터: 16000 B/s → 2초
        frame = bytes([0xFF, 0xFB, 0x90, 0x00])
        f = self.dir / "e.mp3"
        f.write_bytes(frame + bytes(32000 - 4))
        sec, how = duration_sec(f, 64)
        self.assertEqual(how, "header")
        self.assertAlmostEqual(sec, 2.0)

    def test_fallback_by_size(self):
        f = self.dir / "f.amr"
        f.write_bytes(bytes(8000))  # 8000 B = 64000 bit → 64kbps 에서 1초
        self.assertEqual(duration_sec(f, 64), (1.0, "size"))

    def test_broken_header_falls_back(self):
        f = self.dir / "g.m4a"
        f.write_bytes(b"garbage" * 1000)
        self.assertEqual(duration_sec(f, 56)[1], "size")


if __name__ == "__main__":
    unittest.main()
