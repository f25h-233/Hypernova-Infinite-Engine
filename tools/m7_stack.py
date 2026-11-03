"""M7 统一部署包：实验根盘点、256 mod 迁移与路线 A/B 安装。

Task 1 只读盘点；Task 2 迁移规划；Task 3 增加路线 B（FR 0.9.7rc2 +
jdk-28+13 + Hypernova，可选 Prepatcher）；Task 4 增加路线 A（MixinFR
1.2.5 + JRE 17 + StarsectorParallel + Hypernova，绝不混入 FR 0.9.7，
也不装 Prepatcher）。两条路线都必须由显式 ``java.exe @route-*.vmparams``
启动器启动：``starsector.exe`` 与 ``fr.bat`` 都硬编码随包 JRE 17，不能用
来跑 Java 28。所有写操作都必须显式 ``--apply``，默认 dry-run；apply 前
生成 M7 自己的回滚清单。
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
import zipfile
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
SSIME_DLL_NAME = Path(SSIME_DLL_PATH).name
SSIME_DLL_DISABLED_NAME = SSIME_DLL_NAME + ".disabled"
SSIME_DLL_DISABLED_PATH = SSIME_DLL_PATH + ".disabled"

# Task 5：IME 短路、日志收集与 MixinFR 字体开关。
CIF_MOD_ID = "ChineseInputFix"
CIF_MOD_FOLDER = "ChineseInputFix"
CIF_MOD_REL = Path("mods") / CIF_MOD_FOLDER
DEFAULT_CIF_SOURCE = (
    Path(__file__).resolve().parent.parent
    / "Starsector-098-260mods" / "mods" / CIF_MOD_FOLDER
)
LOG_NAMES = (
    "starsector.log",
    "mixinlib.log",
    "mixinfr-fonthd.log",
    "scripts-agent.log",
)
# 游戏日志在 starsector-core；agent 日志默认写在 saves/hypernova。
LOG_SEARCH_DIRS = ("starsector-core", "", "saves/hypernova", "saves")
MIXINFR_FONT_CONFIG_NAMES = (
    "mixinfr.imefix.mixin.json",
    "mixinfr.font.json",
    "fonts.json",
)
_FONT_SWITCH_KEYS = frozenset(name.lower() for name in (
    "FrFontHd",
    "frFontHd",
    "fontHd",
    "font_hd",
    "fr_font_hd",
    "hdFonts",
))

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
# 随包 JRE 17 的 vmparams 带有 Java 28 不接受的参数。路线 B 必须过滤，
# 否则 Java 28 在创建 JVM 时就退出（实测 -noverify 等）。
ROUTE_B_JAVA28_REMOVED_TOKENS = frozenset({
    "-noverify",
    "-XX:+UseXMMForArrayCopy",
    "-XX:+ParallelRefProcEnabled",
    "-XX:+AlwaysAtomicAccesses",
    "-XX:+UseVectorStubs",
    "-XX:ShenandoahGCMode=iu",
    "--enable-preview",
})
_MEMORY_VALUE_RE = re.compile(r"^\d+[kKmMgG]$")
DEFAULT_ROUTE_B_XMS = "8G"
DEFAULT_ROUTE_B_XMX = "10G"
# ---- 路线 A 常量（Task 4）----
# MixinFR 的 install.bat 从 mod 文件夹名推导 agent 路径，因此目标文件夹
# 固定为 MixinFR（不能含空格）；Parallel 同理，由我们固定命名。
JRE_DIR_NAME = "jre"
JRE_JAVA_TOKEN = "..\\jre\\bin\\java.exe"
ROUTE_A_VMPARAMS_NAME = "route-a.vmparams"
ROUTE_A_LAUNCHER_NAME = "launch-route-a.bat"
MIXINFR_MOD_FOLDER = "MixinFR"
PARALLEL_MOD_FOLDER = "StarsectorParallel"
MIXINFR_MOD_ID = "MixinLib"
PARALLEL_MOD_ID = "starsectorparallel"
MIXIN_AGENT_TOKEN = (
    "-javaagent:..\\mods\\MixinFR\\jars\\MixinLib-bridge.jar"
)
# 路线 A 与 B 共用同一组 Hypernova 惰性纹理开关；路线 A 不写 -Dmixinfr.*。
ROUTE_A_FLAGS = ROUTE_B_FLAGS
ROUTE_A_MANAGED_MOD_IDS = (HYPERNOVA_MOD_ID, MIXINFR_MOD_ID, PARALLEL_MOD_ID)
# CLI 未显式传 --hypernova-mod 时使用仓库根（build/ 产物所在处）。
DEFAULT_HYPERNOVA_MOD = Path(__file__).resolve().parent.parent
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
    route: str = "b",
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
        "route": route,
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


def _copy_entry(
    src: Path, dst: Path, kind: str = "file"
) -> dict[str, object]:
    exists = src.is_dir() if kind == "tree" else src.is_file()
    return {"src": str(src), "dst": str(dst), "kind": kind,
            "exists": exists}


def _hypernova_copies(
    root: Path, hypernova_mod: str | Path
) -> list[dict[str, object]]:
    """路线 A/B 共用的 Hypernova 复制清单（mod + 淘汰占位图）。"""
    hn = Path(hypernova_mod)
    mod_dir = root / HYPERNOVA_MOD_REL
    core = root / "starsector-core"
    copies: list[dict[str, object]] = [
        _copy_entry(hn / "mod_info.json", mod_dir / "mod_info.json"),
    ]
    packaged = (hn / "jars" / "hypernova.jar").is_file()
    if packaged:
        copies.append(_copy_entry(hn / "jars", mod_dir / "jars", "tree"))
    else:
        copies.append(_copy_entry(hn / "build" / "java" / "hypernova.jar",
                                  mod_dir / "jars" / "hypernova.jar"))
        copies.append(_copy_entry(_hypernova_agent_source(hn),
                                  mod_dir / "jars" / "hypernova.agent.jar"))
    copies.append(_copy_entry(hn / "data", mod_dir / "data", "tree"))
    copies.append(_copy_entry(hn / "graphics", mod_dir / "graphics", "tree"))
    # 淘汰占位图必须同时在 starsector-core（agent-only 安装下 mod 目录
    # 不保证被 FileLoader 扫描）；见 tools/java/install-manifest.sh。
    copies.append(_copy_entry(
        hn / "graphics" / "hypernova" / "blank.png",
        core / "graphics" / "hypernova" / "blank.png"))
    return copies


def _route_b_copies(
    root: Path,
    fr_dir: str | Path,
    jdk_dir: str | Path,
    hypernova_mod: str | Path,
    prepatcher_dir: str | Path | None,
) -> list[dict[str, object]]:
    """列出路线 B 的复制清单（只描述意图，不写盘）。"""
    copies: list[dict[str, object]] = []
    core = root / "starsector-core"
    fr = Path(fr_dir)
    if fr.is_dir():
        for item in sorted(fr.iterdir(), key=lambda path: path.name.lower()):
            if item.is_file():
                copies.append(_copy_entry(item, core / item.name))

    copies.append(_copy_entry(Path(jdk_dir), root / JDK_DIR_NAME, "tree"))
    copies.extend(_hypernova_copies(root, hypernova_mod))
    if prepatcher_dir is not None:
        copies.append(_copy_entry(Path(prepatcher_dir),
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


def _tokenless_arguments(tokens: list[str]) -> list[str]:
    """生成 token-less 参数序列：丢掉原启动档的 argv[0]。

    原 vmparams 的首 token 是给 ``starsector.exe`` 的 argv[0]，不是 JVM
    参数；直接喂给 ``java @argfile`` 会被当作主类。若输入本身已 token-less
    （首 token 以 ``-`` 开头或就是主类），原样保留，保证幂等。
    路线 A/B 共用（两者都由显式 ``java.exe @argfile`` 启动）。
    """
    args = list(tokens)
    if args and not args[0].startswith("-") and args[0] != MAIN_CLASS:
        args = args[1:]
    return args


def _normalize_memory_value(value: str, *, name: str) -> str:
    text = str(value).strip()
    if not _MEMORY_VALUE_RE.fullmatch(text):
        raise ValueError(
            f"invalid {name}: {value!r}; expected e.g. 8G, 8192m, 10240m")
    return text


def _ddscache_state(root: Path) -> dict[str, object]:
    """FR 0.9.7rc2 requires ``mods/DDSCache`` to exist before startup."""
    path = root / "mods" / "DDSCache"
    exists = path.exists()
    return {
        "path": str(path),
        "present": path.is_dir(),
        "will_create": not exists,
        "blocked": exists and not path.is_dir(),
    }


def _lunalib_settings_state(root: Path) -> dict[str, object]:
    """Detect the known LunaLib first-run corruption (all files identical).

    M7 must not write LunaSettings; this is a read-only precheck so the
    operator can restore a known-good ``saves/common/LunaSettings`` before
    launching a 256-mod install.
    """
    folder = root / "saves" / "common" / "LunaSettings"
    files = sorted(folder.glob("*.json.data")) if folder.is_dir() else []
    by_hash: dict[str, list[str]] = {}
    for path in files:
        try:
            digest = _sha256_file(path)
        except OSError:
            continue
        by_hash.setdefault(digest, []).append(path.name)
    unique = len(by_hash)
    suspicious = len(files) > 1 and unique == 1
    sample = []
    if suspicious:
        sample = sorted(by_hash, key=lambda key: -len(by_hash[key]))[:1]
        sample = [name for name in by_hash[sample[0]]][:5]
    return {
        "path": str(folder),
        "present": folder.is_dir(),
        "file_count": len(files),
        "unique_hashes": unique,
        "suspicious": suspicious,
        "sample": sample,
    }


def _route_b_tokens(tokens: list[str], *, prepatcher: bool,
                    xms: str | None = None,
                    xmx: str | None = None) -> list[str]:
    """清洗旧注入并生成路线 B 的 token-less 参数序列。"""
    out: list[str] = []
    replace_memory = xms is not None or xmx is not None
    for token in tokens:
        lowered = token.lower()
        if token in ROUTE_B_JAVA28_REMOVED_TOKENS:
            continue
        if replace_memory and (
                lowered.startswith("-xms") or lowered.startswith("-xmx")):
            continue
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

    memory: list[str] = []
    if xms is not None:
        memory.append(f"-Xms{xms}")
    if xmx is not None:
        memory.append(f"-Xmx{xmx}")
    options = memory + list(ROUTE_B_FLAGS) + [
        HYPERNOVA_AGENT_TOKEN, FR_AGENT_TOKEN]
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
    xms: str | None = None,
    xmx: str | None = None,
) -> dict[str, object]:
    """规划路线 B（FR 0.9.7rc2 + jdk-28+13 + Hypernova）。

    只读：返回新的 vmparams 行、effective Java 与复制清单。写盘必须显式
    调用 ``apply_route_b`` 并先经过 ``m6_env_snapshot.snapshot``。
    ``xms``/``xmx`` 会替换源 vmparams 的内存参数；Java 28 专属过滤见
    ``ROUTE_B_JAVA28_REMOVED_TOKENS``。
    """
    base = Path(root).resolve()
    if xms is not None:
        xms = _normalize_memory_value(xms, name="xms")
    if xmx is not None:
        xmx = _normalize_memory_value(xmx, name="xmx")
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
    args = _tokenless_arguments(tokens)
    new_line = " ".join(
        _route_b_tokens(
            args, prepatcher=prepatcher_dir is not None,
            xms=xms, xmx=xmx))
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

    ddscache = _ddscache_state(base)
    if ddscache["blocked"]:
        warnings.append(
            f"{ddscache['path']} exists but is not a directory; route B "
            "needs an empty directory here")
    elif ddscache["will_create"]:
        warnings.append(
            "mods/DDSCache missing; apply will create it (FR 0.9.7rc2 "
            "requires it before startup)")
    lunalib = _lunalib_settings_state(base)
    if lunalib["suspicious"]:
        warnings.append(
            "LunaLib settings look corrupt: "
            f"{lunalib['file_count']} file(s) share one hash under "
            f"{lunalib['path']}; restore a known-good "
            "saves/common/LunaSettings before launching")
    elif not lunalib["present"]:
        warnings.append(
            "LunaLib settings directory missing; first run may regenerate it "
            "(known issue: 256-mod first run can write identical files)")

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
    ensure_dirs: list[str] = []
    if ddscache["will_create"] and not ddscache["blocked"]:
        ensure_dirs.append(str(ddscache["path"]))
        rollback_paths.append(str(ddscache["path"]))
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
        "memory": {
            "xms": xms,
            "xmx": xmx,
            "overridden": xms is not None or xmx is not None,
            "source": ("override" if (xms is not None or xmx is not None)
                       else "inherited"),
        },
        "java28_removed_tokens": sorted(ROUTE_B_JAVA28_REMOVED_TOKENS),
        "ddscache": ddscache,
        "lunalib_settings": lunalib,
        "ensure_dirs": ensure_dirs,
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
    raw_ddscache = plan.get("ddscache")
    ddscache = raw_ddscache if isinstance(raw_ddscache, dict) else {}
    if ddscache.get("blocked"):
        raise ValueError(
            "route-b requires a directory at "
            f"{ddscache.get('path')!r} for FR DDS metadata")

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

    raw_ensure = plan.get("ensure_dirs")
    ensure_dirs = ([str(item) for item in raw_ensure]
                   if isinstance(raw_ensure, list) else [])
    for item in ensure_dirs:
        _snapshot_paths(root, [item])
        Path(item).mkdir(parents=True, exist_ok=True)

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
        "created_dirs": ensure_dirs,
        "vmparams": plan["vmparams"],
        "memory": plan.get("memory"),
        "ddscache": plan.get("ddscache"),
        "lunalib_settings": plan.get("lunalib_settings"),
        "root_vmparams_modified": False,
        "copied": copied,
        "enabled_mods": enabled,
        "manifest": manifest,
        "agent": agent,
        "launcher": plan.get("launcher"),
        "intended_java": plan.get("intended_java"),
        "effective_java": plan.get("effective_java"),
    }


# ---- 路线 A（Task 4）：MixinFR 1.2.5 + JRE 17 + StarsectorParallel ----


def _agent_basename(token: str) -> str:
    name = token.split(":", 1)[1] if ":" in token else token
    return name.replace("\\", "/").rsplit("/", 1)[-1].lower()


def _reject_route_a_inputs(root: Path, tokens: list[str]) -> None:
    """路线 A 隔离闸门：拒绝 FR 0.9.7 与 StarsectorPrepatcher。

    MixinFR 自带 FR 0.9.5；再叠加 FR 0.9.7 的 agent/fr.jar 会双重注入。
    Prepatcher 在 MixinLib 的 TargetClassLoader 下 20/34 目标被
    ``SKIPPED_LOADER``，且 Java 27+ 还会 ``FatalCompatibilityException``。
    """
    if (root / "starsector-core" / "fr.jar").is_file():
        raise ValueError("route A must not mix FR 0.9.7")
    for token in tokens:
        lowered = token.lower()
        if lowered.startswith("-javaagent:"):
            name = _agent_basename(token)
            if name in {"fr.agent.jar", "fr.jar"}:
                raise ValueError("route A must not mix FR 0.9.7")
            if name == _PREPATCHER_AGENT_NAME or "prepatcher" in name:
                raise ValueError(
                    "route A must not install StarsectorPrepatcher")
        for part in lowered.split(";"):
            if part.replace("\\", "/").rsplit("/", 1)[-1] == "fr.jar":
                raise ValueError("route A must not mix FR 0.9.7")
    mods = root / "mods"
    if mods.is_dir():
        for entry in mods.iterdir():
            if (entry.is_dir()
                    and entry.name.lower() == "starsectorprepatcher"):
                raise ValueError(
                    "route A must not install StarsectorPrepatcher")


def _route_a_tokens(tokens: list[str]) -> list[str]:
    """清洗旧注入并生成路线 A 的 token-less 参数序列。

    agent 顺序固定：``MixinLib-bridge.jar`` 先建立 Mixin 运行时，
    ``hypernova.agent.jar`` 后注入；两者都在 classpath/主类之前。
    """
    out: list[str] = []
    for token in tokens:
        lowered = token.lower()
        if lowered.startswith("-javaagent:"):
            name = _agent_basename(token)
            if (name in _HYPERNOVA_AGENT_NAMES
                    or name == "mixinlib-bridge.jar"):
                continue
        if lowered.startswith("-dhypernova."):
            continue
        out.append(token)

    if MAIN_CLASS not in out:
        raise ValueError(f"vmparams has no main class: {MAIN_CLASS}")

    insert_at = out.index(MAIN_CLASS)
    for index, token in enumerate(out):
        if token in ("-classpath", "-cp"):
            insert_at = index
            break

    options = list(ROUTE_A_FLAGS) + [MIXIN_AGENT_TOKEN, HYPERNOVA_AGENT_TOKEN]
    return out[:insert_at] + options + out[insert_at:]


def _route_a_copies(
    root: Path,
    mixinfr_dir: str | Path,
    parallel_dir: str | Path,
    hypernova_mod: str | Path,
) -> list[dict[str, object]]:
    """列出路线 A 的复制清单（只描述意图，不写盘）。"""
    copies = [
        _copy_entry(Path(mixinfr_dir),
                    root / "mods" / MIXINFR_MOD_FOLDER, "tree"),
        _copy_entry(Path(parallel_dir),
                    root / "mods" / PARALLEL_MOD_FOLDER, "tree"),
    ]
    copies.extend(_hypernova_copies(root, hypernova_mod))
    return copies


def _route_a_launcher_path(root: str | Path) -> Path:
    return _audit_root(root) / "scripts" / ROUTE_A_LAUNCHER_NAME


def _route_a_launcher_text(root: str | Path) -> str:
    scripts = _route_a_launcher_path(root).parent
    core = Path(root).resolve() / "starsector-core"
    core_rel = os.path.relpath(core, scripts.resolve()).replace("/", "\\")
    lines = [
        "@echo off",
        "setlocal",
        "rem M7 Route A: explicit JRE 17 launcher.",
        "rem starsector.exe always starts ..\\jre\\bin\\java.exe (JRE 17);",
        "rem this script carries the route A javaagents instead of vmparams.",
        f'cd /d "%~dp0{core_rel}"',
        f'"{JRE_JAVA_TOKEN}" @..\\{ROUTE_A_VMPARAMS_NAME}',
    ]
    return "\r\n".join(lines) + "\r\n"


def _route_a_managed_mods(
    root: Path,
    mixinfr_dir: str | Path,
    parallel_dir: str | Path,
    hypernova_mod: str | Path,
) -> list[dict[str, object]]:
    """按启用顺序（Hypernova → MixinLib → starsectorparallel）校验 mod id。"""
    specs = [
        (HYPERNOVA_MOD_ID, Path(hypernova_mod), root / HYPERNOVA_MOD_REL),
        (MIXINFR_MOD_ID, Path(mixinfr_dir),
         root / "mods" / MIXINFR_MOD_FOLDER),
        (PARALLEL_MOD_ID, Path(parallel_dir),
         root / "mods" / PARALLEL_MOD_FOLDER),
    ]
    managed: list[dict[str, object]] = []
    for mod_id, src, dst in specs:
        info = src / "mod_info.json"
        entry: dict[str, object] = {
            "id": mod_id,
            "src": str(src),
            "dst": str(dst),
            "mod_info": str(info),
            "verified": False,
            "source_id": None,
            "error": None,
        }
        try:
            actual = _read_mod_id(info)
        except Exception as exc:  # noqa: BLE001 - dry-run 只告警
            entry["error"] = str(exc)
        else:
            entry["source_id"] = actual
            if actual == mod_id:
                entry["verified"] = True
            else:
                entry["error"] = (
                    f"mod_info id mismatch: {actual!r}, expected {mod_id!r}")
        managed.append(entry)
    return managed


def _route_a_enabled_spec(
    root: Path, managed: list[dict[str, object]]
) -> dict[str, object]:
    path = root / ENABLED_MODS_PATH
    state = _enabled_mods_state(path)
    current = state["ids"] if state["state"] == "ok" else []
    assert isinstance(current, list)
    verified = [str(item["id"]) for item in managed if item.get("verified")]
    managed_lower = {str(item["id"]).lower() for item in managed}
    lower = {str(item).lower() for item in current}
    return {
        "path": str(path),
        "present": path.is_file(),
        "state": state["state"],
        "error": state["error"],
        "current_count": len(current),
        "add": [mod_id for mod_id in verified
                if mod_id.lower() not in lower],
        # 最终顺序：保留既有 mod 的相对顺序，再把路线 A 三个 id 依
        # Hypernova → MixinLib → starsectorparallel 追加到末尾。
        "order": [str(item) for item in current
                  if str(item).lower() not in managed_lower] + verified,
    }


def _route_a_snapshot_plan(root: Path) -> dict[str, object]:
    resolved = root.resolve()
    label = "m7-route-a-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return {
        "game_root": str(resolved),
        "dest": str(_default_backups(resolved)),
        "label": label,
        "route": "a",
        "m6_files": list(m6_env_snapshot.SNAPSHOT_FILES),
        "rollback_manifest": ROUTE_ROLLBACK_MANIFEST,
        "route_files": list(ROUTE_SNAPSHOT_PATHS),
    }


def plan_route_a(
    root: str | Path,
    *,
    mixinfr_dir: str | Path,
    parallel_dir: str | Path,
    hypernova_mod: str | Path,
) -> dict[str, object]:
    """规划路线 A（MixinFR 1.2.5 + JRE 17 + StarsectorParallel + Hypernova）。

    只读：返回 token-less argfile 行、显式 JRE 17 启动器与复制清单。写盘
    必须显式调用 ``apply_route_a`` 并先经过 M6/M7 快照。根 ``vmparams``
    不改写；``starsector-core/fr.jar`` 或 vmparams 里的 FR token 直接拒绝。
    """
    base = Path(root).resolve()
    if not base.is_dir():
        raise FileNotFoundError(f"install root not found: {base}")
    vmparams = base / VMPARAMS_PATH
    if not vmparams.is_file():
        raise FileNotFoundError(f"vmparams not found: {vmparams}")
    original = vmparams.read_text(encoding="utf-8-sig", errors="replace")
    tokens = original.split()
    if not tokens:
        raise ValueError(f"empty vmparams: {vmparams}")

    _reject_route_a_inputs(base, tokens)
    args = _tokenless_arguments(tokens)
    new_line = " ".join(_route_a_tokens(args))

    route_a_vmparams = base / ROUTE_A_VMPARAMS_NAME
    launcher_path = _route_a_launcher_path(base)
    launcher_text = _route_a_launcher_text(base)
    copies = _route_a_copies(base, mixinfr_dir, parallel_dir, hypernova_mod)
    managed = _route_a_managed_mods(
        base, mixinfr_dir, parallel_dir, hypernova_mod)

    jre_version = _jre_version(base)
    java_exe = base / JRE_DIR_NAME / "bin" / "java.exe"
    agent_source = _hypernova_agent_source(hypernova_mod)
    hypernova_json = (Path(hypernova_mod) / "data" / "config" /
                      "hypernova" / "hypernova.json")
    mixin_agent = Path(mixinfr_dir) / "jars" / "MixinLib-bridge.jar"
    mixin_fr = Path(mixinfr_dir) / "jars" / "fr.jar"
    vram_present = (base / "mods" / "VramOptimizer").is_dir()
    enabled_mods = _route_a_enabled_spec(base, managed)

    warnings: list[str] = []
    for item in copies:
        if not item["exists"]:
            warnings.append(f"missing source: {item['src']}")
    if not agent_source.is_file():
        warnings.append(f"missing agent jar: {agent_source}")
    if not hypernova_json.is_file():
        warnings.append(f"missing hypernova.json: {hypernova_json}")
    if not mixin_agent.is_file():
        warnings.append(f"missing MixinLib bridge agent: {mixin_agent}")
    if not mixin_fr.is_file():
        warnings.append(f"missing bundled MixinFR fr.jar: {mixin_fr}")
    if not java_exe.is_file():
        warnings.append(f"jre java.exe not found: {java_exe}")
    if jre_version is None:
        warnings.append(
            f"cannot read bundled JRE version from "
            f"{base / JRE_RELEASE_PATH}")
    elif not str(jre_version).startswith("17"):
        warnings.append(
            f"bundled JRE is {jre_version}, route A expects 17.x")
    for item in managed:
        if not item.get("verified"):
            warnings.append(
                f"cannot verify mod id {item['id']} from "
                f"{item['mod_info']}: {item['error']}")
    if enabled_mods["state"] == "missing":
        warnings.append(
            "enabled_mods.json missing; run the 256-mod migration (Task 2) "
            "before applying route A")
    elif enabled_mods["state"] == "error":
        warnings.append(
            "enabled_mods.json is unreadable/invalid; apply will refuse to "
            f"write it: {enabled_mods['error']}")
    if not vram_present:
        warnings.append(
            "VramOptimizer not present in target mods; apply the 256-mod "
            "migration (Task 2) before route A")
    warnings.append(
        "StarsectorPrepatcher is excluded from route A: under MixinLib's "
        "TargetClassLoader 20/34 targets are SKIPPED_LOADER and Java 27+ "
        "adds FatalCompatibilityException")
    warnings.append(
        "starsector.exe hardcodes ..\\jre\\bin\\java.exe (JRE 17); use the "
        "generated launch-route-a.bat for the explicit route A entry point")

    rollback_paths = [
        VMPARAMS_PATH,
        ROUTE_A_VMPARAMS_NAME,
        str(launcher_path),
        ENABLED_MODS_PATH,
        "starsector-core/data/config/settings.json",
        str(base / HYPERNOVA_MOD_REL),
        str(base / HYPERNOVA_MOD_REL / "data/config/hypernova/hypernova.json"),
        str(base / "mods" / MIXINFR_MOD_FOLDER),
        str(base / "mods" / PARALLEL_MOD_FOLDER),
    ]
    rollback_paths.extend(str(item["dst"]) for item in copies)

    writes = [
        {"path": str(route_a_vmparams), "kind": "file",
         "content": new_line + "\n"},
        {"path": str(launcher_path), "kind": "file",
         "content": launcher_text},
    ]

    return {
        "route": "a",
        "name": ROUTES["a"]["name"],
        "root": str(base),
        "apply": False,
        "java": JRE_JAVA_TOKEN,
        "java_target": str(java_exe),
        "jre_version": jre_version,
        "intended_java": {
            "release": str(base / JRE_RELEASE_PATH),
            "java_exe": str(java_exe),
            "java_exe_present": java_exe.is_file(),
            "java_version": jre_version,
            "launcher_java": JRE_JAVA_TOKEN,
            "target": str(java_exe),
        },
        "effective_java": {
            "verified": False,
            "java_version": None,
            "evidence": None,
            "note": "runtime JVM version is not proven; collect java -version "
                    "or -Xlog evidence in smoke before claiming JRE 17",
        },
        "launcher": {
            "kind": "explicit-java",
            "java": JRE_JAVA_TOKEN,
            "java_target": str(java_exe),
            "bat": str(launcher_path),
            "bat_content": launcher_text,
            "cwd": str(base / "starsector-core"),
            "argfile": f"..\\{ROUTE_A_VMPARAMS_NAME}",
            "argfile_path": str(route_a_vmparams),
            "command": f"{JRE_JAVA_TOKEN} @..\\{ROUTE_A_VMPARAMS_NAME}",
            "note": "starsector.exe hardcodes ..\\jre\\bin\\java.exe "
                    "(JRE 17); this explicit launcher is the route A entry "
                    "point",
        },
        "starsector_exe": {
            "java": "..\\jre\\bin\\java.exe",
            "jre_version": jre_version,
            "route_a": False,
            "note": "hardcoded lpApplicationName; fallback/control only",
        },
        "root_vmparams_path": str(vmparams),
        "root_vmparams_modified": False,
        "source_vmparams_sha256": _sha256_file(vmparams),
        "hypernova_config": str(hypernova_json),
        "vmparams_path": str(route_a_vmparams),
        "vmparams": new_line,
        "vmparams_tokenless": True,
        "agents": [MIXIN_AGENT_TOKEN, HYPERNOVA_AGENT_TOKEN],
        "flags": list(ROUTE_A_FLAGS),
        "writes": writes,
        "copies": copies,
        "copy_count": len(copies),
        "missing_sources": [str(item["src"]) for item in copies
                            if not item["exists"]],
        "agent_jar": str(agent_source),
        "mixinfr": {
            "id": MIXINFR_MOD_ID,
            "source": str(mixinfr_dir),
            "dst": str(base / "mods" / MIXINFR_MOD_FOLDER),
            "agent": MIXIN_AGENT_TOKEN,
            "agent_source": str(mixin_agent),
            "agent_present": mixin_agent.is_file(),
            "bundled_fr": str(mixin_fr),
            "bundled_fr_present": mixin_fr.is_file(),
            "bundled_fr_version": "0.9.5",
            "note": "MixinFR bundles FR 0.9.5; never add FR 0.9.7 on route A",
        },
        "parallel": {
            "id": PARALLEL_MOD_ID,
            "source": str(parallel_dir),
            "dst": str(base / "mods" / PARALLEL_MOD_FOLDER),
            "requires": MIXINFR_MOD_ID,
        },
        "enabled_mods": enabled_mods,
        "managed_mods": managed,
        "mod_ids": {
            str(item["id"]): str(item["mod_info"]) for item in managed
        },
        "vram_optimizer": {
            "present": vram_present,
            "source": "256-mod migration (Task 2)",
        },
        "prepatcher": {
            "installed": False,
            "excluded": True,
            "reason": "StarsectorPrepatcher 0.18.4 is SKIPPED_LOADER 20/34 "
                      "under MixinLib TargetClassLoader and fatal on Java 27+; "
                      "route A never installs it",
        },
        "snapshot": _route_a_snapshot_plan(base),
        "rollback_paths": rollback_paths,
        "warnings": warnings,
    }


def _apply_route_a_enabled_mods(
    root: Path,
    spec: dict[str, object],
    managed: list[dict[str, object]],
) -> dict[str, object]:
    """按 Hypernova → MixinLib → starsectorparallel 合并启用列表。

    写入前逐一校验目标 ``mod_info.json``，避免写悬空 id。
    """
    path_text = spec.get("path")
    path = Path(str(path_text)) if path_text else root / ENABLED_MODS_PATH
    state = _enabled_mods_state(path)
    if state["state"] == "error":
        raise ValueError(
            "refusing to overwrite invalid enabled_mods.json: "
            f"{state['error']}")
    verified = [item for item in managed if item.get("verified")]
    if len(verified) != len(managed):
        missing = [str(item["id"]) for item in managed
                   if not item.get("verified")]
        raise ValueError(
            "refusing to enable route A ids without verified mods: "
            + ", ".join(missing))
    for item in verified:
        info = Path(str(item["dst"])) / "mod_info.json"
        actual = _read_mod_id(info)
        if actual != item["id"]:
            raise ValueError(
                f"mod_info id mismatch after copy: {info} is {actual!r}, "
                f"expected {item['id']!r}")

    ids = list(state["ids"]) if isinstance(state["ids"], list) else []
    payload = state.get("payload")
    base_payload = dict(payload) if isinstance(payload, dict) else {}
    managed_lower = {str(item["id"]).lower() for item in verified}
    previous_lower = {item.lower() for item in ids}
    ordered = [str(item) for item in ids
               if item.lower() not in managed_lower]
    ordered.extend(str(item["id"]) for item in verified)
    added = [mod_id for mod_id in ordered
             if mod_id.lower() not in previous_lower]
    base_payload["enabledMods"] = ordered
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(base_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)
    return {"path": str(path), "added": added, "order": ordered,
            "count": len(ordered)}


def apply_route_a(plan: dict[str, object]) -> dict[str, object]:
    """执行路线 A 计划。默认 dry-run；只有 ``plan["apply"]`` 为真才写盘。

    写盘顺序：校验源与 enabled_mods → M6 快照（全局约束）+ M7 回滚快照
    → token-less argfile + 显式 JRE 17 启动器 → 复制 MixinFR/Parallel/
    Hypernova → 合并 enabled_mods → manifest。根 ``vmparams`` 不改写，
    也不调用 ``install_agent``（agent 已在本路线的 argfile 里）。
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
    java_exe = Path(str(plan.get("java_target") or
                        root / JRE_DIR_NAME / "bin" / "java.exe"))
    if not java_exe.is_file() and str(java_exe) not in missing:
        missing.append(str(java_exe))
    hypernova_config = Path(str(plan.get("hypernova_config") or ""))
    if not hypernova_config.is_file() and str(hypernova_config) not in missing:
        missing.append(str(hypernova_config))
    if missing:
        raise FileNotFoundError(
            "missing route-a sources: " + ", ".join(missing))

    expected_vm_sha = plan.get("source_vmparams_sha256")
    if expected_vm_sha:
        source_vmparams = root / VMPARAMS_PATH
        if (not source_vmparams.is_file()
                or _sha256_file(source_vmparams) != str(expected_vm_sha)):
            raise ValueError(
                "source vmparams changed after planning; replan route-a")

    raw_enabled = plan.get("enabled_mods")
    enabled_spec = raw_enabled if isinstance(raw_enabled, dict) else {}
    enabled_path = Path(str(enabled_spec.get("path") or
                            root / ENABLED_MODS_PATH))
    _snapshot_paths(root, [enabled_path])
    state = _enabled_mods_state(enabled_path)
    if state["state"] == "error":
        raise ValueError(
            "refusing to apply with invalid enabled_mods.json: "
            f"{state['error']}")

    raw_managed = plan.get("managed_mods")
    managed = ([item for item in raw_managed if isinstance(item, dict)]
               if isinstance(raw_managed, list) else [])
    if not managed:
        raise ValueError("route-a plan has no managed mods")

    raw_writes = plan.get("writes")
    writes = raw_writes if isinstance(raw_writes, list) else []
    if not writes:
        raise ValueError("route-a plan has no generated files")
    raw_rollback = plan.get("rollback_paths")
    rollback_paths = (raw_rollback if isinstance(raw_rollback, list)
                      else list(ROUTE_SNAPSHOT_PATHS))

    raw_snapshot = plan.get("snapshot")
    snapshot = raw_snapshot if isinstance(raw_snapshot, dict) else {}
    dest = snapshot.get("dest")
    label = snapshot.get("label")
    if not dest or not label:
        raise ValueError("route-a plan has no snapshot dest/label")
    dest_path = Path(str(dest))
    snapshot_meta = m6_env_snapshot.snapshot(root, str(dest_path), str(label))
    snapshot_dir = dest_path.resolve() / str(label)
    rollback_meta = snapshot_route(
        root, str(label), paths=rollback_paths, dest=dest_path, route="a")

    generated: list[str] = []
    for item in writes:
        if not isinstance(item, dict) or not item.get("path"):
            raise ValueError("invalid route-a generated file entry")
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

    enabled = _apply_route_a_enabled_mods(root, enabled_spec, managed)
    manifest = _apply_install_manifest(root)
    ok = bool(manifest.get("ok"))
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
        "launcher": plan.get("launcher"),
        "java": plan.get("java"),
        "jre_version": plan.get("jre_version"),
    }


