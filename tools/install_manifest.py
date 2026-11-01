#!/usr/bin/env python3
"""为一个真实游戏安装生成、校验并落盘运行时 manifest。

用法:
    python -I tools/install_manifest.py --game-root Starsector-098-260mods
    python -I tools/install_manifest.py --game-root <game> --out <file>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# `python -I` 不会把脚本目录加入 sys.path；工具内部自行补上。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen_lazy_skip import build_skip, write_skip  # noqa: E402
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
    skip_file: Path | None = None
    skip_count: int = 0


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
    skip_file: Path | None = None
    skip_count = 0
    if not critical:
        runtime = trim(built.manifest)
        target.parent.mkdir(parents=True, exist_ok=True)
        skip_target = target.parent / "lazy-skip-v1.txt"
        # manifest 与 skip 必须同代：先把两者都算好、都写到同目录 .tmp，再按
        # 顺序替换。任何一步失败都不能留下“新 manifest + 旧 skip”的跨代 pair
        # （旧 skip 可能跳过新 manifest 提升为 L1 的 path，违反硬不变量）。
        skip_rows, _skip_stats = build_skip(runtime)
        tmp = target.with_name(target.name + ".tmp")
        skip_tmp = skip_target.with_name(skip_target.name + ".tmp")
        try:
            # 原子写：先写同目录 sibling 临时文件，成功后再替换目标；任何异常
            # 都删除临时文件并保留旧 manifest（这是运行时唯一的 manifest 写点）。
            with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(runtime, fh, ensure_ascii=False, separators=(",", ":"))
                fh.flush()
            # skip 头记录它所配对的那份 manifest 的 sha256（agent 读取时跳过
            # # 行），便于事后核对两者是不是同一代。
            generation = hashlib.sha256(tmp.read_bytes()).hexdigest()
            write_skip(skip_tmp, skip_rows, header=f"# generation={generation}")
            os.replace(tmp, target)
            try:
                os.replace(skip_tmp, skip_target)
            except BaseException:
                # manifest 已换新而 skip 还是旧代：删除旧 skip，让 agent 走
                # “skip 缺失 → lazy disabled → 正常加载”，绝不留下跨代 pair。
                skip_target.unlink(missing_ok=True)
                raise
        except BaseException:
            tmp.unlink(missing_ok=True)
            skip_tmp.unlink(missing_ok=True)
            raise
        skip_file = skip_target
        skip_count = len(skip_rows)
    return InstallResult(
        built.manifest,
        runtime,
        target,
        findings,
        skip_file=skip_file,
        skip_count=skip_count,
    )


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
    print(f"skip={result.skip_count} skip_file={result.skip_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
