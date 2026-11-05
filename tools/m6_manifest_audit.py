"""M6：manifest/skip generation 配对、宿主污染与 fail-open 审计。"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from hn_json import load  # noqa: E402
from install_manifest import DEFAULT_REL, install  # noqa: E402
from l1_core import CORE_STATIC, PLANET_FIELDS, PLANET_TYPES  # noqa: E402

RUNTIME_SCHEMA = "hypernova-runtime-1"
HYPERNOVA_REL = Path(
    "mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _generation(path: Path) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# generation="):
            return line.split("=", 1)[1].strip()
    return None


def _skip_entries(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )


def _obj(value) -> dict:
    return value if isinstance(value, dict) else {}


def audit_installed(game_root: str | Path) -> dict:
    root = Path(game_root).resolve()
    manifest = root / DEFAULT_REL
    skip_dir = manifest.parent
    findings: list[str] = []
    manifest_exists = manifest.is_file()
    manifest_info = {
        "path": str(manifest),
        "exists": manifest_exists,
        "sha256": None,
        "size_bytes": 0,
        "schema": None,
        "l1": 0,
        "l2": 0,
        "l3": 0,
    }
    if manifest_exists:
        manifest_info["sha256"] = _sha256(manifest)
        manifest_info["size_bytes"] = manifest.stat().st_size
        try:
            data = load(manifest)
        except Exception as exc:  # noqa: BLE001 - fail-closed finding
            findings.append("manifest_parse_error")
            manifest_info["parse_error"] = str(exc)
        else:
            if not isinstance(data, dict):
                findings.append("manifest_parse_error")
                manifest_info["parse_error"] = "top-level is not an object"
            else:
                layers = _obj(data.get("layers"))
                counts = {}
                for name in ("L1", "L2", "L3"):
                    value = layers.get(name)
                    counts[name] = len(value) if isinstance(value, list) else 0
                manifest_info.update({
                    "schema": data.get("schema"),
                    "l1": counts["L1"],
                    "l2": counts["L2"],
                    "l3": counts["L3"],
                })
                if data.get("schema") != RUNTIME_SCHEMA:
                    findings.append("manifest_schema_unexpected")
                if sum(counts.values()) == 0:
                    findings.append("manifest_empty")
    else:
        findings.append("manifest_missing")

    skip_v1 = skip_dir / "lazy-skip-v1.txt"
    skip_v2 = skip_dir / "lazy-skip-v2.txt"
    skip_info = {
        "v1": {
            "path": str(skip_v1),
            "exists": skip_v1.is_file(),
            "generation": _generation(skip_v1),
            "entries": _skip_entries(skip_v1),
            "generation_checked": manifest_info["sha256"] is not None,
        },
        "v2": {
            "path": str(skip_v2),
            "exists": skip_v2.is_file(),
            "generation": _generation(skip_v2),
            "entries": _skip_entries(skip_v2),
            "generation_checked": manifest_info["sha256"] is not None,
        },
    }
    for key in ("v1", "v2"):
        info = skip_info[key]
        if not info["exists"]:
            findings.append(f"skip_{key}_missing")
        elif manifest_info["sha256"] is None:
            findings.append(f"skip_{key}_generation_unpaired")
        elif info["generation"] != manifest_info["sha256"]:
            findings.append(f"skip_{key}_generation_mismatch")

    core = root / "starsector-core"
    core_exists = core.is_dir()
    if not core_exists:
        findings.append("core_dir_missing")
    host = (
        sorted(str(p.relative_to(root)) for p in core.glob("lazy-skip-*.txt"))
        if core_exists
        else []
    )
    if host:
        findings.append("host_lazy_skip")

    hn = root / HYPERNOVA_REL
    config_info = {"path": str(hn), "exists": hn.is_file()}
    config_error: str | None = None
    if not hn.is_file():
        findings.append("hypernova_config_missing")
        cfg: dict = {}
    else:
        try:
            cfg = load(hn)
        except Exception as exc:  # noqa: BLE001 - fail-closed finding
            config_error = str(exc)
            cfg = {}
        if not isinstance(cfg, dict):
            config_error = config_error or "top-level is not an object"
            cfg = {}
    if config_error:
        findings.append("hypernova_config_invalid")
        config_info["error"] = config_error

    textures_raw = cfg.get("textures")
    textures = _obj(textures_raw)
    lazy_raw = textures.get("lazy")
    lazy = _obj(lazy_raw)
    eviction_raw = lazy.get("eviction")
    eviction = _obj(eviction_raw)
    scene_raw = eviction.get("scene_unload")
    scene = _obj(scene_raw)
    if any(
        value is not None and not isinstance(value, dict)
        for value in (textures_raw, lazy_raw, eviction_raw, scene_raw)
    ) and "hypernova_config_invalid" not in findings:
        findings.append("hypernova_config_invalid")
    defaults = {
        # 产品 TexturePatchConfig 的缺省是 true；显式 false 才会关闭。
        "textures_enabled": bool(textures.get("enabled", True)),
        "textures_enabled_explicit": "enabled" in textures,
        "lazy": bool(lazy.get("enabled", False)),
        "eviction": bool(eviction.get("enabled", False)),
        # 产品真实键：textures.lazy.eviction.scene_unload.enabled
        "scene_unload": bool(isinstance(scene_raw, dict) and scene.get("enabled", False)),
    }
    if defaults["lazy"] or defaults["eviction"] or defaults["scene_unload"]:
        findings.append("default_not_off")
    return {
        "manifest": manifest_info,
        "skip_v1": skip_info["v1"],
        "skip_v2": skip_info["v2"],
        "core": {"path": str(core), "exists": core_exists},
        "config": config_info,
        "host_pollution": {"found": host},
        "defaults": defaults,
        "findings": findings,
        "ok": not findings,
    }


def _png(w: int, h: int) -> bytes:
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
            + struct.pack(">II", w, h) + b"\x08\x06\x00\x00\x00"
            + b"\x00\x00\x00\x00")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_broken_game(root: Path) -> None:
    for rel in CORE_STATIC:
        path = root / "starsector-core" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_png(2, 2))
    planets = {
        t: {f: f"graphics/planets/{t}_{f}.jpg" for f in PLANET_FIELDS}
        for t in PLANET_TYPES
    }
    for t, fields in planets.items():
        for rel in fields.values():
            path = root / "starsector-core" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_png(2, 2))
    _write(root / "starsector-core/data/config/planets.json", json.dumps(planets))
    # dup_same 是真实 ModID；两个目录同 id 构成 duplicate ModID。
    _write(root / "mods/enabled_mods.json", json.dumps({
        "enabledMods": ["good_mod", "dup_same", "tail_mod", "missing_mod"],
    }))
    # 正常 mod
    good = root / "mods/good_mod"
    _write(good / "mod_info.json", '{"id":"good_mod","name":"good"}')
    (good / "graphics/ships").mkdir(parents=True)
    (good / "graphics/ships/ship.png").write_bytes(_png(4, 4))
    # duplicate ModID：两个目录同 id
    for folder in ("dup_a", "dup_b"):
        _write(root / "mods" / folder / "mod_info.json",
               '{"id":"dup_same","name":"dup"}')
    # 尾逗号 mod_info（ChineseInputFix 风格）
    _write(root / "mods/tail_mod/mod_info.json",
           '{"id":"tail_mod","name":"tail",}')
    (root / "mods/tail_mod/graphics").mkdir(parents=True)
    (root / "mods/tail_mod/graphics/tail.png").write_bytes(_png(3, 3))
    # 空目录（无 mod_info）
    (root / "mods/empty_mod").mkdir(parents=True)


def _seed_bad_metadata(root: Path) -> None:
    _seed_broken_game(root)
    _write(root / "mods/DDSCache/bad_mod/dds_metadata.json", "{bad json,")


def _seed_missing_dds(root: Path) -> None:
    _seed_broken_game(root)
    _write(
        root / "mods/DDSCache/good_mod/dds_metadata.json",
        json.dumps([{
            "ModFolderName": "good_mod",
            "RelativeImagePath": "graphics\\ships\\ship.png",
            "DDSFilePath": "\\mods\\DDSCache\\good_mod\\graphics\\ships\\ship.dds",
            "Width": 4,
            "Height": 4,
        }]),
    )


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _reject_unsafe_workdir(base: Path, game_root: str | Path | None) -> None:
    if _is_within(base, REPO_ROOT):
        raise ValueError(
            f"fail-open workdir must be outside the repository: {base}"
        )
    if game_root is not None:
        game = Path(game_root).resolve()
        if _is_within(base, game):
            raise ValueError(
                f"fail-open workdir must be outside the game root: {base}"
            )
    if base.exists():
        if not base.is_dir() or any(base.iterdir()):
            raise FileExistsError(f"workdir already exists and is not empty: {base}")


def _scenario_summary(result, out: Path) -> dict:
    stats = _obj(result.full.get("stats"))
    conflicts = _obj(stats.get("conflicts"))
    layers = _obj(result.full.get("layers"))
    entries: list[dict] = []
    for name in ("L1", "L2", "L3"):
        value = layers.get(name)
        if isinstance(value, list):
            entries.extend(e for e in value if isinstance(e, dict))
    good_entries = [
        e for e in entries
        if str(e.get("modId")) == "good_mod"
        and "ship.png" in str(e.get("path", "")).replace("\\", "/")
    ]
    mods = result.full.get("mods")
    scanned = sorted({
        str(m.get("modId"))
        for m in (mods if isinstance(mods, list) else [])
        if isinstance(m, dict) and m.get("modId")
    })
    skip_file = Path(result.skip_file) if result.skip_file is not None else None
    return {
        "manifest_written": out.is_file(),
        "findings": [f"{f.severity}:{f.code}" for f in result.findings],
        "skip_v1_count": result.skip_count,
        "skip_v2_count": result.skip_v2_count,
        "duplicate_ids": conflicts.get("duplicate_mod_ids") or {},
        "missing_mod_ids": conflicts.get("missing_mod_ids") or [],
        "parse_errors": conflicts.get("mod_parse_errors") or {},
        "metadata_parse_errors": stats.get("metadata_parse_errors") or {},
        "source_mode": stats.get("source_mode"),
        "metadata_fallback_hits": stats.get("metadata_fallback_hits", 0),
        "stale_metadata_count": stats.get("stale_metadata_count", 0),
        "dds_missing_count": stats.get("dds_missing_count", 0),
        "unresolved_refs_count": stats.get("unresolved_refs_count", 0),
        "scanned_mod_ids": scanned,
        "good_mod_baked": (
            bool(good_entries[0].get("baked")) if good_entries else None
        ),
        "generation_matches": bool(
            out.is_file()
            and skip_file is not None
            and _generation(skip_file) == _sha256(out)
        ),
        "exception": None,
    }


def _run_scenario(base: Path, name: str, seed) -> dict:
    root = base / name / "game"
    seed(root)
    out = base / name / "runtime" / "manifest-v1.json"
    try:
        result = install(root, out=out)
    except Exception as exc:  # noqa: BLE001 - fail-open evidence
        return {
            "ok": False,
            "exception": f"{type(exc).__name__}: {exc}",
            "manifest_written": out.is_file(),
        }
    return _scenario_summary(result, out)


def _has_critical(summary: dict) -> bool:
    return any(
        str(f).startswith("Critical:")
        for f in (summary.get("findings") or [])
    )


def _run_missing_skip_rerun(base: Path) -> dict:
    root = base / "missing_skip_rerun" / "game"
    _seed_broken_game(root)
    out = base / "missing_skip_rerun" / "runtime" / "manifest-v1.json"
    try:
        first = install(root, out=out)
        removed = []
        for path in (first.skip_file, first.skip_v2_file):
            if path is not None and Path(path).is_file():
                Path(path).unlink()
                removed.append(str(path))
        second = install(root, out=out)
    except Exception as exc:  # noqa: BLE001 - fail-open evidence
        return {
            "ok": False,
            "exception": f"{type(exc).__name__}: {exc}",
            "manifest_written": out.is_file(),
        }
    summary = _scenario_summary(second, out)
    summary["skip_removed_before_rerun"] = len(removed) == 2
    summary["first_skip_v1_count"] = first.skip_count
    summary["first_skip_v2_count"] = first.skip_v2_count
    summary["ok"] = bool(
        summary["exception"] is None
        and summary["skip_removed_before_rerun"]
        and first.skip_count > 0
        and first.skip_v2_count > 0
        and summary["manifest_written"]
        and summary["skip_v1_count"] > 0
        and summary["skip_v2_count"] > 0
        and summary["generation_matches"]
        and not _has_critical(summary)
    )
    return summary


def audit_fail_open(
    workdir: str | Path, *, game_root: str | Path | None = None
) -> dict:
    base = Path(workdir).resolve()
    _reject_unsafe_workdir(base, game_root)
    scenarios = {
        "broken_mods": _run_scenario(base, "broken_mods", _seed_broken_game),
        "bad_metadata": _run_scenario(base, "bad_metadata", _seed_bad_metadata),
        "missing_dds": _run_scenario(base, "missing_dds", _seed_missing_dds),
        "missing_skip_rerun": _run_missing_skip_rerun(base),
    }
    broken = scenarios["broken_mods"]
    broken["ok"] = bool(
        broken.get("exception") is None
        and broken.get("manifest_written") is True
        and broken.get("skip_v1_count", 0) > 0
        and broken.get("skip_v2_count", 0) > 0
        and broken.get("duplicate_ids") == {"dup_same": ["dup_a", "dup_b"]}
        and broken.get("missing_mod_ids") == ["missing_mod"]
        and "tail_mod" in (broken.get("scanned_mod_ids") or [])
        and broken.get("good_mod_baked") is False
        and broken.get("source_mode") == "disk_scan"
        and not _has_critical(broken)
    )
    bad = scenarios["bad_metadata"]
    bad["ok"] = bool(
        bad.get("exception") is None
        and bad.get("manifest_written") is False
        and "Critical:metadata_parse_errors" in (bad.get("findings") or [])
        and bool(bad.get("metadata_parse_errors"))
    )
    missing = scenarios["missing_dds"]
    # 2026-11-05：DDSCache 里的 DDS 文件丢失时，manifest 不再拒绝写盘，而是把
    # 该条目降级为未烘焙（原图仍在，游戏照常能加载）。这比让玩家拿不到整份
    # 清单更稳；这里锁住"降级并写盘、无 Critical"的新语义。
    missing["ok"] = bool(
        missing.get("exception") is None
        and missing.get("manifest_written") is True
        and missing.get("dds_missing_count", 0) >= 1
        and missing.get("good_mod_baked") is False
        and not _has_critical(missing)
    )
    return {
        "workdir": str(base),
        "scenarios": scenarios,
        # 兼容 brief 顶层字段：默认取 broken_mods 场景。
        "duplicate_ids": broken.get("duplicate_ids", {}),
        "parse_errors": broken.get("parse_errors", {}),
        "manifest_written": bool(broken.get("manifest_written")),
        "findings": broken.get("findings", []),
        "skip_v1_count": int(broken.get("skip_v1_count", 0)),
        "skip_v2_count": int(broken.get("skip_v2_count", 0)),
        "metadata_parse_errors": broken.get("metadata_parse_errors", {}),
        "source_mode": broken.get("source_mode"),
        "metadata_fallback_hits": broken.get("metadata_fallback_hits", 0),
        "missing_mod_ids": broken.get("missing_mod_ids", []),
        "scanned_mod_ids": broken.get("scanned_mod_ids", []),
        "good_mod_baked": broken.get("good_mod_baked"),
        "ok": all(bool(sc.get("ok")) for sc in scenarios.values()),
    }


def _failure_summary(report: dict) -> str:
    parts: list[str] = []
    installed = report.get("installed") or {}
    if not installed.get("ok"):
        findings = installed.get("findings") or []
        parts.append(
            "installed: " + (",".join(findings) if findings else "ok=false")
        )
    fail_open = report.get("fail_open")
    if fail_open is not None and not fail_open.get("ok"):
        failed: list[str] = []
        for name, scenario in (fail_open.get("scenarios") or {}).items():
            if not scenario.get("ok"):
                detail = (
                    scenario.get("exception")
                    or ",".join(scenario.get("findings") or [])
                    or "ok=false"
                )
                failed.append(f"{name}:{detail}")
        parts.append("fail_open: " + ("; ".join(failed) if failed else "ok=false"))
    return "; ".join(parts) or "ok=false"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--fail-open-dir", type=Path)
    parser.add_argument("--fail-open-out", type=Path)
    args = parser.parse_args(argv)
    try:
        report = {"installed": audit_installed(args.game_root)}
        if args.fail_open_dir:
            report["fail_open"] = audit_fail_open(
                args.fail_open_dir, game_root=args.game_root
            )
        text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text + "\n", encoding="utf-8")
        if args.fail_open_out:
            if "fail_open" not in report:
                raise ValueError("--fail-open-out requires --fail-open-dir")
            args.fail_open_out.parent.mkdir(parents=True, exist_ok=True)
            args.fail_open_out.write_text(
                json.dumps(
                    report["fail_open"], ensure_ascii=False,
                    indent=2, sort_keys=True,
                ) + "\n",
                encoding="utf-8",
            )
    except Exception as exc:  # noqa: BLE001 - fail-closed one-line stderr
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1
    print(text)
    if not report["installed"]["ok"] or (
        "fail_open" in report and not report["fail_open"]["ok"]
    ):
        print(f"FATAL: {_failure_summary(report)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