# ---- Task 5：IME 短路、MixinFR 字体开关、回滚与日志收集 ----


def _mod_id_and_error(info_path: Path) -> tuple[str | None, str | None]:
    try:
        return _read_mod_id(info_path), None
    except Exception as exc:  # noqa: BLE001 - dry-run 只报告，不中断
        return None, str(exc)


def _cif_state(root: Path, cif_source: str | Path | None) -> dict[str, object]:
    """检查 ChineseInputFix 的目标/源目录；写 enabled 前必须 verified。"""
    target = root / CIF_MOD_REL
    source = (Path(cif_source).resolve() if cif_source is not None
              else DEFAULT_CIF_SOURCE)
    target_present = target.is_dir()
    source_present = source.is_dir()
    target_id: str | None = None
    source_id: str | None = None
    error: str | None = None
    if target_present:
        target_id, error = _mod_id_and_error(target / "mod_info.json")
        if target_id != CIF_MOD_ID:
            error = error or (
                f"mod_info id mismatch: {target_id!r}, "
                f"expected {CIF_MOD_ID!r}")
            verified = False
        else:
            verified = True
    elif source_present:
        source_id, error = _mod_id_and_error(source / "mod_info.json")
        if source_id != CIF_MOD_ID:
            error = error or (
                f"mod_info id mismatch: {source_id!r}, "
                f"expected {CIF_MOD_ID!r}")
            verified = False
        else:
            verified = True
    else:
        error = f"ChineseInputFix folder not found: {target} or {source}"
        verified = False
    return {
        "expected_id": CIF_MOD_ID,
        "target": str(target),
        "target_present": target_present,
        "source": str(source),
        "source_present": source_present,
        "target_id": target_id,
        "source_id": source_id,
        "verified": verified,
        "need_copy": not target_present,
        "error": error if not verified else None,
    }


