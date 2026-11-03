"""M6 兼容性审计：环境矩阵（只读）。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hn_json import load  # noqa: E402

CJK = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
CORE = "starsector-core"
HN_REL = Path("mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json")


def _iter_strings(node: Any) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _iter_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_strings(value)


def _strings_stats(path: Path) -> dict[str, Any]:
    data = load(path)
    values = list(_iter_strings(data))
    cjk = sum(1 for value in values if CJK.search(value))
    return {
        "total_strings": len(values),
        "cjk_strings": cjk,
        "cjk_ratio": round(cjk / len(values), 4) if values else 0.0,
    }


def _version_text(value: Any) -> str | None:
    if isinstance(value, dict):
        parts = [value.get("major"), value.get("minor"), value.get("patch")]
        if all(isinstance(p, int) for p in parts):
            return ".".join(str(p) for p in parts)
    if isinstance(value, str):
        return value
    return None


def _mod_infos(mods_dir: Path) -> tuple[dict[str, dict], dict[str, str],
                                        dict[str, list[str]]]:
    """Return (by_id, parse_errors, folders_by_id)."""
    by_id: dict[str, dict] = {}
    parse_errors: dict[str, str] = {}
    folders: dict[str, list[str]] = {}
    for folder in sorted(mods_dir.iterdir()):
        info = folder / "mod_info.json"
        if not folder.is_dir() or not info.is_file():
            continue
        try:
            data = load(info)
        except Exception as exc:  # noqa: BLE001 - 审计要报告所有解析失败
            parse_errors[folder.name] = str(exc)
            continue
        mid = data.get("id")
        if not mid:
            continue
        mid = str(mid)
        data["_folder"] = folder.name
        by_id.setdefault(mid, data)
        folders.setdefault(mid, []).append(folder.name)
    duplicates = {
        mid: sorted(names) for mid, names in folders.items() if len(names) > 1
    }
    return by_id, parse_errors, duplicates


def _hypernova_state(game_root: Path) -> dict[str, Any]:
    data = load(game_root / HN_REL)
    textures = data.get("textures") or {}
    lazy = textures.get("lazy") or {}
    eviction = lazy.get("eviction") or {}
    scene = eviction.get("scene_unload") or {}
    return {
        # 产品默认值为 true（HypernovaConfig.java:15 / TexturePatchConfig.java:26）。
        "enabled": bool(data.get("enabled", True)),
        "textures_enabled": bool(textures.get("enabled", True)),
        "lazy": bool(lazy.get("enabled", False)),
        "eviction": bool(eviction.get("enabled", False)),
        # 产品 JSON 键是 textures.lazy.eviction.scene_unload.enabled
        # （LazyTextureConfig.java:80-81,107），不是 -D 属性的 sceneUnload。
        "scene_unload": bool(scene.get("enabled", False)),
        # 区分“未配置（走产品默认）”与“显式关闭”。
        "textures_present": isinstance(data.get("textures"), dict),
        "enabled_explicit": isinstance(data.get("enabled"), bool),
    }


def scan_environment(game_root: str | Path) -> dict[str, Any]:
    root = Path(game_root).resolve()
    # fail-closed：核心输入缺失时抛错，由 CLI 统一输出一行 FATAL。
    required = (
        Path(CORE) / "data" / "config" / "settings.json",
        Path("mods") / "enabled_mods.json",
        Path(CORE) / "data" / "strings" / "strings.json",
        HN_REL,
    )
    for rel in required:
        path = root / rel
        if not path.is_file():
            raise FileNotFoundError(f"missing {path}")
    settings = root / CORE / "data" / "config" / "settings.json"
    cfg = load(settings)
    mods_dir = root / "mods"
    enabled_data = load(mods_dir / "enabled_mods.json")
    enabled = [str(x) for x in (enabled_data.get("enabledMods") or [])]
    by_id, parse_errors, duplicates = _mod_infos(mods_dir)
    present = set(by_id)
    font_ui = []
    for mid, info in sorted(by_id.items()):
        folder = mods_dir / info["_folder"]
        records = {
            "mod_id": mid,
            "folder": info["_folder"],
            "enabled": mid in enabled,
            "fonts": (folder / "graphics" / "fonts").is_dir(),
            "ui": (folder / "graphics" / "ui").is_dir(),
            "strings": (folder / "data" / "strings").is_dir(),
        }
        # ChineseInputFix 本身是审计对象，即使不覆盖字体/UI/strings 也列入，
        # 以便矩阵直接展示其版本与启用状态；其余 mod 仍按覆盖目录过滤。
        if (
            records["fonts"]
            or records["ui"]
            or records["strings"]
            or mid == "ChineseInputFix"
        ):
            font_ui.append(records)
    chinese = by_id.get("ChineseInputFix")
    return {
        "game_root": str(root),
        "locale_override": cfg.get("localeOverride"),
        "cjk_mode": cfg.get("cjkMode"),
        "default_font": cfg.get("defaultFont"),
        "strings": _strings_stats(root / CORE / "data" / "strings" / "strings.json"),
        "mods": {
            "enabled_count": len(enabled),
            "scanned_count": len(present & set(enabled)),
            "scanned_total": len(present),
            "missing_enabled_ids": sorted(set(enabled) - present),
            "parse_errors": parse_errors,
            "duplicate_ids": duplicates,
        },
        "chinese_input_fix": {
            "present": chinese is not None,
            "enabled": "ChineseInputFix" in enabled,
            "version": _version_text(chinese.get("version")) if chinese else None,
        },
        "font_ui_mods": font_ui,
        "hypernova": _hypernova_state(root),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--text", action="store_true")
    args = parser.parse_args(argv)
    try:
        data = scan_environment(args.game_root)
        text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text + "\n", encoding="utf-8")
        if args.text or not args.out:
            print(text)
    except Exception as exc:  # noqa: BLE001 - fail-closed
        print(f"FATAL: {exc}".replace("\n", " "), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
