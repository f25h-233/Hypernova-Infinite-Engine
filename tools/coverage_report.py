#!/usr/bin/env python3
"""把 manifest + demand 渲染成 M0 覆盖率报告（Markdown）。"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def _pct(value) -> str:
    if value is None:
        return "N/A"
    return f"{float(value) * 100:.2f}%"


def _gate(value, threshold: float) -> str:
    if value is None:
        return "N/A"
    return "PASS" if float(value) >= threshold else "FAIL"


def render_report(
    manifest: dict,
    demand: list[dict],
    env_name: str,
    game_root: Path,
    min_coverage: float = 0.95,
    max_l1: int = 8000,
) -> str:
    stats = manifest.get("stats") or {}
    coverage = stats.get("coverage") or {}
    layers = manifest.get("layers") or {}
    l1 = layers.get("L1") or []
    l2 = layers.get("L2") or []
    l3 = layers.get("L3") or []
    l1_count = int(stats.get("l1_count") or len(l1))

    gate_rows = [
        ("L1 ≤ %d" % max_l1, _gate(l1_count, 0) if l1_count <= max_l1 else "FAIL", str(l1_count)),
        (
            "closure_refs ≥ %.2f" % min_coverage,
            _gate(coverage.get("closure_refs"), min_coverage),
            "N/A" if coverage.get("closure_refs") is None else f"{float(coverage['closure_refs']):.3f}",
        ),
        (
            "l1_sprite_disk ≥ %.2f" % min_coverage,
            _gate(coverage.get("l1_sprite_disk"), min_coverage),
            "N/A" if coverage.get("l1_sprite_disk") is None else f"{float(coverage['l1_sprite_disk']):.3f}",
        ),
        (
            "metadata == 1.0",
            "N/A" if coverage.get("metadata") is None else ("PASS" if float(coverage["metadata"]) >= 1.0 else "FAIL"),
            "N/A" if coverage.get("metadata") is None else f"{float(coverage['metadata']):.3f}",
        ),
    ]

    manifest_paths = {
        str(e.get("path", "")).casefold() for layer in (l1, l2, l3) for e in layer
    }
    demand_paths = [str(r.get("path", "")) for r in demand]
    unique_demand = sorted(set(demand_paths))
    covered = [p for p in unique_demand if p.casefold() in manifest_paths]
    missing_demand = [p for p in unique_demand if p.casefold() not in manifest_paths]
    prefix = Counter(p.split("/")[0] if "/" in p else p for p in missing_demand)

    lines = [
        f"# M0 覆盖率报告 — {env_name}",
        "",
        f"- 游戏根：`{game_root.as_posix()}`",
        f"- 生成时间：{manifest.get('generated_at', 'N/A')}",
        f"- scope：`{stats.get('scope')}`，include_core：`{stats.get('include_core')}`",
        f"- 数据来源：`{stats.get('source_mode', 'unknown')}`，优先级：`{stats.get('precedence', 'unknown')}`",
        "",
        "## 出口 gate",
        "",
        "| 指标 | 结果 | 实测 |",
        "|---|---|---|",
    ]
    lines += [f"| {name} | {result} | {value} |" for name, result, value in gate_rows]
    lines += [
        "",
        "## 层级规模",
        "",
        "| 层 | 条目数 |",
        "|---|---:|",
        f"| L1 | {len(l1)} |",
        f"| L2 | {len(l2)} |",
        f"| L3 | {len(l3)} |",
        "",
        "## 覆盖率",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
        f"| L1 sprite 落盘 | {_pct(coverage.get('l1_sprite_disk'))} |",
        f"| L1 已烘焙 | {_pct(coverage.get('l1_baked'))} |",
        f"| 闭包引用解析 | {_pct(coverage.get('closure_refs'))} |",
        f"| metadata 纳入 | {_pct(coverage.get('metadata'))} |",
        f"| metadata 条目（scope） | {stats.get('metadata_entries', 0)} |",
        f"| core 条目 | {stats.get('core_entries', 0)} |",
        f"| 磁盘图片（scope） | {stats.get('disk_images', 0)} |",
        f"| 未烘焙 | {stats.get('unbaked', 0)} |",
        f"| metadata 回退命中 | {stats.get('metadata_fallback_hits', 0)} |",
        "",
        "## 闭包缺口",
        "",
    ]
    closure = stats.get("closure") or {}
    if closure:
        lines += ["| 类别 | 引用 | 解析 |", "|---|---:|---:|"]
        for name, pair in closure.items():
            total, ok = pair
            lines.append(f"| {name} | {total} | {ok} |")
        lines.append("")
    missing = stats.get("missing") or {}
    if missing:
        for kind, names in sorted(missing.items()):
            sample = ", ".join(names[:8])
            lines.append(f"- `{kind}`（{len(names)}）：{sample}")
    else:
        lines.append("- 无")
    lines += ["", "## 首屏需求覆盖", ""]
    if demand:
        lines += [
            f"- 需求记录：{len(demand)} 条，唯一路径 {len(unique_demand)} 条",
            f"- manifest 覆盖：{len(covered)} / {len(unique_demand)} = {_pct(len(covered) / len(unique_demand))}",
        ]
        if covered:
            lines.append(f"- 已覆盖样例：{', '.join(covered[:8])}")
        if missing_demand:
            top = ", ".join(f"{k} ({v})" for k, v in prefix.most_common(8))
            lines.append(f"- 未覆盖路径前缀：{top}")
    else:
        lines.append("- 未提供 demand.jsonl")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--game-root", required=True, type=Path)
    parser.add_argument("--env-name", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--demand", type=Path, default=None)
    parser.add_argument("--min-coverage", type=float, default=0.95)
    parser.add_argument("--max-l1", type=int, default=8000)
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    demand = []
    if args.demand and args.demand.is_file():
        demand = [
            json.loads(line)
            for line in args.demand.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    text = render_report(
        manifest, demand, args.env_name, args.game_root, args.min_coverage, args.max_l1
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