def _enabled_cif_state(root: Path) -> dict[str, object]:
    path = root / ENABLED_MODS_PATH
    state = _enabled_mods_state(path)
    ids = state["ids"] if isinstance(state["ids"], list) else []
    lowered = {str(item).lower() for item in ids}
    return {
        "path": str(path),
        "state": state["state"],
        "error": state["error"],
        "count": len(ids),
        "has_chinese_input_fix": CIF_MOD_ID.lower() in lowered,
    }


def plan_disable_ime(
    root: str | Path,
    *,
    cif_source: str | Path | None = None,
) -> dict[str, object]:
    """规划 IME 短路：改名 ssime.dll，并确保 ChineseInputFix 已复制/启用。

    只读。``apply_disable_ime`` 才会先做 M6+M7 快照再写盘。
    """
    base = Path(root).resolve()
    if not base.is_dir():
        raise FileNotFoundError(f"install root not found: {base}")
    dll = base / SSIME_DLL_PATH
    disabled = base / SSIME_DLL_DISABLED_PATH
    dll_present = dll.is_file()
    disabled_present = disabled.is_file()
    conflict = dll_present and disabled_present
    rename = ([(SSIME_DLL_NAME, SSIME_DLL_DISABLED_NAME)]
              if dll_present and not disabled_present else [])

    cif = _cif_state(base, cif_source)
    enabled = _enabled_cif_state(base)
    verified = bool(cif["verified"])
    add = ([CIF_MOD_ID]
           if verified and not enabled["has_chinese_input_fix"] else [])

    warnings: list[str] = []
    if conflict:
        warnings.append(
            "both ssime.dll and ssime.dll.disabled exist; refusing to guess")
    elif disabled_present and not dll_present:
        warnings.append("ssime.dll is already disabled")
    elif not dll_present:
        warnings.append("ssime.dll not found; nothing to rename")
    if not verified:
        warnings.append(str(cif["error"]))
    if enabled["state"] != "ok":
        warnings.append(
            f"enabled_mods.json state is {enabled['state']}; apply will "
            "refuse to write it (run the 256-mod migration first)")
    if dll_present and verified and not add:
        warnings.append(
            "ChineseInputFix is already enabled; only the DLL rename remains")

    blocked_reasons: list[str] = []
    if conflict:
        blocked_reasons.append("ssime.dll and ssime.dll.disabled both exist")
    if not verified:
        blocked_reasons.append(str(cif["error"]))
    if enabled["state"] != "ok":
        blocked_reasons.append(
            f"enabled_mods.json state is {enabled['state']}")

    label = "m7-disable-ime-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    snapshot = {
        "dest": str(_default_backups(base)),
        "label": label,
        "paths": [
            str(base / SSIME_DLL_PATH),
            str(base / SSIME_DLL_DISABLED_PATH),
            str(base / ENABLED_MODS_PATH),
            str(base / CIF_MOD_REL),
        ],
    }
    writes: list[dict[str, object]] = []
    if rename:
        writes.append({
            "kind": "rename",
            "from": SSIME_DLL_NAME,
            "to": SSIME_DLL_DISABLED_NAME,
        })
    if cif["need_copy"] and verified:
        writes.append({
            "kind": "copy-tree",
            "src": cif["source"],
            "dst": cif["target"],
        })
    if add:
        writes.append({"kind": "enabled-mods", "add": add})

    return {
        "route": "ime",
        "root": str(base),
        "apply": False,
        "dll_present": dll_present,
        "disabled_present": disabled_present,
        "already_disabled": disabled_present and not dll_present,
        "conflict": conflict,
        "rename": rename,
        "cif": cif,
        "enabled_mods": {
            **enabled,
            "need_enable": bool(add),
            "add": add,
        },
        "writes": writes,
        "snapshot": snapshot,
        "warnings": warnings,
        "apply_blocked": bool(blocked_reasons),
        "blocked_reason": "; ".join(blocked_reasons) or None,
    }


