"""M7 统一部署包：实验根盘点、256 mod 迁移与路线 B 安装。

Task 1 只读盘点；Task 2 迁移规划；Task 3 增加路线 B（FR 0.9.7rc2 +
jdk-28+13 + Hypernova，可选 Prepatcher）。路线 B 必须由显式
``jdk-28+13/bin/java.exe @route-b.vmparams`` 启动器启动：``starsector.exe``
与 ``fr.bat`` 都硬编码随包 JRE 17，不能用来跑 Java 28。所有写操作都必须
显式 ``--apply``，默认 dry-run；apply 前生成 M7 自己的回滚清单。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hn_json import load  # noqa: E402
import m6_env_snapshot  # noqa: E402  (快照复用；只调用，不修改 M6)
from install_agent import AGENT_LINE as _INSTALL_AGENT_LINE  # noqa: E402

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

# 保留项：不排除。即使源里未启用，也把文件夹随迁移复制过去（不写入
# enabled），供后续 disable-ime 等步骤按需启用。
PRESERVED_MOD_IDS = frozenset({"vramoptimizer", "chineseinputfix"})

# ---- 路线 B 常量（Task 3）----
# 启动链事实（审查 67fba6a）：starsector.exe 的 lpApplicationName 硬编码
# `..\jre\bin\java.exe`，vmparams 首 token 只是子进程 argv[0]；fr.bat 同样
# 硬编码 JRE 17。因此路线 B 必须生成 token-less argfile + 显式 java 启动器。
# Starsector 的启动档 CWD 是 starsector-core，所以 java/mods/argfile 都从
# 该目录相对定位。
JDK_DIR_NAME = "jdk-28+13"
JDK_JAVA_TOKEN = "..\\jdk-28+13\\bin\\java.exe"
ROUTE_B_VMPARAMS_NAME = "route-b.vmparams"
ROUTE_LAUNCHER_NAME = "launch-route-b.bat"
ROUTE_ROLLBACK_MANIFEST = "route-rollback.json"
HYPERNOVA_MOD_ID = "hypernova_infinite_engine"
HYPERNOVA_MOD_REL = Path("mods") / HYPERNOVA_MOD_ID
# 与 install_agent.AGENT_LINE 共用同一真源，避免路径漂移。
HYPERNOVA_AGENT_TOKEN = _INSTALL_AGENT_LINE
FR_AGENT_TOKEN = "-javaagent:fr.agent.jar"
PREPATCHER_MOD_REL = Path("mods") / "StarsectorPrepatcher"
PREPATCHER_AGENT_TOKEN = (
    "-javaagent:..\\mods\\StarsectorPrepatcher\\agent\\"
    "StarsectorPrepatcherAgent.jar"
)
ROUTE_B_FLAGS = (
    "-Dhypernova.textures.lazy=true",
    "-Dhypernova.textures.lazy.dds=true",
    "-Dhypernova.textures.lazy.eviction=true",
    "-Dhypernova.textures.lazy.eviction.sceneUnload=false",
)
# 回滚清单至少覆盖的配置/启动文件；apply 还会追加本次所有写入目标。
ROUTE_SNAPSHOT_PATHS = (
    VMPARAMS_PATH,
    "mods/enabled_mods.json",
    "mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json",
    "starsector-core/data/config/settings.json",
)
_HYPERNOVA_AGENT_NAMES = frozenset({
    "hypernova.agent.jar",
    "hypernova-agent.jar",
})
_FR_AGENT_NAME = "fr.agent.jar"
_PREPATCHER_AGENT_NAME = "starsectorprepatcheragent.jar"
_RELEASE_FIELD_RE = re.compile(r'^([A-Z_]+)="([^"]*)"', re.MULTILINE)
_MIXIN_MOD_NAMES = frozenset({"mixinfr", "mixinlib", "starsectorparallel"})


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
    """读取 enabled_mods.json；迁移场景必须 fail-closed。"""
    path = source_mods / "enabled_mods.json"
    if not path.is_file():
        raise FileNotFoundError(f"enabled_mods.json not found: {path}")
    try:
        payload = load(path)
    except Exception as exc:  # noqa: BLE001 - 迁移不能静默空跑
        raise ValueError(f"cannot parse {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: top-level must be an object")
    raw = payload.get("enabledMods")
    if not isinstance(raw, list):
        raise ValueError(f"{path}: enabledMods must be a list")
    if not raw:
        raise ValueError(f"{path}: enabledMods is empty")
    ids: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                f"{path}: enabledMods must contain non-empty strings")
        ids.append(item)
    return ids


def _scan_mod_folders(source_mods: Path) -> dict[str, object]:
    """扫描 mod_info.json，重复 id 规则与 ``mod_index.scan_mods`` 一致。

    重复 id 取 ``sorted(folders)[0]``（与游戏实际加载的文件夹一致），
    并把全部候选记录到 ``duplicate_ids``，让 dry-run 可审阅。
    """
    by_id: dict[str, list[tuple[str, str]]] = {}
    by_folder: dict[str, str] = {}
    for entry in sorted(source_mods.iterdir(), key=lambda item: item.name):
        if not entry.is_dir():
            continue
        by_folder[entry.name.lower()] = entry.name
        info = _read_json(entry / "mod_info.json")
        if isinstance(info, dict):
            mod_id = info.get("id")
            if isinstance(mod_id, str) and mod_id:
                by_id.setdefault(mod_id.lower(), []).append(
                    (mod_id, entry.name))

    folders: dict[str, str] = {}
    ids: dict[str, str] = {}
    all_folders: dict[str, list[str]] = {}
    duplicate_ids: dict[str, dict[str, object]] = {}
    for key, items in by_id.items():
        ordered = sorted(items, key=lambda item: item[1])
        chosen_id, chosen_folder = ordered[0]
        folders[key] = chosen_folder
        ids[key] = chosen_id
        all_folders[key] = [folder for _, folder in ordered]
        if len(ordered) > 1:
            duplicate_ids[chosen_id] = {
                "chosen": chosen_folder,
                "candidates": [folder for _, folder in ordered],
            }
    return {
        "folders": folders,
        "ids": ids,
        "all_folders": all_folders,
        "by_folder": by_folder,
        "duplicate_ids": duplicate_ids,
    }


def _preserved_extras(
    ids: dict[str, str],
    all_folders: dict[str, list[str]],
    by_folder: dict[str, str],
    copied: list[str],
) -> list[dict[str, str]]:
    """保留项中未启用的文件夹：复制但不写入 enabled。"""
    extras: list[dict[str, str]] = []
    seen = set(copied)
    for key, candidates in all_folders.items():
        if key not in PRESERVED_MOD_IDS or key in EXCLUDED_MOD_IDS:
            continue
        for folder in candidates:
            if folder in seen:
                continue
            seen.add(folder)
            extras.append({
                "id": ids.get(key, key),
                "folder": folder,
                "reason": "preserved but not enabled in source",
            })
    # 个别保留项没有可解析的 mod_info.json 时按文件夹名兜底。
    for key, folder in by_folder.items():
        if key not in PRESERVED_MOD_IDS or key in EXCLUDED_MOD_IDS:
            continue
        if folder in seen:
            continue
        seen.add(folder)
        extras.append({
            "id": key,
            "folder": folder,
            "reason": "preserved but no readable mod_info.json",
        })
    extras.sort(key=lambda item: item["folder"])
    return extras


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
    source = Path(source_mods).resolve()
    target = Path(target_mods).resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"source mods dir not found: {source}")

    enabled_ids = _enabled_ids(source)
    scan = _scan_mod_folders(source)
    folders = scan["folders"]
    ids = scan["ids"]
    all_folders = scan["all_folders"]
    by_folder = scan["by_folder"]
    duplicate_ids = scan["duplicate_ids"]
    assert isinstance(folders, dict)
    assert isinstance(ids, dict)
    assert isinstance(all_folders, dict)
    assert isinstance(by_folder, dict)
    assert isinstance(duplicate_ids, dict)

    copy: list[str] = []
    enabled: list[str] = []
    enabled_folders: dict[str, str] = {}
    missing: list[str] = []
    for mod_id in enabled_ids:
        key = mod_id.lower()
        if key in EXCLUDED_MOD_IDS:
            continue
        enabled.append(mod_id)
        # 优先按 id 映射；个别 mod 缺少 mod_info.json 时退回同名文件夹。
        folder = folders.get(key) or by_folder.get(key)
        if folder is None:
            missing.append(mod_id)
            continue
        enabled_folders[mod_id] = folder
        if folder not in copy:
            copy.append(folder)

    excluded_set: set[str] = set()
    for key, candidates in all_folders.items():
        if key in EXCLUDED_MOD_IDS:
            excluded_set.update(candidates)
    for key, folder in by_folder.items():
        if key in EXCLUDED_MOD_IDS:
            excluded_set.add(folder)
    excluded = sorted(excluded_set)

    extras = _preserved_extras(ids, all_folders, by_folder, copy)
    return {
        "source": str(source),
        "target": str(target),
        "link": bool(link),
        "apply": False,
        "copy": copy,
        "enabled": enabled,
        "enabled_folders": enabled_folders,
        "excluded": excluded,
        "extras": extras,
        "missing_enabled_ids": missing,
        "duplicate_ids": duplicate_ids,
    }


def apply_migrate(plan: dict[str, object]) -> dict[str, object]:
    """执行迁移计划；默认 dry-run，只有 ``plan["apply"]`` 为真才写盘。"""
    if not plan.get("apply"):
        return {"applied": False, "target": plan.get("target")}

    source = Path(str(plan["source"])).resolve()
    target = Path(str(plan["target"])).resolve()
    if target.exists():
        raise FileExistsError(f"target already exists: {target}")

    raw_copy = plan.get("copy")
    names = [str(item) for item in raw_copy] if isinstance(raw_copy, list) else []
    raw_extras = plan.get("extras")
    extras = raw_extras if isinstance(raw_extras, list) else []
    extra_names = [
        str(item["folder"]) for item in extras
        if isinstance(item, dict) and item.get("folder")
    ]
    all_names = names + [name for name in extra_names if name not in names]
    linked = bool(plan.get("link"))

    raw_enabled = plan.get("enabled")
    enabled = [str(item) for item in raw_enabled] if isinstance(raw_enabled, list) else []
    raw_enabled_folders = plan.get("enabled_folders")
    enabled_folders = (
        raw_enabled_folders if isinstance(raw_enabled_folders, dict) else {})
    raw_missing = plan.get("missing_enabled_ids")
    missing_ids = [str(item) for item in raw_missing] if isinstance(raw_missing, list) else []

    # fail-closed：空计划、悬空 id、未覆盖的 id 都不允许写盘。
    if not enabled:
        raise ValueError("refusing to apply migration with empty enabled list")
    if not names:
        raise ValueError("refusing to apply migration with empty copy list")
    if missing_ids:
        raise ValueError(
            "plan has unresolved enabled ids: " + ", ".join(missing_ids))
    uncovered = [
        mod_id for mod_id in enabled
        if str(enabled_folders.get(mod_id)) not in all_names
    ]
    if uncovered:
        raise ValueError(
            "enabled ids not covered by copy plan: " + ", ".join(uncovered))
    missing_sources = [
        name for name in all_names if not (source / name).is_dir()]
    if missing_sources:
        raise FileNotFoundError(
            "missing mod folders: " + ", ".join(missing_sources))

    target.mkdir(parents=True)
    try:
        for name in all_names:
            src = source / name
            dst = target / name
            if linked:
                proc = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(dst), str(src)],
                    capture_output=True, text=True, check=False,
                )
                if proc.returncode != 0:
                    detail = (proc.stderr or proc.stdout).strip()
                    raise RuntimeError(
                        f"mklink failed for {name}: {detail}")
            else:
                shutil.copytree(src, dst)
        missing_targets = [
            name for name in all_names if not (target / name).is_dir()]
        if missing_targets:
            raise ValueError(
                "copied mod folders missing in target: "
                + ", ".join(missing_targets))
        payload = {"enabledMods": enabled}
        tmp = target / "enabled_mods.json.tmp"
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, target / "enabled_mods.json")
    except BaseException:
        # 失败时清理本次创建的 target，避免留下半成品。
        shutil.rmtree(target, ignore_errors=True)
        raise

    return {
        "applied": True,
        "target": str(target),
        "copied": len(names),
        "extras_copied": len(extra_names),
        "total_copied": len(all_names),
        "enabled": len(enabled),
        "link": linked,
    }


def _route_b_intended_java(jdk_dir: str | Path) -> dict[str, object]:
    """读取 ``jdk-28+13/release``：这是**启动器打算使用**的 JDK，不是
    已经证实的运行时 JVM。实际生效版本必须由实机 ``java -version`` 或
    ``-Xlog`` 证据确认；``starsector.exe`` 本身固定用随包 JRE 17。
    """
    base = Path(jdk_dir)
    release = base / "release"
    java_exe = base / "bin" / "java.exe"
    data: dict[str, object] = {
        "release": str(release),
        "java_exe": str(java_exe),
        "java_exe_present": java_exe.is_file(),
        "java_version": None,
        "java_runtime_version": None,
        "implementor_version": None,
    }
    if release.is_file():
        text = release.read_text(encoding="utf-8-sig", errors="replace")
        fields = dict(_RELEASE_FIELD_RE.findall(text))
        data["java_version"] = fields.get("JAVA_VERSION")
        data["java_runtime_version"] = fields.get("JAVA_RUNTIME_VERSION")
        data["implementor_version"] = fields.get("IMPLEMENTOR_VERSION")
    return data


def _route_b_fr_version(fr_dir: str | Path) -> str | None:
    path = Path(fr_dir) / "fr.version.txt"
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace").strip() or None
    except OSError:
        return None


def _audit_root(root: str | Path) -> Path:
    """实验根的上层审计目录（`<audit>/install/<name>` → `<audit>`）。"""
    resolved = Path(root).resolve()
    if resolved.parent.name.lower() == "install":
        return resolved.parent.parent
    return resolved.parent


def _default_backups(root: str | Path) -> Path:
    return _audit_root(root) / "backups"


def _validate_snapshot_label(label: str) -> str:
    if not isinstance(label, str) or not label or label in {".", ".."}:
        raise ValueError(f"invalid snapshot label: {label!r}")
    if "/" in label or "\\" in label:
        raise ValueError(f"invalid snapshot label: {label!r}")
    candidate = Path(label)
    if candidate.is_absolute() or candidate.drive or candidate.name != label:
        raise ValueError(f"invalid snapshot label: {label!r}")
    return label


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*")):
        if not item.is_file():
            continue
        rel = item.relative_to(path).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256_file(item).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _route_launcher_path(root: str | Path) -> Path:
    return _audit_root(root) / "scripts" / ROUTE_LAUNCHER_NAME


def _route_launcher_text(root: str | Path) -> str:
    scripts = _route_launcher_path(root).parent
    core = (Path(root).resolve() / "starsector-core")
    core_rel = os.path.relpath(core, scripts.resolve()).replace("/", "\\")
    lines = [
        "@echo off",
        "setlocal",
        "rem M7 Route B: explicit Java 28 launcher.",
        "rem starsector.exe always starts ..\\jre\\bin\\java.exe (JRE 17);",
        "rem this script is the only route B entry point.",
        f'cd /d "%~dp0{core_rel}"',
        f'"{JDK_JAVA_TOKEN}" @..\\{ROUTE_B_VMPARAMS_NAME}',
    ]
    return "\r\n".join(lines) + "\r\n"


def _enabled_mods_state(path: Path) -> dict[str, object]:
    """区分 missing / parse-error / ok；apply 必须 fail-closed。"""
    if not path.is_file():
        return {"state": "missing", "ids": [], "payload": None, "error": None}
    try:
        payload = load(path)
    except Exception as exc:  # noqa: BLE001 - 由调用方决定 fail-closed
        return {"state": "error", "ids": [], "payload": None,
                "error": str(exc)}
    if not isinstance(payload, dict):
        return {"state": "error", "ids": [], "payload": None,
                "error": "top-level must be an object"}
    raw = payload.get("enabledMods")
    if not isinstance(raw, list):
        return {"state": "error", "ids": [], "payload": None,
                "error": "enabledMods must be a list"}
    ids: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            return {"state": "error", "ids": [], "payload": None,
                    "error": "enabledMods must contain non-empty strings"}
        ids.append(item)
    return {"state": "ok", "ids": ids, "payload": payload, "error": None}


def _snapshot_paths(root: Path, paths: list[str | Path]) -> list[Path]:
    """把相对/绝对路径规范化，并限制在实验根或审计目录内。"""
    resolved_root = root.resolve()
    allowed = (resolved_root, _audit_root(root).resolve())
    normalized: list[Path] = []
    seen: set[Path] = set()
    for raw in paths:
        candidate = Path(raw)
        target = (candidate if candidate.is_absolute()
                  else resolved_root / candidate).resolve()
        if not any(target.is_relative_to(base) for base in allowed):
            raise ValueError(f"snapshot path escapes install/audit root: {raw}")
        if target not in seen:
            seen.add(target)
            normalized.append(target)
    return normalized


def snapshot_route(
    root: str | Path,
    label: str,
    *,
    paths: list[str | Path] | None = None,
    dest: str | Path | None = None,
) -> dict[str, object]:
    """M7 自建回滚快照：逐路径记录 existed_before / 备份 / sha256。

    与 M6 快照并存（M6 仍按全局约束先跑），但回滚只依赖本清单，因为它
    覆盖 ``vmparams``、生成文件与 absent-before 的删除语义。
    """
    base = Path(root).resolve()
    if not base.is_dir():
        raise FileNotFoundError(f"install root not found: {base}")
    label = _validate_snapshot_label(label)
    snap = (Path(dest).resolve() if dest is not None
            else _default_backups(base).resolve()) / label
    manifest_path = snap / ROUTE_ROLLBACK_MANIFEST
    if manifest_path.exists():
        raise FileExistsError(f"route rollback snapshot already exists: {snap}")

    raw_paths = list(paths) if paths is not None else list(ROUTE_SNAPSHOT_PATHS)
    targets = _snapshot_paths(base, raw_paths)
    backups = snap / "rollback"
    entries: list[dict[str, object]] = []
    for index, target in enumerate(targets):
        try:
            rel = target.relative_to(base).as_posix()
        except ValueError:
            rel = None
        entry: dict[str, object] = {
            "path": str(target),
            "rel": rel,
            "existed_before": False,
            "kind": "absent",
            "backup": None,
            "sha256": None,
            "tree_sha256": None,
            "file_count": 0,
        }
        if target.is_file():
            backup = backups / f"{index:04d}.file"
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
            entry.update({
                "existed_before": True,
                "kind": "file",
                "backup": backup.relative_to(snap).as_posix(),
                "sha256": _sha256_file(target),
                "size": target.stat().st_size,
            })
        elif target.is_dir():
            backup = backups / f"{index:04d}.dir"
            shutil.copytree(target, backup)
            file_count = sum(1 for item in target.rglob("*") if item.is_file())
            entry.update({
                "existed_before": True,
                "kind": "dir",
                "backup": backup.relative_to(snap).as_posix(),
                "tree_sha256": _tree_digest(target),
                "file_count": file_count,
            })
        entries.append(entry)

    meta = {
        "version": 1,
        "route": "b",
        "root": str(base),
        "label": label,
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "entries": entries,
    }
    snap.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return meta


def _load_rollback_manifest(
    root: Path, label: str, dest: str | Path | None
) -> tuple[Path, dict[str, object]]:
    label = _validate_snapshot_label(label)
    snap = (Path(dest).resolve() if dest is not None
            else _default_backups(root).resolve()) / label
    manifest_path = snap / ROUTE_ROLLBACK_MANIFEST
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"missing route rollback manifest: {manifest_path}")
    meta = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(meta, dict) or meta.get("version") != 1:
        raise ValueError("unsupported route rollback manifest")
    if Path(str(meta.get("root"))).resolve() != root.resolve():
        raise ValueError("rollback manifest root does not match")
    entries = meta.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("empty route rollback manifest")
    allowed = (root.resolve(), _audit_root(root).resolve())
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("invalid rollback entry")
        target = Path(str(entry.get("path"))).resolve()
        if not any(target.is_relative_to(base) for base in allowed):
            raise ValueError(f"rollback path escapes install/audit root: {target}")
    return snap, meta


def rollback_route(
    root: str | Path,
    label: str,
    *,
    dest: str | Path | None = None,
    apply: bool = False,
) -> dict[str, object]:
    """按 M7 回滚清单恢复：existed_before → 恢复；absent-before → 删除。"""
    base = Path(root).resolve()
    snap, meta = _load_rollback_manifest(base, label, dest)
    entries = meta["entries"]
    assert isinstance(entries, list)

    actions: list[dict[str, object]] = []
    for entry in entries:
        assert isinstance(entry, dict)
        target = Path(str(entry["path"])).resolve()
        existed = bool(entry.get("existed_before"))
        action = "absent"
        if existed:
            backup_rel = entry.get("backup")
            if not backup_rel:
                raise ValueError(f"missing backup for {target}")
            backup = (snap / str(backup_rel)).resolve()
            if not backup.is_relative_to(snap):
                raise ValueError(f"backup escapes snapshot: {backup}")
            if entry.get("kind") == "file":
                if not backup.is_file():
                    raise FileNotFoundError(f"missing snapshot file: {backup}")
                expected = str(entry.get("sha256"))
                if _sha256_file(backup) != expected:
                    raise ValueError(f"snapshot payload sha256 mismatch: {backup}")
                if target.is_file() and _sha256_file(target) == expected:
                    action = "unchanged"
                else:
                    action = "restore-file"
            else:
                if not backup.is_dir():
                    raise FileNotFoundError(f"missing snapshot tree: {backup}")
                expected_tree = str(entry.get("tree_sha256"))
                if _tree_digest(backup) != expected_tree:
                    raise ValueError(f"snapshot tree digest mismatch: {backup}")
                if target.is_dir() and _tree_digest(target) == expected_tree:
                    action = "unchanged"
                else:
                    action = "restore-tree"
        elif target.exists():
            action = "delete"
        actions.append({"path": str(target), "kind": entry.get("kind"),
                        "action": action})

    result: dict[str, object] = {
        "applied": bool(apply),
        "root": str(base),
        "label": label,
        "snapshot": str(snap),
        "actions": actions,
        "restored": 0,
        "deleted": 0,
    }
    if not apply:
        return result

    restored = 0
    for entry, item in zip(entries, actions):
        assert isinstance(entry, dict)
        action = item["action"]
        target = Path(str(item["path"]))
        if action in {"restore-file", "restore-tree"}:
            backup = (snap / str(entry["backup"])).resolve()
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            target.parent.mkdir(parents=True, exist_ok=True)
            if action == "restore-file":
                shutil.copy2(backup, target)
            else:
                shutil.copytree(backup, target)
            restored += 1
    deleted = 0
    deletes = [item for item in actions if item["action"] == "delete"]
    deletes.sort(key=lambda item: len(Path(str(item["path"])).parts),
                 reverse=True)
    for item in deletes:
        target = Path(str(item["path"]))
        if target.is_dir():
            shutil.rmtree(target)
        elif target.is_file():
            target.unlink()
        deleted += 1
    result["restored"] = restored
    result["deleted"] = deleted
    result["ok"] = True
    return result


def _reject_route_a_components(root: Path, tokens: list[str]) -> None:
    """路线 B 不允许混入 MixinFR/MixinLib/StarsectorParallel（R1 隔离）。"""
    lowered = [token.lower() for token in tokens]
    if any("mixinlib-bridge.jar" in token or "mixinfr" in token
           for token in lowered):
        raise ValueError("route B must not mix MixinFR/MixinLib javaagents")
    mods = root / "mods"
    if mods.is_dir():
        for entry in mods.iterdir():
            if entry.is_dir() and entry.name.lower() in _MIXIN_MOD_NAMES:
                raise ValueError(
                    f"route B must not mix route A mod: {entry.name}")


def _hypernova_agent_source(hypernova_mod: str | Path) -> Path:
    """返回 agent jar 源文件：优先打包目录，其次仓库构建产物。"""
    base = Path(hypernova_mod)
    packaged = base / "jars" / "hypernova.agent.jar"
    if packaged.is_file():
        return packaged
    return base / "build" / "agent" / "hypernova.agent.jar"


def _route_b_copies(
    root: Path,
    fr_dir: str | Path,
    jdk_dir: str | Path,
    hypernova_mod: str | Path,
    prepatcher_dir: str | Path | None,
) -> list[dict[str, object]]:
    """列出路线 B 的复制清单（只描述意图，不写盘）。"""

    def entry(src: Path, dst: Path, kind: str = "file") -> dict[str, object]:
        exists = src.is_dir() if kind == "tree" else src.is_file()
        return {"src": str(src), "dst": str(dst), "kind": kind,
                "exists": exists}

    copies: list[dict[str, object]] = []
    core = root / "starsector-core"
    fr = Path(fr_dir)
    if fr.is_dir():
        for item in sorted(fr.iterdir(), key=lambda path: path.name.lower()):
            if item.is_file():
                copies.append(entry(item, core / item.name))

    copies.append(entry(Path(jdk_dir), root / JDK_DIR_NAME, "tree"))

    hn = Path(hypernova_mod)
    mod_dir = root / HYPERNOVA_MOD_REL
    copies.append(entry(hn / "mod_info.json", mod_dir / "mod_info.json"))
    packaged = (hn / "jars" / "hypernova.jar").is_file()
    if packaged:
        copies.append(entry(hn / "jars", mod_dir / "jars", "tree"))
    else:
        copies.append(entry(hn / "build" / "java" / "hypernova.jar",
                            mod_dir / "jars" / "hypernova.jar"))
        copies.append(entry(_hypernova_agent_source(hn),
                            mod_dir / "jars" / "hypernova.agent.jar"))
    copies.append(entry(hn / "data", mod_dir / "data", "tree"))
    copies.append(entry(hn / "graphics", mod_dir / "graphics", "tree"))
    # 淘汰占位图必须同时在 starsector-core（agent-only 安装下 mod 目录
    # 不保证被 FileLoader 扫描）；见 tools/java/install-manifest.sh。
    copies.append(entry(hn / "graphics" / "hypernova" / "blank.png",
                        core / "graphics" / "hypernova" / "blank.png"))
    if prepatcher_dir is not None:
        copies.append(entry(Path(prepatcher_dir),
                            root / PREPATCHER_MOD_REL, "tree"))
    return copies


def _route_b_enabled_mods(root: Path,
                          prepatcher: bool) -> dict[str, object]:
    path = root / ENABLED_MODS_PATH
    state = _enabled_mods_state(path)
    current = state["ids"] if state["state"] == "ok" else []
    assert isinstance(current, list)
    wanted = [HYPERNOVA_MOD_ID]
    if prepatcher:
        wanted.append("starsector_prepatcher")
    lower = {item.lower() for item in current}
    return {
        "path": str(path),
        "present": path.is_file(),
        "state": state["state"],
        "error": state["error"],
        "current_count": len(current),
        "add": [item for item in wanted if item.lower() not in lower],
    }


def _read_mod_id(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"mod_info.json not found: {path}")
    payload = load(path)
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: top-level must be an object")
    mod_id = payload.get("id")
    if not isinstance(mod_id, str) or not mod_id:
        raise ValueError(f"{path}: missing string id")
    return mod_id


def _prepatcher_capabilities(prepatcher_dir: Path) -> dict[str, object]:
    """只读能力检查；不修改 prepatcher.properties（保持 production 默认）。"""
    props = prepatcher_dir / "prepatcher.properties"
    if not props.is_file():
        return {"properties_present": False, "enabled": None,
                "patch_count": 0}
    try:
        text = props.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return {"properties_present": False, "enabled": None,
                "patch_count": 0}
    enabled_match = re.search(r"^enabled\s*=\s*(true|false)\s*$", text,
                              re.MULTILINE | re.IGNORECASE)
    return {
        "properties_present": True,
        "enabled": None if enabled_match is None
        else enabled_match.group(1).lower() == "true",
        "patch_count": len(re.findall(r"^patch\.[^=\s]+=true\s*$", text,
                                      re.MULTILINE)),
    }


def _route_b_snapshot_plan(root: Path) -> dict[str, object]:
    resolved = root.resolve()
    label = "m7-route-b-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return {
        "game_root": str(resolved),
        "dest": str(_default_backups(resolved)),
        "label": label,
        "m6_files": list(m6_env_snapshot.SNAPSHOT_FILES),
        "rollback_manifest": ROUTE_ROLLBACK_MANIFEST,
        "route_files": list(ROUTE_SNAPSHOT_PATHS),
    }


def _route_b_arguments(tokens: list[str]) -> list[str]:
    """生成 token-less 参数序列：丢掉原启动档的 argv[0]。

    原 vmparams 的首 token 是给 ``starsector.exe`` 的 argv[0]，不是 JVM
    参数；直接喂给 ``java @argfile`` 会被当作主类。若输入本身已 token-less
    （首 token 以 ``-`` 开头或就是主类），原样保留，保证幂等。
    """
    args = list(tokens)
    if args and not args[0].startswith("-") and args[0] != MAIN_CLASS:
        args = args[1:]
    return args


def _route_b_tokens(tokens: list[str], *, prepatcher: bool) -> list[str]:
    """清洗旧注入并生成路线 B 的 token-less 参数序列。"""
    out: list[str] = []
    for token in tokens:
        lowered = token.lower()
        if lowered.startswith("-javaagent:"):
            name = lowered[len("-javaagent:"):].replace("\\", "/")
            name = name.rsplit("/", 1)[-1]
            if (name in _HYPERNOVA_AGENT_NAMES
                    or name == _FR_AGENT_NAME
                    or name == _PREPATCHER_AGENT_NAME):
                continue
        if lowered.startswith("-dhypernova."):
            continue
        out.append(token)

    if MAIN_CLASS not in out:
        raise ValueError(f"vmparams has no main class: {MAIN_CLASS}")

    # 显式 java 启动器的 argfile 也必须把 fr.jar 放到 classpath 首位。
    for index, token in enumerate(out[:-1]):
        if token in ("-classpath", "-cp"):
            parts = out[index + 1].split(";")
            if "fr.jar" not in {part.lower() for part in parts}:
                out[index + 1] = "fr.jar;" + out[index + 1]
            break

    insert_at = out.index(MAIN_CLASS)
    for index, token in enumerate(out):
        if token in ("-classpath", "-cp"):
            insert_at = index
            break

    options = list(ROUTE_B_FLAGS) + [HYPERNOVA_AGENT_TOKEN, FR_AGENT_TOKEN]
    if prepatcher:
        options.append(PREPATCHER_AGENT_TOKEN)
    return out[:insert_at] + options + out[insert_at:]


def plan_route_b(
    root: str | Path,
    *,
    fr_dir: str | Path,
    jdk_dir: str | Path,
    hypernova_mod: str | Path,
    prepatcher_dir: str | Path | None = None,
) -> dict[str, object]:
    """规划路线 B（FR 0.9.7rc2 + jdk-28+13 + Hypernova）。

    只读：返回新的 vmparams 行、effective Java 与复制清单。写盘必须显式
    调用 ``apply_route_b`` 并先经过 ``m6_env_snapshot.snapshot``。
    """
    base = Path(root)
    if not base.is_dir():
        raise FileNotFoundError(f"install root not found: {base}")
    vmparams = base / VMPARAMS_PATH
    if not vmparams.is_file():
        raise FileNotFoundError(f"vmparams not found: {vmparams}")
    original = vmparams.read_text(encoding="utf-8-sig", errors="replace")
    tokens = original.split()
    if not tokens:
        raise ValueError(f"empty vmparams: {vmparams}")

    _reject_route_a_components(base, tokens)
    args = _route_b_arguments(tokens)
    new_line = " ".join(
        _route_b_tokens(args, prepatcher=prepatcher_dir is not None))
    route_b_vmparams = base / ROUTE_B_VMPARAMS_NAME
    launcher_path = _route_launcher_path(base)
    launcher_text = _route_launcher_text(base)

    copies = _route_b_copies(base, fr_dir, jdk_dir, hypernova_mod,
                             prepatcher_dir)
    intended_java = _route_b_intended_java(jdk_dir)
    intended_java["launcher_java"] = JDK_JAVA_TOKEN
    intended_java["target"] = str(base / JDK_DIR_NAME / "bin" / "java.exe")
    fr_version = _route_b_fr_version(fr_dir)

    warnings: list[str] = []
    for item in copies:
        if not item["exists"]:
            warnings.append(f"missing source: {item['src']}")
    agent_source = _hypernova_agent_source(hypernova_mod)
    if not agent_source.is_file():
        warnings.append(f"missing agent jar: {agent_source}")
    hypernova_json = (Path(hypernova_mod) / "data" / "config" /
                      "hypernova" / "hypernova.json")
    if not hypernova_json.is_file():
        warnings.append(f"missing hypernova.json: {hypernova_json}")
    if not Path(str(intended_java["java_exe"])).is_file():
        warnings.append(
            f"jdk java.exe not found: {intended_java['java_exe']}")
    if fr_version is None:
        warnings.append(f"fr.version.txt not found under {fr_dir}")
    elif "0.9.7rc2" not in fr_version:
        warnings.append(f"unexpected FR version: {fr_version}")
    intended_version = intended_java.get("java_version")
    if intended_version is None:
        warnings.append(f"cannot read intended Java version from {jdk_dir}")
    elif str(intended_version) != "28":
        warnings.append(
            f"intended Java is {intended_version}, expected 28 for route B")
    warnings.append(
        "starsector.exe and fr.bat hardcode ..\\jre\\bin\\java.exe (JRE 17); "
        "only the generated launcher bat runs jdk-28+13")

    prepatcher: dict[str, object] | None = None
    if prepatcher_dir is not None:
        pp = Path(prepatcher_dir)
        agent = pp / "agent" / "StarsectorPrepatcherAgent.jar"
        capabilities = _prepatcher_capabilities(pp)
        prepatcher = {
            "dir": str(pp),
            "dst": str(base / PREPATCHER_MOD_REL),
            "agent": str(agent),
            "agent_present": agent.is_file(),
            "version": "0.18.4",
            "java28_declared": False,
            "experimental": True,
            **capabilities,
        }
        if not agent.is_file():
            warnings.append(f"missing Prepatcher agent: {agent}")
        if capabilities.get("enabled") is False:
            warnings.append(
                "Prepatcher is disabled in prepatcher.properties; route B "
                "expects the default production profile (enabled=true)")
        warnings.append(
            "StarsectorPrepatcher 0.18.4 does not declare Java 28 support; "
            "experimental only")

    agents = [HYPERNOVA_AGENT_TOKEN, FR_AGENT_TOKEN]
    if prepatcher_dir is not None:
        agents.append(PREPATCHER_AGENT_TOKEN)

    vram_present = (base / "mods" / "VramOptimizer").is_dir()
    if not vram_present:
        warnings.append(
            "VramOptimizer not present in target mods; apply the 256-mod "
            "migration (Task 2) before route B")

    mod_ids: dict[str, str] = {
        HYPERNOVA_MOD_ID: str(Path(hypernova_mod) / "mod_info.json"),
    }
    if prepatcher_dir is not None:
        mod_ids["starsector_prepatcher"] = str(
            Path(prepatcher_dir) / "mod_info.json")
    for mod_id, info_path in mod_ids.items():
        try:
            actual = _read_mod_id(Path(info_path))
        except Exception as exc:  # noqa: BLE001 - dry-run 只告警
            warnings.append(f"cannot verify mod id for {mod_id}: {exc}")
            continue
        if actual != mod_id:
            warnings.append(
                f"mod_info id mismatch: {info_path} is {actual!r}, "
                f"expected {mod_id!r}")

    enabled_mods = _route_b_enabled_mods(
        base, prepatcher_dir is not None)
    if enabled_mods["state"] == "error":
        warnings.append(
            "enabled_mods.json is unreadable/invalid; apply will refuse to "
            f"write it: {enabled_mods['error']}")

    rollback_paths = [
        VMPARAMS_PATH,
        ROUTE_B_VMPARAMS_NAME,
        str(launcher_path),
        ENABLED_MODS_PATH,
        "starsector-core/data/config/settings.json",
        "starsector-core/fr.vmparams.bak-hypernova",
        str(base / HYPERNOVA_MOD_REL),
        str(base / HYPERNOVA_MOD_REL / "data/config/hypernova/hypernova.json"),
    ]
    rollback_paths.extend(str(item["dst"]) for item in copies)

    writes = [
        {"path": str(route_b_vmparams), "kind": "file",
         "content": new_line + "\n"},
        {"path": str(launcher_path), "kind": "file",
         "content": launcher_text},
    ]

    return {
        "route": "b",
        "name": ROUTES["b"]["name"],
        "root": str(base),
        "apply": False,
        "java": JDK_JAVA_TOKEN,
        "java_target": str(base / JDK_DIR_NAME / "bin" / "java.exe"),
        "intended_java": intended_java,
        "effective_java": {
            "verified": False,
            "java_version": None,
            "evidence": None,
            "note": "runtime JVM version is not proven; collect java -version "
                    "or -Xlog evidence in smoke before claiming Java 28",
        },
        "launcher": {
            "kind": "explicit-java",
            "java": JDK_JAVA_TOKEN,
            "java_target": str(base / JDK_DIR_NAME / "bin" / "java.exe"),
            "bat": str(launcher_path),
            "bat_content": launcher_text,
            "cwd": str(base / "starsector-core"),
            "argfile": f"..\\{ROUTE_B_VMPARAMS_NAME}",
            "argfile_path": str(route_b_vmparams),
            "command": f"{JDK_JAVA_TOKEN} @..\\{ROUTE_B_VMPARAMS_NAME}",
            "note": "starsector.exe/fr.bat hardcode ..\\jre\\bin\\java.exe "
                    "(JRE 17); this explicit launcher is the only Java 28 "
                    "entry point",
        },
        "starsector_exe": {
            "java": "..\\jre\\bin\\java.exe",
            "jre_version": _jre_version(base),
            "route_b": False,
            "note": "hardcoded lpApplicationName; fallback/control only",
        },
        "bundled_jre_version": _jre_version(base),
        "fr_version": fr_version,
        "root_vmparams_path": str(vmparams),
        "root_vmparams_modified": False,
        "source_vmparams_sha256": _sha256_file(vmparams),
        "hypernova_config": str(hypernova_json),
        "vmparams_path": str(route_b_vmparams),
        "vmparams": new_line,
        "vmparams_tokenless": True,
        "vmparams_changed": False,
        "agents": agents,
        "flags": list(ROUTE_B_FLAGS),
        "writes": writes,
        "copies": copies,
        "copy_count": len(copies),
        "missing_sources": [str(item["src"]) for item in copies
                            if not item["exists"]],
        "agent_jar": str(agent_source),
        "enabled_mods": enabled_mods,
        "mod_ids": mod_ids,
        "vram_optimizer": {
            "present": vram_present,
            "source": "256-mod migration (Task 2)",
        },
        "prepatcher": prepatcher,
        "snapshot": _route_b_snapshot_plan(base),
        "rollback_paths": rollback_paths,
        "warnings": warnings,
    }


def _apply_enabled_mods(root: Path, spec: dict[str, object]) -> dict[str, object]:
    """合并启用列表；parse error 必须 fail-closed，不能覆盖 256 列表。"""
    path_text = spec.get("path")
    path = Path(str(path_text)) if path_text else root / ENABLED_MODS_PATH
    state = _enabled_mods_state(path)
    if state["state"] == "error":
        raise ValueError(
            f"refusing to overwrite invalid enabled_mods.json: {state['error']}")
    ids = list(state["ids"]) if isinstance(state["ids"], list) else []
    payload = state.get("payload")
    base_payload = dict(payload) if isinstance(payload, dict) else {}
    lower = {item.lower() for item in ids}
    raw_add = spec.get("add")
    add = [str(item) for item in raw_add] if isinstance(raw_add, list) else []
    added: list[str] = []
    for mod_id in add:
        if mod_id.lower() not in lower:
            ids.append(mod_id)
            lower.add(mod_id.lower())
            added.append(mod_id)
    base_payload["enabledMods"] = ids
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(base_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)
    return {"path": str(path), "added": added, "count": len(ids)}


def _apply_install_manifest(root: Path) -> dict[str, object]:
    try:
        from install_manifest import install  # noqa: PLC0415 - apply 才加载
        result = install(root)
    except Exception as exc:  # noqa: BLE001 - 汇总进 apply 报告
        return {"ok": False, "error": str(exc)}
    stats = result.full.get("stats") if isinstance(result.full, dict) else {}
    stats = stats if isinstance(stats, dict) else {}
    critical = [finding.code for finding in result.findings
                if finding.severity == "Critical"]
    return {
        "ok": not critical,
        "out": str(result.out),
        "critical": critical,
        "l1_count": stats.get("l1_count"),
        "l2_count": stats.get("l2_count"),
        "l3_count": stats.get("l3_count"),
        "skip_count": result.skip_count,
    }


def _apply_install_agent(root: Path, agent_jar: str | Path) -> dict[str, object]:
    tool = Path(__file__).resolve().with_name("install_agent.py")
    cmd = [sys.executable, "-I", str(tool), "--game", str(root),
           "--env", "base", "--jar", str(agent_jar)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "cmd": cmd,
    }


def apply_route_b(plan: dict[str, object]) -> dict[str, object]:
    """执行路线 B 计划。默认 dry-run；只有 ``plan["apply"]`` 为真才写盘。

    写盘顺序：校验源与 enabled_mods → M6 快照（全局约束）+ M7 回滚快照
    → token-less argfile + 显式 Java 28 启动器 → 复制 FR/jdk/Hypernova
    [/Prepatcher] → 合并 enabled_mods → manifest → install_agent（JRE 17
    回退路径）。根 ``vmparams`` 不改写。
    """
    if not plan.get("apply"):
        return {"applied": False, "root": plan.get("root")}

    root = Path(str(plan["root"]))
    raw_copies = plan.get("copies")
    copies = raw_copies if isinstance(raw_copies, list) else []
    missing = [str(Path(str(item["src"])).resolve()) for item in copies
               if not Path(str(item["src"])).exists()]
    agent_jar = Path(str(plan.get("agent_jar") or "")).resolve()
    if not agent_jar.is_file() and str(agent_jar) not in missing:
        missing.append(str(agent_jar))
    intended = plan.get("intended_java")
    intended = intended if isinstance(intended, dict) else {}
    java_exe = Path(str(intended.get("java_exe") or ""))
    if not java_exe.is_file() and str(java_exe) not in missing:
        missing.append(str(java_exe))
    hypernova_config = Path(str(plan.get("hypernova_config") or ""))
    if not hypernova_config.is_file() and str(hypernova_config) not in missing:
        missing.append(str(hypernova_config))
    if missing:
        raise FileNotFoundError(
            "missing route-b sources: " + ", ".join(missing))

    expected_vm_sha = plan.get("source_vmparams_sha256")
    if expected_vm_sha:
        source_vmparams = root / VMPARAMS_PATH
        if (not source_vmparams.is_file()
                or _sha256_file(source_vmparams) != str(expected_vm_sha)):
            raise ValueError(
                "source vmparams changed after planning; replan route-b")

    # enabled_mods 解析失败必须在任何写盘之前拒绝，绝不能覆盖 256 列表。
    raw_enabled = plan.get("enabled_mods")
    enabled_spec = raw_enabled if isinstance(raw_enabled, dict) else {}
    enabled_path = Path(str(enabled_spec.get("path") or
                            root / ENABLED_MODS_PATH))
    _snapshot_paths(root, [enabled_path])
    state = _enabled_mods_state(enabled_path)
    if state["state"] == "error":
        raise ValueError(
            f"refusing to apply with invalid enabled_mods.json: "
            f"{state['error']}")
    raw_add = enabled_spec.get("add")
    add_ids = [str(item) for item in raw_add] if isinstance(raw_add, list) else []
    raw_mod_ids = plan.get("mod_ids")
    mod_ids = raw_mod_ids if isinstance(raw_mod_ids, dict) else {}
    for mod_id in add_ids:
        info_path = mod_ids.get(mod_id)
        if not info_path:
            raise ValueError(f"no mod_info.json declared for {mod_id!r}")
        actual = _read_mod_id(Path(str(info_path)))
        if actual != mod_id:
            raise ValueError(
                f"mod_info id mismatch: {info_path} is {actual!r}, "
                f"expected {mod_id!r}")

    raw_writes = plan.get("writes")
    writes = raw_writes if isinstance(raw_writes, list) else []
    if not writes:
        raise ValueError("route-b plan has no generated files")
    raw_rollback = plan.get("rollback_paths")
    rollback_paths = (raw_rollback if isinstance(raw_rollback, list)
                      else list(ROUTE_SNAPSHOT_PATHS))

    # 快照先行：M6（全局约束） + M7 自己的完整回滚清单。
    raw_snapshot = plan.get("snapshot")
    snapshot = raw_snapshot if isinstance(raw_snapshot, dict) else {}
    dest = snapshot.get("dest")
    label = snapshot.get("label")
    if not dest or not label:
        raise ValueError("route-b plan has no snapshot dest/label")
    dest_path = Path(str(dest))
    snapshot_meta = m6_env_snapshot.snapshot(root, str(dest_path), str(label))
    snapshot_dir = dest_path.resolve() / str(label)
    rollback_meta = snapshot_route(
        root, str(label), paths=rollback_paths, dest=dest_path)

    generated: list[str] = []
    for item in writes:
        if not isinstance(item, dict) or not item.get("path"):
            raise ValueError("invalid route-b generated file entry")
        target = Path(str(item["path"]))
        _snapshot_paths(root, [target])
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="") as handle:
            handle.write(str(item.get("content", "")))
        generated.append(str(target))

    copied: list[str] = []
    for item in copies:
        src = Path(str(item["src"])).resolve()
        dst = Path(str(item["dst"]))
        _snapshot_paths(root, [dst])
        if item.get("kind") == "tree":
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        copied.append(str(dst))

    enabled = _apply_enabled_mods(root, enabled_spec)
    manifest = _apply_install_manifest(root)
    agent = _apply_install_agent(root, agent_jar)
    ok = bool(manifest.get("ok")) and agent.get("returncode") == 0
    return {
        "applied": True,
        "ok": ok,
        "root": str(root),
        "snapshot": snapshot_meta,
        "rollback": {
            "dest": str(snapshot_dir.parent),
            "label": str(label),
            "manifest": str(snapshot_dir / ROUTE_ROLLBACK_MANIFEST),
            "entries": len(rollback_meta.get("entries", [])),
        },
        "generated": generated,
        "vmparams": plan["vmparams"],
        "root_vmparams_modified": False,
        "copied": copied,
        "enabled_mods": enabled,
        "manifest": manifest,
        "agent": agent,
        "launcher": plan.get("launcher"),
        "intended_java": plan.get("intended_java"),
        "effective_java": plan.get("effective_java"),
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


def _format_migrate_text(data: dict[str, object]) -> str:
    def flag(value: object) -> str:
        return "true" if value else "false"

    def joined(value: object) -> str:
        items = value if isinstance(value, list) else []
        return ",".join(str(item) for item in items) or "-"

    if "applied" in data:
        return "\n".join([
            f"applied={flag(data.get('applied'))}",
            f"target={data.get('target')}",
            f"copied={data.get('copied', 0)}",
            f"extras_copied={data.get('extras_copied', 0)}",
            f"total_copied={data.get('total_copied', 0)}",
            f"enabled={data.get('enabled', 0)}",
            f"link={flag(data.get('link'))}",
        ])

    raw_extras = data.get("extras")
    extras = [
        str(item.get("folder")) for item in raw_extras
        if isinstance(item, dict) and item.get("folder")
    ] if isinstance(raw_extras, list) else []
    raw_duplicates = data.get("duplicate_ids")
    duplicates: list[str] = []
    if isinstance(raw_duplicates, dict):
        for mod_id, info in raw_duplicates.items():
            if isinstance(info, dict):
                duplicates.append(f"{mod_id}:{info.get('chosen')}")
    raw_copy = data.get("copy")
    raw_enabled = data.get("enabled")
    return "\n".join([
        f"source={data.get('source')}",
        f"target={data.get('target')}",
        f"link={flag(data.get('link'))}",
        f"apply={flag(data.get('apply'))}",
        f"copy={len(raw_copy) if isinstance(raw_copy, list) else 0}",
        f"enabled={len(raw_enabled) if isinstance(raw_enabled, list) else 0}",
        f"excluded={joined(data.get('excluded'))}",
        f"extras={joined(extras)}",
        f"missing_enabled_ids={joined(data.get('missing_enabled_ids'))}",
        f"duplicate_ids={joined(duplicates)}",
    ])


def _format_route_b_text(data: dict[str, object]) -> str:
    def flag(value: object) -> str:
        return "true" if value else "false"

    def joined(value: object) -> str:
        items = value if isinstance(value, list) else []
        return ",".join(str(item) for item in items) or "-"

    if "applied" in data:
        raw_rollback = data.get("rollback")
        rollback = raw_rollback if isinstance(raw_rollback, dict) else {}
        generated = data.get("generated")
        copied = data.get("copied")
        return "\n".join([
            f"applied={flag(data.get('applied'))}",
            f"ok={flag(data.get('ok'))}",
            f"root={data.get('root')}",
            f"rollback.label={rollback.get('label')}",
            f"rollback.manifest={rollback.get('manifest')}",
            f"generated={len(generated) if isinstance(generated, list) else 0}",
            f"copied={len(copied) if isinstance(copied, list) else 0}",
            f"root_vmparams_modified="
            f"{flag(data.get('root_vmparams_modified'))}",
        ])

    raw_intended = data.get("intended_java")
    intended = raw_intended if isinstance(raw_intended, dict) else {}
    raw_launcher = data.get("launcher")
    launcher = raw_launcher if isinstance(raw_launcher, dict) else {}
    raw_enabled = data.get("enabled_mods")
    enabled = raw_enabled if isinstance(raw_enabled, dict) else {}
    raw_warnings = data.get("warnings")
    raw_copies = data.get("copies")
    return "\n".join([
        f"route={data.get('route')}",
        f"root={data.get('root')}",
        f"intended_java.version={intended.get('java_version')}",
        f"intended_java.runtime={intended.get('java_runtime_version')}",
        f"launcher.java={launcher.get('java')}",
        f"launcher.bat={launcher.get('bat')}",
        f"launcher.argfile={launcher.get('argfile')}",
        f"vmparams={data.get('vmparams_path')}",
        f"root_vmparams_modified="
        f"{flag(data.get('root_vmparams_modified'))}",
        f"copies={len(raw_copies) if isinstance(raw_copies, list) else 0}",
        f"enabled_mods.state={enabled.get('state')}",
        f"enabled_mods.add={joined(enabled.get('add'))}",
        f"warnings={len(raw_warnings) if isinstance(raw_warnings, list) else 0}",
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
    migrate.add_argument("--text", action="store_true", help="以 key=value 输出摘要")
    route_b = sub.add_parser(
        "route-b", help="规划/执行路线 B（FR 0.9.7rc2 + Java 28，默认 dry-run）")
    route_b.add_argument("--root", required=True, type=Path)
    route_b.add_argument("--fr-dir", required=True, type=Path)
    route_b.add_argument("--jdk-dir", required=True, type=Path)
    route_b.add_argument("--hypernova-mod", required=True, type=Path)
    route_b.add_argument("--prepatcher", type=Path,
                         help="可选：StarsectorPrepatcher 目录（实验）")
    route_b.add_argument("--backups", type=Path,
                         help="快照根目录（默认为 <audit>/backups）")
    route_b.add_argument("--text", action="store_true",
                         help="以 key=value 输出摘要")
    route_b.add_argument("--json-out", "--out", dest="json_out", type=Path,
                         help="把 JSON 结果写入该文件（evidence）")
    route_b.add_argument("--apply", action="store_true",
                         help="真正写盘（默认只规划）")
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
            if args.text:
                print(_format_migrate_text(data))
            else:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        if args.command == "route-b":
            plan = plan_route_b(
                args.root,
                fr_dir=args.fr_dir,
                jdk_dir=args.jdk_dir,
                hypernova_mod=args.hypernova_mod,
                prepatcher_dir=args.prepatcher,
            )
            if args.backups is not None:
                plan["snapshot"]["dest"] = str(args.backups)  # type: ignore[index]
            if args.apply:
                plan["apply"] = True
                data = apply_route_b(plan)
            else:
                data = plan
            if args.json_out is not None:
                args.json_out.parent.mkdir(parents=True, exist_ok=True)
                args.json_out.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            if args.text:
                print(_format_route_b_text(data))
            else:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            if args.apply and not data.get("ok"):
                manifest = data.get("manifest")
                manifest = manifest if isinstance(manifest, dict) else {}
                agent = data.get("agent")
                agent = agent if isinstance(agent, dict) else {}
                rollback = data.get("rollback")
                rollback = rollback if isinstance(rollback, dict) else {}
                print(
                    "FATAL: route-b apply failed "
                    f"(manifest={manifest.get('critical') or manifest.get('error')}, "
                    f"agent_rc={agent.get('returncode')}, "
                    f"rollback_label={rollback.get('label')})",
                    file=sys.stderr,
                )
                return 1
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
