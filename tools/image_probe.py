"""只读文件头拿尺寸，不解码像素。"""
from __future__ import annotations

import struct
from pathlib import Path

_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _png(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or not data.startswith(_PNG_SIG):
        return (0, 0)
    w, h = struct.unpack(">II", data[16:24])
    return (int(w), int(h))


def _gif(data: bytes) -> tuple[int, int]:
    if len(data) < 10:
        return (0, 0)
    w, h = struct.unpack("<HH", data[6:10])
    return (int(w), int(h))


def _jpeg(data: bytes) -> tuple[int, int]:
    i = 2
    n = len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0xD9):
            i += 2
            continue
        if i + 4 > n:
            break
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if i + 9 <= n:
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return (int(w), int(h))
            return (0, 0)
        if length < 2:
            break
        i += 2 + length
    return (0, 0)


def _webp(data: bytes) -> tuple[int, int]:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return (0, 0)
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        w = 1 + int.from_bytes(data[24:27], "little")
        h = 1 + int.from_bytes(data[27:30], "little")
        return (w, h)
    if chunk == b"VP8L" and len(data) >= 25:
        bits = int.from_bytes(data[21:25], "little")
        return (1 + (bits & 0x3FFF), 1 + ((bits >> 14) & 0x3FFF))
    if chunk == b"VP8 " and len(data) >= 30:
        w = int.from_bytes(data[26:28], "little") & 0x3FFF
        h = int.from_bytes(data[28:30], "little") & 0x3FFF
        return (w, h)
    return (0, 0)


def probe(path: Path) -> tuple[int, int]:
    try:
        with open(path, "rb") as fh:
            data = fh.read(262144)
    except OSError:
        return (0, 0)
    suffix = path.suffix.casefold()
    if suffix == ".png":
        return _png(data)
    if suffix == ".gif":
        return _gif(data)
    if suffix in (".jpg", ".jpeg"):
        return _jpeg(data)
    if suffix == ".webp":
        return _webp(data)
    return (0, 0)