def apply_disable_ime(plan: dict[str, object]) -> dict[str, object]:
    """执行 IME 短路。默认 dry-run；只有 ``plan["apply"]`` 为真才写盘。"""
    if not plan.get("apply"):
        return {"applied": False, "root": plan.get("root")}

    base = Path(str(plan["root"])).resolve()
    if not base.is_dir():
        raise FileNotFoundError(f"install root not found: {base}")

    raw_cif = plan.get("cif")
    cif = raw_cif if isinstance(raw_cif, dict) else {}
    source = Path(str(cif.get("source") or DEFAULT_CIF_SOURCE))
    target = base / CIF_MOD_REL
    target_present = target.is_dir()
    try:
        if target_present:
            verified = _read_mod_id(target / "mod_info.json") == CIF_MOD_ID
        elif source.is_dir():
            verified = _read_mod_id(source / "mod_info.json") == CIF_MOD_ID
        else:
            verified = False
    except Exception as exc:  # noqa: BLE001 - 统一成可读的 fail-closed 错误
        raise ValueError(
            f"cannot verify ChineseInputFix before apply: {exc}") from exc
    if not verified:
        raise FileNotFoundError(
            "ChineseInputFix is not verified; refusing to disable IME "
            f"(target={target}, source={source})")

    enabled_path = base / ENABLED_MODS_PATH
    state = _enabled_mods_state(enabled_path)
    if state["state"] != "ok":
        raise ValueError(
            "refusing to modify enabled_mods.json "
            f"(state={state['state']}, error={state['error']})")
    ids = state["ids"] if isinstance(state["ids"], list) else []
    has_cif = any(str(item).lower() == CIF_MOD_ID.lower() for item in ids)

    dll = base / SSIME_DLL_PATH
    disabled = base / SSIME_DLL_DISABLED_PATH
    do_rename = dll.is_file()
    if do_rename and disabled.exists():
        raise FileExistsError(
            f"both {dll.name} and {disabled.name} exist; refusing to guess")
    do_copy = not target_present
    do_enable = not has_cif
    if not (do_rename or do_copy or do_enable):
        return {
            "applied": True,
            "ok": True,
            "changed": False,
            "root": str(base),
            "renamed": [],
            "copied_cif": False,
            "enabled_mods": {
                "path": str(enabled_path),
                "added": [],
                "count": len(ids),
            },
            "snapshot": None,
            "rollback": None,
        }

    raw_snapshot = plan.get("snapshot")
    snapshot = raw_snapshot if isinstance(raw_snapshot, dict) else {}
    label = str(snapshot.get("label")
                or "m7-disable-ime-" + datetime.now().strftime(
                    "%Y%m%d-%H%M%S-%f"))
    dest = Path(str(snapshot.get("dest")
                    or _default_backups(base))).resolve()
    raw_paths = snapshot.get("paths")
    raw_list = ([str(item) for item in raw_paths]
                if isinstance(raw_paths, list) else [
                    str(base / SSIME_DLL_PATH),
                    str(base / SSIME_DLL_DISABLED_PATH),
                    str(base / ENABLED_MODS_PATH),
                    str(base / CIF_MOD_REL),
                ])
    paths = [str(item) for item in _snapshot_paths(base, raw_list)]

    # 快照先行：M6（全局约束）+ M7 自己的完整回滚清单。
    snapshot_meta = m6_env_snapshot.snapshot(base, str(dest), label)
    rollback_meta = snapshot_route(
        base, label, paths=paths, dest=dest, route="ime")
    _verify_rollback_targets(
        dest / label, rollback_meta,
        [Path(item) for item in paths])

    enabled_result: dict[str, object] = {
        "path": str(enabled_path),
        "added": [],
        "count": len(ids),
    }
    copied = False
    try:
        if do_copy:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)
            actual = _read_mod_id(target / "mod_info.json")
            if actual != CIF_MOD_ID:
                raise ValueError(
                    f"mod_info id mismatch after copy: {actual!r}, "
                    f"expected {CIF_MOD_ID!r}")
            copied = True
        if do_enable:
            enabled_result = _apply_enabled_mods(
                base, {"path": str(enabled_path), "add": [CIF_MOD_ID]})
        if do_rename:
            dll.rename(disabled)
    except BaseException as exc:
        try:
            rollback_route(base, label, dest=dest, apply=True)
        except Exception as rollback_exc:  # noqa: BLE001 - 保留原始异常
            add_note = getattr(exc, "add_note", None)
            if callable(add_note):
                add_note(f"automatic rollback failed: {rollback_exc}")
        raise

    return {
        "applied": True,
        "ok": True,
        "changed": True,
        "root": str(base),
        "renamed": ([{"from": SSIME_DLL_NAME,
                      "to": SSIME_DLL_DISABLED_NAME}]
                    if do_rename else []),
        "copied_cif": copied,
        "enabled_mods": enabled_result,
        "snapshot": snapshot_meta,
        "rollback": {
            "dest": str(dest),
            "label": label,
            "manifest": str(dest / label / ROUTE_ROLLBACK_MANIFEST),
            "entries": len(rollback_meta.get("entries", [])),
        },
    }


