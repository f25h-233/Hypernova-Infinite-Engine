#!/usr/bin/env python3
"""生成 M0 manifest。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# `python -I` 不会把脚本目录加入 sys.path；工具内部自行补上。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from manifest_builder import build_manifest, load_tier_overrides  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--scope", default="mod_non_shader", choices=["mod_non_shader", "all_mod_metadata"]
    )
    parser.add_argument("--no-core", action="store_true")
    parser.add_argument("--no-l2", action="store_true")
    parser.add_argument("--variant-limit", type=int, default=0)
    parser.add_argument("--tiers", type=Path,
                        help='JSON: {"mods": {"<modId>": "L1|L2|L3"}}')
    args = parser.parse_args(argv)

    result = build_manifest(
        args.game_root,
        scope=args.scope,
        include_core=not args.no_core,
        include_l2=not args.no_l2,
        variant_limit=args.variant_limit,
        tier_overrides=load_tier_overrides(args.tiers) if args.tiers else {},
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result.manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(result.manifest["stats"], ensure_ascii=False, indent=2))
    for warning in result.warnings:
        print(f"WARN: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
