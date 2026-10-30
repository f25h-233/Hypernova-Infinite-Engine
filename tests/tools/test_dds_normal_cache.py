import json
import struct
from argparse import Namespace
from pathlib import Path

from dds_normal_cache import (
    cmd_adopt,
    cmd_verify,
    dds_info,
    png_size,
    rewrite_entry,
)


def test_rewrite_entry_maps_staging_path_to_graphicslib_cache():
    entry = {
        "ModID": "hypernova_dds_staging",
        "ModFolderName": "hypernova_dds_staging",
        "RelativeImagePath": "graphics\\normalcache\\foo___SHIP_normal.png",
        "DDSFilePath": "\\mods\\DDSCache\\hypernova_dds_staging\\graphics\\normalcache\\foo___SHIP_normal.dds",
        "CompressionFormat": "BC7",
        "Width": 256,
        "Height": 128,
    }
    out = rewrite_entry(entry)
    assert out["ModFolderName"] == "GraphicsLib"
    assert out["RelativeImagePath"] == "cache\\foo___SHIP_normal.png"
    assert out["DDSFilePath"] == "\\mods\\DDSCache\\GraphicsLib\\cache\\foo___SHIP_normal.dds"
    assert out["CompressionFormat"] == "BC7"


def test_dds_info_rejects_non_bc7(tmp_path):
    p = tmp_path / "x.dds"
    data = bytearray(148)
    data[0:4] = b"DDS "
    struct.pack_into("<I", data, 4, 124)
    struct.pack_into("<I", data, 12, 64)    # height
    struct.pack_into("<I", data, 16, 128)   # width
    data[84:88] = b"DX10"
    struct.pack_into("<I", data, 128, 98)   # DXGI_FORMAT_BC7_UNORM
    p.write_bytes(data)
    info = dds_info(p)
    assert info["width"] == 128 and info["height"] == 64 and info["dxgiFormat"] == 98

    data[128:132] = struct.pack("<I", 71)   # BC1
    p.write_bytes(data)
    assert dds_info(p)["dxgiFormat"] == 71


def test_png_size_reads_ihdr(tmp_path):
    p = tmp_path / "x.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
                  + struct.pack(">II", 200, 100) + b"\x08\x06\x00\x00\x00")
    assert png_size(p) == (200, 100)


def _png_bytes(w: int, h: int) -> bytes:
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
            + struct.pack(">II", w, h) + b"\x08\x06\x00\x00\x00")


def _dds_bytes(w: int, h: int, dxgi: int = 98) -> bytes:
    data = bytearray(148)
    data[0:4] = b"DDS "
    struct.pack_into("<I", data, 4, 124)
    struct.pack_into("<I", data, 12, h)
    struct.pack_into("<I", data, 16, w)
    data[84:88] = b"DX10"
    struct.pack_into("<I", data, 128, dxgi)
    return bytes(data)


def _game_with_cache_entry(tmp_path, png_wh, dds_wh):
    game = tmp_path / "game"
    dds = game / "mods" / "DDSCache" / "GraphicsLib" / "cache" / "foo___SHIP_normal.dds"
    dds.parent.mkdir(parents=True)
    dds.write_bytes(_dds_bytes(*dds_wh))
    png = game / "mods" / "GraphicsLib" / "cache" / "foo___SHIP_normal.png"
    png.parent.mkdir(parents=True)
    png.write_bytes(_png_bytes(*png_wh))
    meta = [{
        "ModID": "GraphicsLib",
        "ModFolderName": "GraphicsLib",
        "RelativeImagePath": "cache\\foo___SHIP_normal.png",
        "DDSFilePath": "\\mods\\DDSCache\\GraphicsLib\\cache\\foo___SHIP_normal.dds",
        "CompressionFormat": "BC7",
        "Width": dds_wh[0],
        "Height": dds_wh[1],
    }]
    (dds.parent.parent / "dds_metadata.json").write_text(
        json.dumps(meta), encoding="utf-8")
    return game


def test_verify_flags_png_dds_size_mismatch(tmp_path):
    game = _game_with_cache_entry(tmp_path, (64, 32), (128, 64))
    assert cmd_verify(Namespace(game=game)) == 1


def test_verify_accepts_matching_png_and_dds_size(tmp_path):
    game = _game_with_cache_entry(tmp_path, (128, 64), (128, 64))
    assert cmd_verify(Namespace(game=game)) == 0


def test_adopt_missing_staging_metadata_fails_closed(tmp_path):
    game = tmp_path / "game"
    meta_path = game / "mods" / "DDSCache" / "GraphicsLib" / "dds_metadata.json"
    meta_path.parent.mkdir(parents=True)
    sentinel = b'[{"keep": true}]\n'
    meta_path.write_bytes(sentinel)
    assert cmd_adopt(Namespace(game=game, dry_run=False)) == 2
    assert meta_path.read_bytes() == sentinel
