import json
import struct
from pathlib import Path

from dds_normal_cache import rewrite_entry, dds_info, png_size


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