def _verify_rollback_targets(
    snap: Path, meta: dict[str, object], targets: list[Path]
) -> None:
    """写入前确认快照覆盖每个目标，且已存在目标的原始备份可用。"""
    entries = meta.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("route rollback manifest is empty; refusing to write")
    by_path: dict[Path, dict[str, object]] = {}
    for entry in entries:
        if isinstance(entry, dict):
            by_path[Path(str(entry.get("path"))).resolve()] = entry
    snap_resolved = snap.resolve()
    for target in targets:
        resolved = target.resolve()
        entry = by_path.get(resolved)
        if entry is None:
            raise ValueError(
                f"snapshot does not cover write target: {target}")
        if not resolved.exists():
            continue
        if not entry.get("existed_before"):
            raise ValueError(
                f"snapshot recorded {target} as absent; refusing to write")
        backup_rel = entry.get("backup")
        if not backup_rel:
            raise ValueError(f"snapshot has no backup for {target}")
        backup = (snap_resolved / str(backup_rel)).resolve()
        if not backup.is_relative_to(snap_resolved):
            raise ValueError(
                f"snapshot backup escapes snapshot dir: {backup}")
        kind = entry.get("kind")
        if kind == "file" and not backup.is_file():
            raise FileNotFoundError(f"snapshot backup missing: {backup}")
        if kind == "dir" and not backup.is_dir():
            raise FileNotFoundError(f"snapshot backup missing: {backup}")


