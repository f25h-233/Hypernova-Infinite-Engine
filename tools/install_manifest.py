#!/usr/bin/env python3
"""为一个真实游戏安装生成、校验并落盘运行时 manifest。

用法:
    python -I tools/install_manifest.py --game-root Starsector-098-260mods
    python -I tools/install_manifest.py --game-root <game> --out <file>
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

# `python -I` 不会把脚本目录加入 sys.path；工具内部自行补上。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from manifest_builder import build_manifest, load_tier_overrides  # noqa: E402
from trim_manifest import trim  # noqa: E402
from validate_manifest import Finding, validate  # noqa: E402

DEFAULT_REL = Path(
    "mods/hypernova_infinite_engine/data/config/hypernova/manifest-v1.json"
)


@dataclass(frozen=True)
class InstallResult:
    full: dict
    runtime: dict
    out: Path
    findings: list[Finding]


def install(
    game_root: Path,
    out: Path | None = None,
    *,
    tiers: dict[str, str] | None = None,
    scope: str = "mod_non_shader",
    include_core: bool = True,
    include_l2: bool = True,
    max_l1: int = 8000,
) -> InstallResult:
    root = Path(game_root).resolve()
    target = Path(out) if out is not None else root / DEFAULT_REL
    built = build_manifest(
        root,
        scope=scope,
        include_core=include_core,
        include_l2=include_l2,
        tier_overrides=tiers or {},
    )
    findings = validate(built.manifest, root, max_l1=max_l1)
    critical = any(f.severity == "Critical" for f in findings)
    runtime: dict = {}
    if not critical:
        runtime = trim(built.manifest)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(runtime, fh, ensure_ascii=False, separators=(",", ":"))
    return InstallResult(built.manifest, runtime, target, findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--tiers", type=Path,
                        help='JSON: {"mods": {"<modId>": "L1|L2|L3"}}')
    parser.add_argument("--scope", default="mod_non_shader",
                        choices=["mod_non_shader", "all_mod_metadata"])
    parser.add_argument("--no-core", action="store_true")
    parser.add_argument("--no-l2", action="store_true")
    parser.add_argument("--max-l1", type=int, default=8000)
    args = parser.parse_args(argv)
    tiers = load_tier_overrides(args.tiers) if args.tiers else {}
    result = install(
        args.game_root,
        out=args.out,
        tiers=tiers,
        scope=args.scope,
        include_core=not args.no_core,
        include_l2=not args.no_l2,
        max_l1=args.max_l1,
    )
    stats = result.full["stats"]
    print(
        "full: L1={l1} L2={l2} L3={l3} baked={baked}/{expected} "
        "unresolved={unresolved}".format(
            l1=stats["l1_count"],
            l2=stats["l2_count"],
            l3=stats["l3_count"],
            baked=stats["coverage"]["baked_resolved"],
            expected=stats["coverage"]["baked_expected"],
            unresolved=stats["unresolved_baked_count"],
        )
    )
    for finding in result.findings:
        print(f"[{finding.severity}] {finding.code}: {finding.message}")
    if any(f.severity == "Critical" for f in result.findings):
        print("FATAL: manifest not written (Critical findings)", file=sys.stderr)
        return 1
    print(f"installed: {result.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
