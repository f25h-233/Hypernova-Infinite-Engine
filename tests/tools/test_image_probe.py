import struct

from image_probe import probe


def test_png(tmp_path):
    p = tmp_path / "a.png"
    p.write_bytes(
        b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
        + struct.pack(">II", 640, 480) + b"\x08\x06\x00\x00\x00" + b"\x00" * 4
    )
    assert probe(p) == (640, 480)


def test_jpeg(tmp_path):
    p = tmp_path / "a.jpg"
    sof = b"\xff\xc0" + struct.pack(">H", 11) + b"\x08" + struct.pack(">HH", 200, 300) + b"\x03" + b"\x00" * 6
    p.write_bytes(b"\xff\xd8" + sof + b"\xff\xd9")
    assert probe(p) == (300, 200)


def test_gif(tmp_path):
    p = tmp_path / "a.gif"
    p.write_bytes(b"GIF89a" + struct.pack("<HH", 12, 34))
    assert probe(p) == (12, 34)


def test_unknown_returns_zero(tmp_path):
    p = tmp_path / "a.bin"
    p.write_bytes(b"nonsense")
    assert probe(p) == (0, 0)