def _mixinfr_version(mod_dir: Path) -> str | None:
    payload = _read_json(mod_dir / "mod_info.json")
    if not isinstance(payload, dict):
        return None
    value = payload.get("version")
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        parts = [value.get("major"), value.get("minor"), value.get("patch")]
        if all(isinstance(part, int) for part in parts):
            return ".".join(str(part) for part in parts)
    return None


def _font_switch_paths(
    data: object, prefix: tuple[str, ...] = ()
) -> list[tuple[str, ...]]:
    """在 JSON 里找显式字体开关（bool 或 {"enabled": bool}）。

    只认字典键；mixin 列表里的类名不是开关，不能当成开关改写。
    """
    found: list[tuple[str, ...]] = []
    if not isinstance(data, dict):
        return found
    for key, value in data.items():
        key_text = str(key)
        if key_text.lower() in _FONT_SWITCH_KEYS:
            if isinstance(value, bool):
                found.append(prefix + (key_text,))
            elif (isinstance(value, dict)
                  and isinstance(value.get("enabled"), bool)):
                found.append(prefix + (key_text, "enabled"))
        found.extend(_font_switch_paths(value, prefix + (key_text,)))
    return found


def _dict_value(data: object, path: tuple[str, ...]) -> object:
    node = data
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _set_dict_bool(
    data: object, path: tuple[str, ...], value: bool
) -> None:
    if not path:
        raise ValueError("empty font switch path")
    node = data
    for key in path[:-1]:
        if not isinstance(node, dict) or key not in node:
            raise ValueError(f"font switch path not found: {'.'.join(path)}")
        node = node[key]
    if not isinstance(node, dict):
        raise ValueError(f"font switch path is not an object: {'.'.join(path)}")
    node[path[-1]] = value


def _mixinfr_font_scan(
    mod_dir: Path,
) -> tuple[list[str], list[dict[str, object]], list[dict[str, object]]]:
    """扫描 MixinFR 的显式字体配置；jar 内的开关只报告，不改写。

    返回 ``(checked, switches, parse_errors)``。解析失败不能被当成
    "没有开关"，否则用户会误以为配置正常。
    """
    checked: list[str] = []
    switches: list[dict[str, object]] = []
    parse_errors: list[dict[str, object]] = []

    candidates: list[Path] = []
    for name in MIXINFR_FONT_CONFIG_NAMES:
        candidates.append(mod_dir / name)
        candidates.append(mod_dir / "config" / name)
    for path in candidates:
        if not path.is_file():
            continue
        checked.append(str(path))
        try:
            payload = load(path)
        except Exception as exc:  # noqa: BLE001 - 盘点需要报告解析错误
            parse_errors.append({"path": str(path), "error": str(exc)})
            continue
        if not isinstance(payload, dict):
            parse_errors.append({
                "path": str(path),
                "error": "top-level must be an object",
            })
            continue
        for key_path in _font_switch_paths(payload):
            switches.append({
                "path": str(path),
                "key": ".".join(key_path),
                "key_path": list(key_path),
                "enabled": bool(_dict_value(payload, key_path)),
                "editable": True,
                "payload": payload,
            })

    jar_paths = (sorted(mod_dir.glob("*.jar"))
                 + sorted((mod_dir / "jars").glob("*.jar")))
    for jar in jar_paths:
        try:
            with zipfile.ZipFile(jar) as archive:
                for name in archive.namelist():
                    lowered = name.lower()
                    if not lowered.endswith(".json"):
                        continue
                    if "font" not in lowered and "mixinfr" not in lowered:
                        continue
                    checked.append(f"{jar.name}!{name}")
                    try:
                        payload = json.loads(archive.read(name).decode(
                            "utf-8-sig", errors="replace"))
                    except Exception as exc:  # noqa: BLE001 - 报告解析错误
                        parse_errors.append({
                            "path": f"{jar.name}!{name}",
                            "error": str(exc),
                        })
                        continue
                    for key_path in _font_switch_paths(payload):
                        switches.append({
                            "path": f"{jar.name}!{name}",
                            "key": ".".join(key_path),
                            "key_path": list(key_path),
                            "enabled": bool(_dict_value(payload, key_path)),
                            "editable": False,
                            "payload": None,
                        })
        except (OSError, zipfile.BadZipFile):
            continue
    return checked, switches, parse_errors


