#!/usr/bin/env python3
"""校验 manifest 的结构、路径存在性、覆盖率与 L1 规模。"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

# `python -I` 不会把脚本目录加入 sys.path；工具内部自行补上。
sys.path.insert(0, str(Path(__file__).resolve().parent))

REQUIRED_ENTRY = ("modId", "path", "absolutePath", "ddsPath", "w", "h", "baked", "src")


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str


def _inside_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    return True


def _entry_findings(entry: dict, layer: str, game_root: Path) -> list[Finding]:
    out: list[Finding] = []
    missing = [k for k in REQUIRED_ENTRY if k not in entry]
    if missing:
        return [Finding("Critical", "entry_schema", f"{layer}: missing keys {missing}")]
    path = str(entry["path"])
    if not path or path.startswith("/") or ".." in path.split("/"):
        out.append(Finding("Critical", "bad_path", f"{layer}: illegal path {path!r}"))
    absolute = str(entry["absolutePath"])
    if not absolute:
        out.append(
            Finding("Critical", "missing_file", f"{layer}: unresolved asset {path}")
        )
    elif not Path(absolute).is_file():
        out.append(
            Finding("Critical", "missing_file", f"{layer}: file not found {absolute}")
        )
    if absolute and Path(absolute).is_file() and not _inside_root(Path(absolute), game_root):
        out.append(
            Finding("Critical", "asset_outside_root", f"{layer}: asset outside game root {absolute}")
        )
    if entry["baked"]:
        dds = entry.get("ddsPath")
        if not dds or not Path(str(dds)).is_file():
            out.append(
                Finding("Critical", "missing_dds", f"{layer}: baked entry has no DDS {path}")
            )
        elif not _inside_root(Path(str(dds)), game_root):
            out.append(
                Finding(
                    "Critical",
                    "dds_outside_root",
                    f"{layer}: DDS outside game root {dds}",
                )
            )
    if int(entry["w"]) < 0 or int(entry["h"]) < 0:
        out.append(Finding("Minor", "bad_size", f"{layer}: negative size {path}"))
    return out


def validate(
    manifest: dict,
    game_root: Path,
    min_coverage: float = 0.95,
    max_l1: int = 8000,
) -> list[Finding]:
    findings: list[Finding] = []
    if type(manifest.get("schema")) is not int or manifest.get("schema") != 1:
        findings.append(
            Finding("Critical", "schema", f"expected integer schema 1, got {manifest.get('schema')!r}")
        )
    layers = manifest.get("layers")
    if not isinstance(layers, dict) or not all(k in layers for k in ("L1", "L2", "L3")):
        findings.append(Finding("Critical", "layers", "layers must contain L1/L2/L3"))
        return findings
    for name in ("L1", "L2", "L3"):
        entries = layers[name]
        if not isinstance(entries, list):
            findings.append(Finding("Critical", "layers", f"{name} is not a list"))
            continue
        seen = set()
        for entry in entries:
            findings.extend(_entry_findings(entry, name, game_root))
            key = (str(entry.get("modId")), str(entry.get("path")).casefold())
            if key in seen:
                findings.append(
                    Finding("Important", "duplicate_entry", f"{name}: duplicate {key}")
                )
            seen.add(key)

    if not layers["L1"]:
        findings.append(Finding("Critical", "empty_l1", "L1 layer is empty"))
    key_layers: dict[str, set[str]] = {}
    for name in ("L1", "L2", "L3"):
        if not isinstance(layers[name], list):
            continue
        for entry in layers[name]:
            key = str(entry.get("path", "")).casefold()
            key_layers.setdefault(key, set()).add(name)
    cross = {k: v for k, v in key_layers.items() if len(v) > 1}
    if cross:
        findings.append(
            Finding(
                "Important",
                "cross_layer_duplicate",
                f"{len(cross)} engine key(s) appear in multiple layers: "
                + ", ".join(sorted(cross)[:5]),
            )
        )

    stats = manifest.get("stats")
    if not isinstance(stats, dict):
        findings.append(Finding("Critical", "missing_stats", "manifest.stats is missing"))
        return findings
    coverage = stats.get("coverage")
    if not isinstance(coverage, dict):
        findings.append(
            Finding("Critical", "missing_coverage", "manifest.stats.coverage is missing")
        )
        return findings
    for required in ("l1_sprite_disk", "closure_refs"):
        if required not in coverage:
            findings.append(
                Finding("Critical", "missing_coverage", f"coverage.{required} is missing")
            )
    stats_l1 = stats.get("l1_count")
    stats_l1_value: int | None = None
    if stats_l1 is not None:
        try:
            stats_l1_value = int(stats_l1)
        except (TypeError, ValueError):
            stats_l1_value = None
        if stats_l1_value != len(layers["L1"]):
            findings.append(
                Finding(
                    "Critical",
                    "l1_count_mismatch",
                    f"stats.l1_count={stats_l1} != len(L1)={len(layers['L1'])}",
                )
            )
    l1_count = stats_l1_value if stats_l1_value is not None else len(layers["L1"])
    if l1_count > max_l1:
        findings.append(
            Finding("Critical", "l1_too_large", f"L1={l1_count} > {max_l1}")
        )
    for key in ("l1_sprite_disk", "closure_refs"):
        value = coverage.get(key)
        if value is not None and float(value) < min_coverage:
            findings.append(
                Finding(
                    "Critical",
                    f"coverage_{key}",
                    f"{key}={value} < {min_coverage}",
                )
            )
    meta_cov = coverage.get("metadata")
    if meta_cov is not None and float(meta_cov) < 1.0:
        findings.append(
            Finding("Critical", "coverage_metadata", f"metadata={meta_cov} < 1.0")
        )
    parse_errors = stats.get("metadata_parse_errors") or {}
    if parse_errors:
        findings.append(
            Finding(
                "Critical",
                "metadata_parse_errors",
                f"{len(parse_errors)} metadata file(s) failed to parse: "
                + ", ".join(sorted(parse_errors)[:5]),
            )
        )
    core_errors = stats.get("core_parse_errors") or {}
    if core_errors:
        findings.append(
            Finding(
                "Critical",
                "core_parse_errors",
                f"core asset source failed to parse: "
                + ", ".join(sorted(core_errors)[:5]),
            )
        )

    if "baked" in coverage:
        baked_cov = coverage.get("baked")
        # 新字段存在时必须是可解释为有限浮点数的值；只有整体缺失才兼容旧 manifest。
        try:
            baked_value = float(baked_cov)
        except (TypeError, ValueError, OverflowError):
            findings.append(
                Finding(
                    "Critical",
                    "coverage_baked",
                    f"baked={baked_cov!r} is not numeric",
                )
            )
        else:
            if not math.isfinite(baked_value):
                findings.append(
                    Finding(
                        "Critical",
                        "coverage_baked",
                        f"baked={baked_cov!r} is not finite",
                    )
                )
            elif baked_value < 1.0:
                findings.append(
                    Finding("Critical", "coverage_baked", f"baked={baked_cov} < 1.0")
                )
    unresolved_count = None
    if "unresolved_baked_count" in stats:
        raw_unresolved = stats.get("unresolved_baked_count")
        # 新字段存在时必须能解释为整数；形状不对要报 Critical，不能静默跳过门禁。
        try:
            unresolved_count = int(raw_unresolved)
        except (TypeError, ValueError, OverflowError):
            findings.append(
                Finding(
                    "Critical",
                    "baked_unresolved_shape",
                    f"unresolved_baked_count={raw_unresolved!r} is not an integer",
                )
            )
    if unresolved_count is not None and unresolved_count > 0:
        sample = stats.get("unresolved_baked") or []
        findings.append(
            Finding(
                "Critical",
                "baked_unresolved",
                f"{unresolved_count} enabled baked texture(s) unresolved: "
                + ", ".join(str(x) for x in sample[:5]),
            )
        )

    mods_summary = manifest.get("mods")
    if "mods" in manifest:
        if not isinstance(mods_summary, list):
            findings.append(
                Finding("Critical", "mods_summary", "mods must be a list")
            )
        else:
            seen_mods: set[str] = set()
            sums = {"L1": 0, "L2": 0, "L3": 0}
            for item in mods_summary:
                if not isinstance(item, dict):
                    findings.append(
                        Finding("Critical", "mods_summary", "mods entry is not an object")
                    )
                    continue
                mid = item.get("modId")
                item_layers = item.get("layers")
                if not isinstance(mid, str) or not mid:
                    findings.append(
                        Finding("Critical", "mods_summary", f"bad modId {mid!r}")
                    )
                    continue
                if mid.casefold() in seen_mods:
                    findings.append(
                        Finding("Important", "duplicate_mod_summary", mid)
                    )
                seen_mods.add(mid.casefold())
                tier = item.get("tier")
                if tier not in (None, "auto", "L1", "L2", "L3"):
                    findings.append(
                        Finding("Critical", "mods_tier", f"{mid}: bad tier {tier!r}")
                    )
                if (
                    not isinstance(item_layers, dict)
                    or any(not isinstance(item_layers.get(k), int) for k in sums)
                ):
                    findings.append(
                        Finding("Critical", "mods_summary", f"{mid}: bad layers")
                    )
                    continue
                for k in sums:
                    sums[k] += item_layers[k]
            for k, total in sums.items():
                expected = len(layers[k]) if isinstance(layers[k], list) else 0
                if total != expected:
                    findings.append(
                        Finding(
                            "Critical",
                            "mods_layer_mismatch",
                            f"{k}: summary={total} != entries={expected}",
                        )
                    )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--game-root", required=True, type=Path)
    parser.add_argument("--min-coverage", type=float, default=0.95)
    parser.add_argument("--max-l1", type=int, default=8000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.game_root.is_dir():
        print(
            f"[Critical] bad_game_root: {args.game_root} is not a directory",
            file=sys.stderr,
        )
        return 1
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    findings = validate(manifest, args.game_root, args.min_coverage, args.max_l1)
    if args.json:
        print(json.dumps([f.__dict__ for f in findings], ensure_ascii=False, indent=2))
    else:
        for f in findings:
            print(f"[{f.severity}] {f.code}: {f.message}")
        if not findings:
            print("OK: no findings")
    return 1 if any(f.severity == "Critical" for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
