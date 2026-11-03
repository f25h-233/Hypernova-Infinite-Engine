"""M7 统一部署包：实验根盘点与 256 mod 迁移。

Task 1 只做只读盘点；Task 2 增加迁移规划。所有写操作都必须显式
``--apply``，默认 dry-run。本模块不依赖 M6 快照，可独立运行。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hn_json import load  # noqa: E402

MAIN_CLASS = "com.fs.starfarer.StarfarerLauncher"

LOCALIZATION_PATH = "starsector-core/localization_version.json"
JRE_RELEASE_PATH = "jre/release"
VMPARAMS_PATH = "vmparams"
ENABLED_MODS_PATH = "mods/enabled_mods.json"
DYN_FONT_DIR = "starsector-core/graphics/fonts/dyn_font"
SSIME_DLL_PATH = "starsector-core/native/windows/ssime.dll"

_AGENT_RE = re.compile(r"-javaagent:(\S+)")
_HYPERNOVA_FLAG_RE = re.compile(r"-Dhypernova\.[^\s]+")
_JAVA_VERSION_RE = re.compile(r'^\s*JAVA_VERSION\s*=\s*"([^"]*)"', re.MULTILINE)

# 路线定义只记录“该路线应当使用什么”，实际安装目录由后续任务显式传入。
ROUTES = {
    "a": {
        "name": "MixinFR + JRE 17 + StarsectorParallel",
        "java": "jre",
        "fr": None,
        "mixinfr": True,
        "parallel": True,
    },
    "b": {
        "name": "FR 0.9.7 + Java 28",
        "java": "jdk-28+13",
        "fr": "0.9.7rc2",
        "mixinfr": False,
        "parallel": False,
    },
}

# 路线单独安装，迁移 256 mod 时必须排除；比较时统一转小写。
EXCLUDED_MOD_IDS = frozenset({
    "hypernova_infinite_engine",
    "mixinfr",
    "mixinlib",
    "starsectorparallel",
})


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def _read_json(path: Path) -> object:
    if not path.is_file():
        return {}
    try:
        return load(path)
    except Exception:  # noqa: BLE001 - 盘点不应因单个坏文件失败
        return {}


def _localization(root: Path) -> dict[str, str | None]:
    payload = _read_json(root / LOCALIZATION_PATH)
    data = payload if isinstance(payload, dict) else {}
    return {
        "version": _as_text(data.get("version")),
        "branch": _as_text(data.get("branch")),
        "language": _as_text(data.get("language")),
        "game_version": _as_text(data.get("game_version")),
    }


def _jre_version(root: Path) -> str | None:
    path = root / JRE_RELEASE_PATH
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    match = _JAVA_VERSION_RE.search(text)
    return match.group(1) if match else None


def _dyn_font(root: Path) -> bool:
    folder = root / DYN_FONT_DIR
    return (folder / "chars.txt").is_file() or (folder / "typefaces.dat").is_file()


def _vmparams(root: Path) -> dict[str, object]:
    path = root / VMPARAMS_PATH
    text = ""
    if path.is_file():
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            text = ""
    agents = _AGENT_RE.findall(text)
    return {
        "path": str(path),
        "has_main_class": MAIN_CLASS in text,
        "agents": agents,
        "hypernova_flags": _HYPERNOVA_FLAG_RE.findall(text),
        # 测试契约要求；同时保留 agents 列表供后续任务使用。
        "has_agent": bool(agents),
    }


def _mods(root: Path) -> dict[str, object]:
    payload = _read_json(root / ENABLED_MODS_PATH)
    enabled: list[str] = []
    if isinstance(payload, dict):
        raw = payload.get("enabledMods")
        if isinstance(raw, list):
            enabled = [item for item in raw if isinstance(item, str)]
    lowered = {item.lower() for item in enabled}
    return {
        "enabled_count": len(enabled),
        "has_hypernova": "hypernova_infinite_engine" in lowered,
        "has_mixinfr": "mixinlib" in lowered,
        "has_parallel": "starsectorparallel" in lowered,
    }


def inspect_root(root: str | Path) -> dict[str, object]:
    """只读盘点一个 Starsector 安装根，返回可序列化的事实字典。"""
    base = Path(root)
    if not base.is_dir():
        raise FileNotFoundError(f"install root not found: {base}")
    return {
        "root": str(base),
        "localization": _localization(base),
        "jre_version": _jre_version(base),
        "dyn_font": _dyn_font(base),
        "ssime_dll": (base / SSIME_DLL_PATH).is_file(),
        "vmparams": _vmparams(base),
        "mods": _mods(base),
    }


def _enabled_ids(source_mods: Path) -> list[str]:
    payload = _read_json(source_mods / "enabled_mods.json")
    if isinstance(payload, dict):
        raw = payload.get("enabledMods")
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, str)]
    return []


def _mod_folders(source_mods: Path) -> dict[str, str]:
    """返回 ``小写 mod id -> 文件夹名``；读取每个文件夹的 mod_info.json。"""
    folders: dict[str, str] = {}
    for entry in sorted(source_mods.iterdir(), key=lambda item: item.name):
        if not entry.is_dir():
            continue
        info = _read_json(entry / "mod_info.json")
        if isinstance(info, dict):
            mod_id = info.get("id")
            if isinstance(mod_id, str) and mod_id:
                folders[mod_id.lower()] = entry.name
    return folders


def plan_migrate(
    source_mods: str | Path,
    target_mods: str | Path,
    *,
    link: bool,
) -> dict[str, object]:
    """规划 256 mod 迁移；只读，不做任何写入。

    ``enabled_mods.json`` 里的条目是 mod id，而非文件夹名，因此先扫描
    ``mod_info.json`` 建立 id 到文件夹的映射。排除项按 id 大小写不敏感过滤。
    """
    source = Path(source_mods)
    target = Path(target_mods)
    if not source.is_dir():
        raise FileNotFoundError(f"source mods dir not found: {source}")

    enabled_ids = _enabled_ids(source)
    folders = _mod_folders(source)
    by_folder = {
        entry.name.lower(): entry.name
        for entry in source.iterdir()
        if entry.is_dir()
    }

    copy: list[str] = []
    enabled: list[str] = []
    for mod_id in enabled_ids:
        key = mod_id.lower()
        if key in EXCLUDED_MOD_IDS:
            continue
        enabled.append(mod_id)
        # 优先按 id 映射；个别 mod 缺少 mod_info.json 时退回同名文件夹。
        folder = folders.get(key) or by_folder.get(key)
        if folder is not None and folder not in copy:
            copy.append(folder)

    excluded = sorted(
        {folder for key, folder in folders.items() if key in EXCLUDED_MOD_IDS}
        | {
            folder
            for key, folder in by_folder.items()
            if key in EXCLUDED_MOD_IDS
        }
    )
    return {
        "source": str(source),
        "target": str(target),
        "link": bool(link),
        "apply": False,
        "copy": copy,
        "enabled": enabled,
        "excluded": excluded,
    }


def apply_migrate(plan: dict[str, object]) -> dict[str, object]:
    """执行迁移计划；默认 dry-run，只有 ``plan["apply"]`` 为真才写盘。"""
    if not plan.get("apply"):
        return {"applied": False, "target": plan.get("target")}

    source = Path(str(plan["source"]))
    target = Path(str(plan["target"]))
    if target.exists():
        raise FileExistsError(f"target already exists: {target}")

    raw_copy = plan.get("copy")
    names = [str(item) for item in raw_copy] if isinstance(raw_copy, list) else []
    linked = bool(plan.get("link"))

    target.mkdir(parents=True)
    for name in names:
        src = source / name
        dst = target / name
        if linked:
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(dst), str(src)],
                check=True,
            )
        else:
            shutil.copytree(src, dst)

    raw_enabled = plan.get("enabled")
    enabled = [str(item) for item in raw_enabled] if isinstance(raw_enabled, list) else []
    (target / "enabled_mods.json").write_text(
        json.dumps({"enabledMods": enabled}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "applied": True,
        "target": str(target),
        "copied": len(names),
        "link": linked,
    }


def _format_text(data: dict[str, object]) -> str:
    loc = data["localization"]
    vmp = data["vmparams"]
    mods = data["mods"]
    assert isinstance(loc, dict)
    assert isinstance(vmp, dict)
    assert isinstance(mods, dict)

    def flag(value: object) -> str:
        return "true" if value else "false"

    def joined(value: object) -> str:
        items = value if isinstance(value, list) else []
        return ",".join(str(item) for item in items) or "-"

    return "\n".join([
        f"root={data['root']}",
        f"localization.version={loc['version']}",
        f"localization.branch={loc['branch']}",
        f"localization.language={loc['language']}",
        f"localization.game_version={loc['game_version']}",
        f"jre_version={data['jre_version']}",
        f"dyn_font={flag(data['dyn_font'])}",
        f"ssime_dll={flag(data['ssime_dll'])}",
        f"vmparams.path={vmp['path']}",
        f"vmparams.has_main_class={flag(vmp['has_main_class'])}",
        f"vmparams.has_agent={flag(vmp['has_agent'])}",
        f"vmparams.agents={joined(vmp['agents'])}",
        f"vmparams.hypernova_flags={joined(vmp['hypernova_flags'])}",
        f"mods.enabled_count={mods['enabled_count']}",
        f"mods.has_hypernova={flag(mods['has_hypernova'])}",
        f"mods.has_mixinfr={flag(mods['has_mixinfr'])}",
        f"mods.has_parallel={flag(mods['has_parallel'])}",
    ])


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="只读盘点安装根")
    inspect.add_argument("--root", required=True, type=Path)
    inspect.add_argument("--out", type=Path, help="把 JSON 结果写入该文件")
    inspect.add_argument("--text", action="store_true", help="以 key=value 输出")
    migrate = sub.add_parser("migrate", help="规划/执行 256 mod 迁移（默认 dry-run）")
    migrate.add_argument("--source", required=True, type=Path)
    migrate.add_argument("--target", required=True, type=Path)
    migrate.add_argument("--link", action="store_true", help="用目录联接代替复制")
    migrate.add_argument("--apply", action="store_true", help="真正写盘（默认只规划）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "migrate":
            plan = plan_migrate(args.source, args.target, link=args.link)
            if args.apply:
                plan["apply"] = True
                data = apply_migrate(plan)
            else:
                data = plan
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        data = inspect_root(args.root)
    except Exception as exc:  # noqa: BLE001 - 失败返回非零
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.text:
        print(_format_text(data))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
