#!/usr/bin/env python3
"""把 M0 manifest 裁剪成运行时 manifest（schema=hypernova-runtime-1）。

用法:
    python -I tools/trim_manifest.py --src build/m0/base/manifest-v1.json \
        --out dist/manifest-v1.json

打包（build-mod.sh）与装机（install-manifest.sh）共用这一份裁剪逻辑，
避免「脚本 A 裁出来能跑、脚本 B 裁出来缺字段」这类只在实机才暴露的分裂。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LAYERS = ("L1", "L2", "L3")


def trim(data: dict) -> dict:
    """丢弃运行时不需要的字段（absolutePath/ddsPath 等），只保留 path/modId/w/h/baked。

    没有 path 的条目直接丢弃；三个层即使源里缺失也保留空数组，
    让运行时侧永远拿到 L1/L2/L3 三把钥匙。
    """
    out: dict = {"schema": "hypernova-runtime-1", "layers": {}}
    for layer in LAYERS:
        out["layers"][layer] = [
            {
                "path": e["path"],
                "modId": e["modId"],
                "w": e.get("w", 0),
                "h": e.get("h", 0),
                "baked": e.get("baked", False),
            }
            for e in data.get("layers", {}).get(layer, [])
            if e.get("path")
        ]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, type=Path, help="M0 生成的大 manifest")
    parser.add_argument("--out", required=True, type=Path, help="运行时 manifest 输出路径")
    args = parser.parse_args(argv)
    if not args.src.is_file():
        print(f"FATAL: manifest source not found: {args.src}", file=sys.stderr)
        return 1
    data = json.loads(args.src.read_text(encoding="utf-8"))
    out = trim(data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    counts = ", ".join(f"{k}={len(v)}" for k, v in out["layers"].items())
    print(f"wrote {args.out}: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
