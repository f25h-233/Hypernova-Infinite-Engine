#!/usr/bin/env python3
"""可选 DDS 路线：用现成 DDSCreator 烘焙 GraphicsLib 法线缓存，再改写成 FR 能读的布局。

DDSCreator.exe 明确跳过 shaderLib 的 cache/ 和 graphics/shaders/。绕法：
把法线 PNG 硬链接到一个普通 mod 的 graphics/normalcache/ 下，让 DDSCreator
按普通 mod 烘焙；adopt 再把 metadata 的 ModFolderName/RelativeImagePath/
DDSFilePath 改回 GraphicsLib/cache，并把 DDS 放到 DDSCache/GraphicsLib/cache/。

不自动运行 DDSCreator（它是交互式 TUI）；prepare 打印手工步骤。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import sys
from pathlib import Path

STAGING = "hypernova_dds_staging"
NORMAL_SUBDIR = "graphics/normalcache"
BC7_DXGI = 98


def game_paths(game: Path) -> tuple[Path, Path]:
    mods = game / "mods"
    return mods / "GraphicsLib/cache", mods


def dds_info(path: Path) -> dict:
    data = path.read_bytes()[:148]
    if len(data) < 148 or data[0:4] != b"DDS ":
        raise ValueError(f"not a DDS file: {path}")
    height, width = struct.unpack_from("<II", data, 12)
    fourcc = data[84:88]
    dxgi = struct.unpack_from("<I", data, 128)[0] if fourcc == b"DX10" else None
    return {"width": width, "height": height, "fourcc": fourcc.decode("ascii", "replace"),
            "dxgiFormat": dxgi}


def png_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ValueError(f"not a PNG file: {path}")
    return struct.unpack(">II", head[16:24])


def rewrite_entry(entry: dict) -> dict:
    rel = entry["RelativeImagePath"].replace("/", "\\")
    name = rel.rsplit("\\", 1)[-1]
    if not name.endswith(".png"):
        raise ValueError(f"unexpected RelativeImagePath: {rel}")
    dds_name = name[:-4] + ".dds"
    out = dict(entry)
    out["ModID"] = "GraphicsLib"
    out["ModFolderName"] = "GraphicsLib"
    out["RelativeImagePath"] = "cache\\" + name
    out["DDSFilePath"] = "\\mods\\DDSCache\\GraphicsLib\\cache\\" + dds_name
    return out


def cmd_prepare(args) -> int:
    cache_dir, mods = game_paths(args.game)
    staging = mods / STAGING
    target = staging / NORMAL_SUBDIR
    if not cache_dir.is_dir():
        print(f"missing {cache_dir}", file=sys.stderr)
        return 2
    target.mkdir(parents=True, exist_ok=True)
    (staging / "mod_info.json").write_text(json.dumps({
        "id": STAGING, "name": "Hypernova DDS staging", "author": "Hypernova",
        "version": "0.1.0", "gameVersion": "0.98a-RC8",
        "description": "Temporary normal-map staging for DDSCreator.", "jars": [],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    pngs = sorted(cache_dir.glob("*_normal.png"))
    if args.limit:
        pngs = pngs[: args.limit]
    linked = copied = 0
    for src in pngs:
        dst = target / src.name
        if dst.exists():
            continue
        if args.copy:
            shutil.copy2(src, dst)
            copied += 1
        else:
            try:
                os.link(src, dst)
                linked += 1
            except OSError:
                shutil.copy2(src, dst)
                copied += 1
    print(f"staged {len(pngs)} PNGs ({linked} hardlinks, {copied} copies) -> {target}")
    print()
    print("下一步（人工）：")
    print("  1. 在 260mods 的 mod 列表里启用 hypernova_dds_staging（DDSCreator 只处理已启用 mod）。")
    print("  2. 运行 VramOptimizer/bin/DDSCreator.exe，选择 Process Mods，等它完成。")
    print("  3. 确认 mods/DDSCache/hypernova_dds_staging/dds_metadata.json 存在。")
    print("  4. 运行: python tools/dds_normal_cache.py adopt")
    print("  5. adopt 完成后禁用 staging mod；它只用于烘焙。")
    return 0


def cmd_adopt(args) -> int:
    cache_dir, mods = game_paths(args.game)
    dds_dir = mods / "DDSCache/GraphicsLib/cache"
    staging_meta = mods / "DDSCache" / STAGING / "dds_metadata.json"
    if not staging_meta.is_file():
        print(f"missing {staging_meta}; run DDSCreator first", file=sys.stderr)
        return 2
    entries = json.loads(staging_meta.read_text(encoding="utf-8"))
    rewritten = []
    for entry in entries:
        rel = entry.get("RelativeImagePath", "")
        if not rel.replace("/", "\\").startswith("graphics\\normalcache\\"):
            continue
        out = rewrite_entry(entry)
        # 从原 entry 的 DDSFilePath 推导 staging 侧路径：
        # \mods\DDSCache\hypernova_dds_staging\graphics\normalcache\foo.dds
        src_dds = mods / "DDSCache" / STAGING / Path(
            entry["DDSFilePath"].split("\\" + STAGING + "\\", 1)[-1].replace("\\", "/"))
        dst_dds = dds_dir / out["DDSFilePath"].split("\\")[-1]
        if not src_dds.is_file():
            print(f"missing DDS {src_dds}", file=sys.stderr)
            return 2
        info = dds_info(src_dds)
        if info["dxgiFormat"] != BC7_DXGI:
            print(f"not BC7: {src_dds} ({info})", file=sys.stderr)
            return 2
        src_png = cache_dir / Path(out["RelativeImagePath"].replace("\\", "/")).name
        if src_png.is_file():
            w, h = png_size(src_png)
            if (w, h) != (info["width"], info["height"]):
                print(f"size mismatch {src_png}: png={w}x{h} dds={info['width']}x{info['height']}",
                      file=sys.stderr)
                return 2
        rewritten.append((src_dds, dst_dds, out))
    if not rewritten:
        print("no staging entries found; check DDSCreator skip rules", file=sys.stderr)
        return 2
    if args.dry_run:
        print(f"dry-run: would adopt {len(rewritten)} normals")
        for _, _, out in rewritten[:5]:
            print("  ", out["RelativeImagePath"], "->", out["DDSFilePath"])
        return 0
    dds_dir.mkdir(parents=True, exist_ok=True)
    (mods / "DDSCache/GraphicsLib").mkdir(parents=True, exist_ok=True)
    meta_path = mods / "DDSCache/GraphicsLib/dds_metadata.json"
    existing = []
    if meta_path.is_file():
        existing = [e for e in json.loads(meta_path.read_text(encoding="utf-8"))
                    if not e.get("RelativeImagePath", "").replace("/", "\\").startswith("cache\\")]
    for src, dst, _ in rewritten:
        if dst.exists():
            dst.unlink()
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)
    meta = existing + [out for _, _, out in rewritten]
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"adopted {len(rewritten)} normals -> {dds_dir} (metadata {meta_path})")
    print("现在禁用 hypernova_dds_staging，重启游戏。")
    return 0


def cmd_verify(args) -> int:
    _, mods = game_paths(args.game)
    meta_path = mods / "DDSCache/GraphicsLib/dds_metadata.json"
    if not meta_path.is_file():
        print(f"missing {meta_path}", file=sys.stderr)
        return 2
    entries = [e for e in json.loads(meta_path.read_text(encoding="utf-8"))
               if e.get("RelativeImagePath", "").replace("/", "\\").startswith("cache\\")]
    bad = 0
    for e in entries:
        dds = mods / "DDSCache/GraphicsLib" / Path(e["DDSFilePath"].split("GraphicsLib\\", 1)[-1].replace("\\", "/"))
        if not dds.is_file():
            bad += 1
            print("missing", dds, file=sys.stderr)
            continue
        info = dds_info(dds)
        if info["dxgiFormat"] != BC7_DXGI:
            bad += 1
            print("not BC7", dds, info, file=sys.stderr)
    print(f"verified {len(entries)} entries, {bad} bad")
    return 0 if bad == 0 else 1


def main() -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--game", default="Starsector-098-260mods")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare", parents=[common])
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--copy", action="store_true")
    p.set_defaults(func=cmd_prepare)
    a = sub.add_parser("adopt", parents=[common])
    a.add_argument("--dry-run", action="store_true")
    a.set_defaults(func=cmd_adopt)
    v = sub.add_parser("verify", parents=[common])
    v.set_defaults(func=cmd_verify)
    args = ap.parse_args()
    args.game = Path(args.game)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