def _font_switch_writes(
    switches: list[dict[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for item in switches:
        if not item.get("editable") or item.get("enabled") is not True:
            continue
        path = str(item["path"])
        group = grouped.setdefault(path, {"payload": item["payload"],
                                          "keys": []})
        keys = group["keys"]
        assert isinstance(keys, list)
        keys.append(tuple(item["key_path"]))  # type: ignore[arg-type]
    writes: list[dict[str, object]] = []
    for path, group in sorted(grouped.items()):
        payload = group["payload"]
        keys = group["keys"]
        assert isinstance(keys, list)
        for key_path in keys:
            _set_dict_bool(payload, key_path, False)
        writes.append({
            "path": path,
            "kind": "file",
            "content": json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            "keys": [".".join(key_path) for key_path in keys],
        })
    return writes


def plan_disable_mixinfr_fonts(root: str | Path) -> dict[str, object]:
    """规划关闭 MixinFR 的 FrFontHd 字体开关（只适用于路线 A）。

    1.2.5 没有包内字体配置文件时只报告“已含修复 / 需换 1.2.5”，
    绝不伪造开关，也不改写 vendor jar。
    """
    base = Path(root).resolve()
    if not base.is_dir():
        raise FileNotFoundError(f"install root not found: {base}")
    mod_dir = base / "mods" / MIXINFR_MOD_FOLDER
    applicable = mod_dir.is_dir()
    version = _mixinfr_version(mod_dir) if applicable else None
    checked, switches, parse_errors = (
        _mixinfr_font_scan(mod_dir) if applicable else ([], [], []))
    writes = _font_switch_writes(switches)
    switch_available = bool(switches)
    editable = any(bool(item.get("editable")) for item in switches)
    config_unreadable = bool(parse_errors)

    if not applicable:
        recommendation = (
            "MixinFR 未安装：disable-mixinfr-fonts 只适用于路线 A"
            "（mods/MixinFR）。")
    elif writes:
        recommendation = "找到显式 FrFontHd 字体开关；用 --apply 关闭。"
    elif switch_available:
        recommendation = (
            "显式 FrFontHd 字体开关已关闭或位于 jar 内不可安全改写；"
            "未生成写入。")
    elif config_unreadable:
        recommendation = (
            "MixinFR 字体配置无法解析，无法确认是否存在 FrFontHd 开关；"
            "请检查 parse_errors 或换 1.2.5。")
    elif version == "1.2.5":
        recommendation = (
            "MixinFR 1.2.5 已包含高清字体重定向修复；包内没有用户可配置的 "
            "FrFontHd 字体开关，无需关闭（若当前不是 1.2.5，需换 1.2.5；"
            "若字体异常请收集 starsector-core/mixinfr-fonthd.log）。")
    else:
        recommendation = (
            f"当前 MixinFR {version or '版本未知'} 没有用户可配置的 "
            "FrFontHd 字体开关；需换 1.2.5。")

    warnings: list[str] = []
    if not applicable:
        warnings.append(f"MixinFR mod folder not found: {mod_dir}")
    if switch_available and not editable:
        warnings.append(
            "font switch is inside a jar; M7 will not rewrite vendor jars")
    if config_unreadable:
        warnings.append(
            f"{len(parse_errors)} MixinFR font config(s) could not be parsed; "
            "cannot confirm whether an FrFontHd switch exists")
    if not switch_available and version not in (None, "1.2.5"):
        warnings.append(
            f"MixinFR {version} has no explicit font switch; upgrade to 1.2.5")

    label = "m7-disable-fonts-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    snapshot = {
        "dest": str(_default_backups(base)),
        "label": label,
        "paths": [str(item["path"]) for item in writes],
    }
    return {
        "route": "a",
        "root": str(base),
        "apply": False,
        "applicable": applicable,
        "mixinfr_dir": str(mod_dir),
        "version": version,
        "required_version": "1.2.5",
        "switch_available": switch_available,
        "editable": editable,
        "switches": [
            {key: value for key, value in item.items() if key != "payload"}
            for item in switches
        ],
        "checked": checked,
        "config_unreadable": config_unreadable,
        "parse_errors": parse_errors,
        "writes": writes,
        "recommendation": recommendation,
        "snapshot": snapshot,
        "warnings": warnings,
    }


def apply_disable_mixinfr_fonts(
    plan: dict[str, object],
) -> dict[str, object]:
    """执行字体开关关闭；无显式开关时只返回报告，不写盘。"""
    if not plan.get("apply"):
        return {"applied": False, "root": plan.get("root")}
    raw_writes = plan.get("writes")
    writes = ([item for item in raw_writes if isinstance(item, dict)]
              if isinstance(raw_writes, list) else [])
    if not writes:
        return {
            "applied": False,
            "ok": True,
            "changed": False,
            "root": plan.get("root"),
            "switch_available": bool(plan.get("switch_available")),
            "recommendation": plan.get("recommendation"),
            "written": [],
            "snapshot": None,
            "rollback": None,
        }

    base = Path(str(plan["root"])).resolve()
    if not base.is_dir():
        raise FileNotFoundError(f"install root not found: {base}")
    raw_snapshot = plan.get("snapshot")
    snapshot = raw_snapshot if isinstance(raw_snapshot, dict) else {}
    label = str(snapshot.get("label")
                or "m7-disable-fonts-" + datetime.now().strftime(
                    "%Y%m%d-%H%M%S-%f"))
    dest = Path(str(snapshot.get("dest")
                    or _default_backups(base))).resolve()
    raw_paths = [str(item["path"]) for item in writes]
    for raw in raw_paths:
        if not Path(raw).is_absolute():
            raise ValueError(
                "font plan contains a relative write path; replan with "
                f"plan_disable_mixinfr_fonts: {raw!r}")
    targets = _snapshot_paths(base, raw_paths)
    if len(targets) != len(raw_paths):
        raise ValueError("duplicate write targets in font plan")
    snapshot_meta = m6_env_snapshot.snapshot(base, str(dest), label)
    rollback_meta = snapshot_route(
        base, label, paths=[str(item) for item in targets],
        dest=dest, route="a")
    _verify_rollback_targets(dest / label, rollback_meta, targets)

    written: list[str] = []
    try:
        for item, target in zip(writes, targets):
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".tmp")
            tmp.write_text(str(item.get("content", "")), encoding="utf-8")
            os.replace(tmp, target)
            written.append(str(target))
    except BaseException as exc:
        try:
            rollback_route(base, label, dest=dest, apply=True)
        except Exception as rollback_exc:  # noqa: BLE001 - 保留原始异常
            add_note = getattr(exc, "add_note", None)
            if callable(add_note):
                add_note(f"automatic rollback failed: {rollback_exc}")
        raise

    return {
        "applied": True,
        "ok": True,
        "changed": True,
        "root": str(base),
        "switch_available": bool(plan.get("switch_available")),
        "recommendation": "已关闭显式 FrFontHd 字体开关。",
        "written": written,
        "snapshot": snapshot_meta,
        "rollback": {
            "dest": str(dest),
            "label": label,
            "manifest": str(dest / label / ROUTE_ROLLBACK_MANIFEST),
            "entries": len(rollback_meta.get("entries", [])),
        },
    }


def collect_logs(root: str | Path, out: str | Path) -> dict[str, object]:
    """把存在的启动日志复制到 evidence；只复制，不删除任何源文件。"""
    base = Path(root)
    if not base.is_dir():
        raise FileNotFoundError(f"install root not found: {base}")
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    missing: list[str] = []
    sources: dict[str, str] = {}
    for name in LOG_NAMES:
        found: Path | None = None
        for rel in LOG_SEARCH_DIRS:
            candidate = (base / rel / name) if rel else (base / name)
            if candidate.is_file():
                found = candidate
                break
        if found is None:
            missing.append(name)
            continue
        dst = out_dir / name
        if dst.resolve() != found.resolve():
            shutil.copy2(found, dst)
        copied.append(name)
        sources[name] = str(found)
    return {
        "root": str(base),
        "out": str(out_dir),
        "copied": copied,
        "missing": missing,
        "sources": sources,
    }


def _format_disable_ime_text(data: dict[str, object]) -> str:
    def flag(value: object) -> str:
        return "true" if value else "false"

    def joined(value: object) -> str:
        items = value if isinstance(value, list) else []
        return ",".join(str(item) for item in items) or "-"

    if "applied" in data:
        raw_rollback = data.get("rollback")
        rollback = raw_rollback if isinstance(raw_rollback, dict) else {}
        raw_enabled = data.get("enabled_mods")
        enabled = raw_enabled if isinstance(raw_enabled, dict) else {}
        raw_renamed = data.get("renamed")
        return "\n".join([
            f"applied={flag(data.get('applied'))}",
            f"ok={flag(data.get('ok'))}",
            f"changed={flag(data.get('changed'))}",
            f"root={data.get('root')}",
            f"renamed={len(raw_renamed) if isinstance(raw_renamed, list) else 0}",
            f"copied_cif={flag(data.get('copied_cif'))}",
            f"enabled_mods.add={joined(enabled.get('added'))}",
            f"rollback.label={rollback.get('label')}",
            f"rollback.manifest={rollback.get('manifest')}",
        ])

    raw_cif = data.get("cif")
    cif = raw_cif if isinstance(raw_cif, dict) else {}
    raw_enabled = data.get("enabled_mods")
    enabled = raw_enabled if isinstance(raw_enabled, dict) else {}
    raw_rename = data.get("rename")
    rename = ",".join(f"{item[0]}->{item[1]}"
                      for item in raw_rename
                      if isinstance(item, (list, tuple)) and len(item) == 2
                      ) if isinstance(raw_rename, list) else ""
    raw_warnings = data.get("warnings")
    return "\n".join([
        "route=ime",
        f"root={data.get('root')}",
        f"apply={flag(data.get('apply'))}",
        f"dll_present={flag(data.get('dll_present'))}",
        f"already_disabled={flag(data.get('already_disabled'))}",
        f"conflict={flag(data.get('conflict'))}",
        f"rename={rename or '-'}",
        f"cif.verified={flag(cif.get('verified'))}",
        f"cif.need_copy={flag(cif.get('need_copy'))}",
        f"enabled_mods.state={enabled.get('state')}",
        f"enabled_mods.add={joined(enabled.get('add'))}",
        f"apply_blocked={flag(data.get('apply_blocked'))}",
        f"warnings={len(raw_warnings) if isinstance(raw_warnings, list) else 0}",
    ])


def _format_fonts_text(data: dict[str, object]) -> str:
    def flag(value: object) -> str:
        return "true" if value else "false"

    if "applied" in data:
        raw_written = data.get("written")
        return "\n".join([
            f"applied={flag(data.get('applied'))}",
            f"ok={flag(data.get('ok'))}",
            f"changed={flag(data.get('changed'))}",
            f"switch_available={flag(data.get('switch_available'))}",
            f"written={len(raw_written) if isinstance(raw_written, list) else 0}",
            f"recommendation={data.get('recommendation')}",
        ])

    raw_writes = data.get("writes")
    raw_checked = data.get("checked")
    raw_errors = data.get("parse_errors")
    raw_warnings = data.get("warnings")
    return "\n".join([
        f"route=a",
        f"root={data.get('root')}",
        f"apply={flag(data.get('apply'))}",
        f"applicable={flag(data.get('applicable'))}",
        f"version={data.get('version')}",
        f"switch_available={flag(data.get('switch_available'))}",
        f"editable={flag(data.get('editable'))}",
        f"config_unreadable={flag(data.get('config_unreadable'))}",
        f"parse_errors={len(raw_errors) if isinstance(raw_errors, list) else 0}",
        f"writes={len(raw_writes) if isinstance(raw_writes, list) else 0}",
        f"checked={len(raw_checked) if isinstance(raw_checked, list) else 0}",
        f"recommendation={data.get('recommendation')}",
        f"warnings={len(raw_warnings) if isinstance(raw_warnings, list) else 0}",
    ])


def _format_rollback_text(data: dict[str, object]) -> str:
    def flag(value: object) -> str:
        return "true" if value else "false"

    raw_actions = data.get("actions")
    lines = [
        f"applied={flag(data.get('applied'))}",
        f"label={data.get('label')}",
        f"snapshot={data.get('snapshot')}",
        f"restored={data.get('restored', 0)}",
        f"deleted={data.get('deleted', 0)}",
        f"actions={len(raw_actions) if isinstance(raw_actions, list) else 0}",
    ]
    if "ok" in data:
        lines.append(f"ok={flag(data.get('ok'))}")
    return "\n".join(lines)


def _format_collect_logs_text(data: dict[str, object]) -> str:
    def joined(value: object) -> str:
        items = value if isinstance(value, list) else []
        return ",".join(str(item) for item in items) or "-"

    return "\n".join([
        f"root={data.get('root')}",
        f"out={data.get('out')}",
        f"copied={joined(data.get('copied'))}",
        f"missing={joined(data.get('missing'))}",
    ])


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
        raw_memory = data.get("memory")
        memory = raw_memory if isinstance(raw_memory, dict) else {}
        raw_ddscache = data.get("ddscache")
        ddscache = raw_ddscache if isinstance(raw_ddscache, dict) else {}
        raw_lunalib = data.get("lunalib_settings")
        lunalib = raw_lunalib if isinstance(raw_lunalib, dict) else {}
        created = data.get("created_dirs")
        return "\n".join([
            f"applied={flag(data.get('applied'))}",
            f"ok={flag(data.get('ok'))}",
            f"root={data.get('root')}",
            f"rollback.label={rollback.get('label')}",
            f"rollback.manifest={rollback.get('manifest')}",
            f"generated={len(generated) if isinstance(generated, list) else 0}",
            f"copied={len(copied) if isinstance(copied, list) else 0}",
            f"created_dirs={len(created) if isinstance(created, list) else 0}",
            f"memory.xms={memory.get('xms')}",
            f"memory.xmx={memory.get('xmx')}",
            f"ddscache.blocked={flag(ddscache.get('blocked'))}",
            f"lunalib_settings.suspicious={flag(lunalib.get('suspicious'))}",
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
    raw_memory = data.get("memory")
    memory = raw_memory if isinstance(raw_memory, dict) else {}
    raw_ddscache = data.get("ddscache")
    ddscache = raw_ddscache if isinstance(raw_ddscache, dict) else {}
    raw_lunalib = data.get("lunalib_settings")
    lunalib = raw_lunalib if isinstance(raw_lunalib, dict) else {}
    return "\n".join([
        f"route={data.get('route')}",
        f"root={data.get('root')}",
        f"intended_java.version={intended.get('java_version')}",
        f"intended_java.runtime={intended.get('java_runtime_version')}",
        f"launcher.java={launcher.get('java')}",
        f"launcher.bat={launcher.get('bat')}",
        f"launcher.argfile={launcher.get('argfile')}",
        f"vmparams={data.get('vmparams_path')}",
        f"memory.xms={memory.get('xms')}",
        f"memory.xmx={memory.get('xmx')}",
        f"memory.source={memory.get('source')}",
        f"ddscache.present={flag(ddscache.get('present'))}",
        f"ddscache.will_create={flag(ddscache.get('will_create'))}",
        f"lunalib_settings.present={flag(lunalib.get('present'))}",
        f"lunalib_settings.file_count={lunalib.get('file_count')}",
        f"lunalib_settings.unique_hashes={lunalib.get('unique_hashes')}",
        f"lunalib_settings.suspicious={flag(lunalib.get('suspicious'))}",
        f"root_vmparams_modified="
        f"{flag(data.get('root_vmparams_modified'))}",
        f"copies={len(raw_copies) if isinstance(raw_copies, list) else 0}",
        f"enabled_mods.state={enabled.get('state')}",
        f"enabled_mods.add={joined(enabled.get('add'))}",
        f"warnings={len(raw_warnings) if isinstance(raw_warnings, list) else 0}",
    ])


def _format_route_a_text(data: dict[str, object]) -> str:
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

    raw_launcher = data.get("launcher")
    launcher = raw_launcher if isinstance(raw_launcher, dict) else {}
    raw_enabled = data.get("enabled_mods")
    enabled = raw_enabled if isinstance(raw_enabled, dict) else {}
    raw_warnings = data.get("warnings")
    raw_copies = data.get("copies")
    raw_agents = data.get("agents")
    return "\n".join([
        f"route={data.get('route')}",
        f"root={data.get('root')}",
        f"java={data.get('java')}",
        f"jre_version={data.get('jre_version')}",
        f"launcher.java={launcher.get('java')}",
        f"launcher.bat={launcher.get('bat')}",
        f"launcher.argfile={launcher.get('argfile')}",
        f"vmparams={data.get('vmparams_path')}",
        f"agents={joined(raw_agents)}",
        f"root_vmparams_modified="
        f"{flag(data.get('root_vmparams_modified'))}",
        f"copies={len(raw_copies) if isinstance(raw_copies, list) else 0}",
        f"enabled_mods.state={enabled.get('state')}",
        f"enabled_mods.add={joined(enabled.get('add'))}",
        f"enabled_mods.order={joined(enabled.get('order'))}",
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
    route_a = sub.add_parser(
        "route-a",
        help="规划/执行路线 A（MixinFR + JRE 17 + Parallel，默认 dry-run）")
    route_a.add_argument("--root", required=True, type=Path)
    route_a.add_argument("--mixinfr", required=True, type=Path)
    route_a.add_argument("--parallel", required=True, type=Path)
    route_a.add_argument("--hypernova-mod", type=Path,
                         default=DEFAULT_HYPERNOVA_MOD)
    route_a.add_argument("--backups", type=Path,
                         help="快照根目录（默认为 <audit>/backups）")
    route_a.add_argument("--text", action="store_true",
                         help="以 key=value 输出摘要")
    route_a.add_argument("--json-out", "--out", dest="json_out", type=Path,
                         help="把 JSON 结果写入该文件（evidence）")
    route_a.add_argument("--apply", action="store_true",
                         help="真正写盘（默认只规划）")
    route_b = sub.add_parser(
        "route-b", help="规划/执行路线 B（FR 0.9.7rc2 + Java 28，默认 dry-run）")
    route_b.add_argument("--root", required=True, type=Path)
    route_b.add_argument("--fr-dir", required=True, type=Path)
    route_b.add_argument("--jdk-dir", required=True, type=Path)
    route_b.add_argument("--hypernova-mod", required=True, type=Path)
    route_b.add_argument("--prepatcher", type=Path,
                         help="可选：StarsectorPrepatcher 目录（实验）")
    route_b.add_argument(
        "--xms", type=str, default=None,
        help="覆盖 -Xms（如 8G/8192m；256 mod 建议 8G）")
    route_b.add_argument(
        "--xmx", type=str, default=None,
        help="覆盖 -Xmx（如 10G/10240m；256 mod 建议 8–12G）")
    route_b.add_argument("--backups", type=Path,
                         help="快照根目录（默认为 <audit>/backups）")
    route_b.add_argument("--text", action="store_true",
                         help="以 key=value 输出摘要")
    route_b.add_argument("--json-out", "--out", dest="json_out", type=Path,
                         help="把 JSON 结果写入该文件（evidence）")
    route_b.add_argument("--apply", action="store_true",
                         help="真正写盘（默认只规划）")
    disable_ime = sub.add_parser(
        "disable-ime",
        help="短路 IME：改名 ssime.dll 并启用 ChineseInputFix（默认 dry-run）")
    disable_ime.add_argument("--root", required=True, type=Path)
    disable_ime.add_argument("--cif-source", type=Path,
                             help="ChineseInputFix 源目录（默认 "
                                  "Starsector-098-260mods/mods/ChineseInputFix）")
    disable_ime.add_argument("--apply", action="store_true",
                             help="真正写盘（默认只规划）")
    disable_ime.add_argument("--text", action="store_true",
                             help="以 key=value 输出摘要")
    disable_fonts = sub.add_parser(
        "disable-mixinfr-fonts",
        help="关闭 MixinFR FrFontHd 字体开关（仅路线 A，默认 dry-run）")
    disable_fonts.add_argument("--root", required=True, type=Path)
    disable_fonts.add_argument("--apply", action="store_true",
                               help="真正写盘（默认只规划）")
    disable_fonts.add_argument("--text", action="store_true",
                               help="以 key=value 输出摘要")
    rollback = sub.add_parser(
        "rollback", help="按 M7 route-rollback.json 恢复（默认 dry-run）")
    rollback.add_argument("--root", required=True, type=Path)
    rollback.add_argument("--label", required=True)
    rollback.add_argument("--backups", type=Path,
                          help="快照根目录（默认为 <audit>/backups）")
    rollback.add_argument("--apply", action="store_true",
                          help="真正恢复（默认只展示动作）")
    rollback.add_argument("--text", action="store_true",
                          help="以 key=value 输出摘要")
    collect = sub.add_parser(
        "collect-logs", help="把启动日志复制到 evidence")
    collect.add_argument("--root", required=True, type=Path)
    collect.add_argument("--out", required=True, type=Path)
    collect.add_argument("--text", action="store_true",
                         help="以 key=value 输出摘要")
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
        if args.command == "route-a":
            plan = plan_route_a(
                args.root,
                mixinfr_dir=args.mixinfr,
                parallel_dir=args.parallel,
                hypernova_mod=args.hypernova_mod,
            )
            if args.backups is not None:
                plan["snapshot"]["dest"] = str(args.backups)  # type: ignore[index]
            if args.apply:
                plan["apply"] = True
                data = apply_route_a(plan)
            else:
                data = plan
            if args.json_out is not None:
                args.json_out.parent.mkdir(parents=True, exist_ok=True)
                args.json_out.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            if args.text:
                print(_format_route_a_text(data))
            else:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            if args.apply and not data.get("ok"):
                manifest = data.get("manifest")
                manifest = manifest if isinstance(manifest, dict) else {}
                rollback = data.get("rollback")
                rollback = rollback if isinstance(rollback, dict) else {}
                print(
                    "FATAL: route-a apply failed "
                    f"(manifest={manifest.get('critical') or manifest.get('error')}, "
                    f"rollback_label={rollback.get('label')})",
                    file=sys.stderr,
                )
                return 1
            return 0
        if args.command == "route-b":
            plan = plan_route_b(
                args.root,
                fr_dir=args.fr_dir,
                jdk_dir=args.jdk_dir,
                hypernova_mod=args.hypernova_mod,
                prepatcher_dir=args.prepatcher,
                xms=args.xms,
                xmx=args.xmx,
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
        if args.command == "disable-ime":
            plan = plan_disable_ime(args.root, cif_source=args.cif_source)
            if args.apply:
                plan["apply"] = True
                data = apply_disable_ime(plan)
            else:
                data = plan
            if args.text:
                print(_format_disable_ime_text(data))
            else:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        if args.command == "disable-mixinfr-fonts":
            plan = plan_disable_mixinfr_fonts(args.root)
            if args.apply:
                plan["apply"] = True
                data = apply_disable_mixinfr_fonts(plan)
            else:
                data = plan
            if args.text:
                print(_format_fonts_text(data))
            else:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        if args.command == "rollback":
            data = rollback_route(
                args.root, args.label, dest=args.backups, apply=args.apply)
            if args.text:
                print(_format_rollback_text(data))
            else:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        if args.command == "collect-logs":
            data = collect_logs(args.root, args.out)
            if args.text:
                print(_format_collect_logs_text(data))
            else:
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
