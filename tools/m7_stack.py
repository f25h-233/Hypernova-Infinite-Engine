"""M7 统一部署包：实验根盘点、256 mod 迁移与路线 B 安装。

Task 1 只读盘点；Task 2 迁移规划；Task 3 增加路线 B（FR 0.9.7rc2 +
jdk-28+13 + Hypernova，可选 Prepatcher）。所有写操作都必须显式
``--apply``，默认 dry-run；apply 前复用 ``m6_env_snapshot.snapshot``。
"""
from __future__ import annotations

import argparse
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
# Starsector 的启动档 CWD 是 starsector-core，因此 java 与 mods 都从该目录
# 相对定位；这与 Inno 安装根 vmparams 的既有写法一致。
JDK_DIR_NAME = "jdk-28+13"
JDK_JAVA_TOKEN = "..\\jdk-28+13\\bin\\java.exe"
HYPERNOVA_MOD_ID = "hypernova_infinite_engine"
HYPERNOVA_MOD_REL = Path("mods") / HYPERNOVA_MOD_ID
HYPERNOVA_AGENT_TOKEN = (
    "-javaagent:..\\mods\\hypernova_infinite_engine\\jars\\hypernova.agent.jar"
)
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


def _route_b_effective_java(jdk_dir: str | Path) -> dict[str, object]:
    """读取 ``jdk-28+13/release``，报告真正会被启动的 JVM 版本。

    ``inspect_root`` 的 ``jre_version`` 只描述随包 JRE；路线 B 用的是
    ``jdk-28+13/bin/java.exe``，两者必须分开报告。
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
    payload = _read_json(path)
    current: list[str] = []
    if isinstance(payload, dict) and isinstance(payload.get("enabledMods"), list):
        current = [item for item in payload["enabledMods"]
                   if isinstance(item, str)]
    wanted = [HYPERNOVA_MOD_ID]
    if prepatcher:
        wanted.append("starsector_prepatcher")
    lower = {item.lower() for item in current}
    return {
        "path": str(path),
        "present": path.is_file(),
        "current_count": len(current),
        "add": [item for item in wanted if item.lower() not in lower],
    }


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
    if resolved.parent.name.lower() == "install":
        backups = resolved.parent.parent / "backups"
    else:
        backups = resolved.parent / "backups"
    label = "m7-route-b-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return {
        "game_root": str(resolved),
        "dest": str(backups),
        "label": label,
        "files": list(m6_env_snapshot.SNAPSHOT_FILES),
        "extra_backup": [VMPARAMS_PATH],
    }


def _route_b_tokens(tokens: list[str], *, prepatcher: bool) -> list[str]:
    """清洗旧注入并生成路线 B 的完整参数 token 序列。"""
    out: list[str] = []
    for index, token in enumerate(tokens):
        if index == 0:
            out.append(JDK_JAVA_TOKEN)
            continue
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

    # 路线 B 通过根 vmparams 直接启动，classpath 必须包含 fr.jar。
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
    new_line = " ".join(
        _route_b_tokens(tokens, prepatcher=prepatcher_dir is not None))

    copies = _route_b_copies(base, fr_dir, jdk_dir, hypernova_mod,
                             prepatcher_dir)
    effective_java = _route_b_effective_java(jdk_dir)
    fr_version = _route_b_fr_version(fr_dir)

    warnings: list[str] = []
    for item in copies:
        if not item["exists"]:
            warnings.append(f"missing source: {item['src']}")
    agent_source = _hypernova_agent_source(hypernova_mod)
    if not agent_source.is_file():
        warnings.append(f"missing agent jar: {agent_source}")
    if fr_version is None:
        warnings.append(f"fr.version.txt not found under {fr_dir}")
    elif "0.9.7rc2" not in fr_version:
        warnings.append(f"unexpected FR version: {fr_version}")
    java_version = effective_java.get("java_version")
    if java_version is None:
        warnings.append(f"cannot read effective Java version from {jdk_dir}")
    elif str(java_version) != "28":
        warnings.append(
            f"effective Java is {java_version}, expected 28 for route B")

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

    return {
        "route": "b",
        "name": ROUTES["b"]["name"],
        "root": str(base),
        "apply": False,
        "java": JDK_JAVA_TOKEN,
        "java_target": str(base / JDK_DIR_NAME / "bin" / "java.exe"),
        "effective_java": effective_java,
        "bundled_jre_version": _jre_version(base),
        "fr_version": fr_version,
        "vmparams_path": str(vmparams),
        "vmparams": new_line,
        "vmparams_changed": new_line != original.strip(),
        "agents": agents,
        "flags": list(ROUTE_B_FLAGS),
        "copies": copies,
        "copy_count": len(copies),
        "missing_sources": [str(item["src"]) for item in copies
                            if not item["exists"]],
        "agent_jar": str(agent_source),
        "enabled_mods": _route_b_enabled_mods(
            base, prepatcher_dir is not None),
        "vram_optimizer": {
            "present": vram_present,
            "source": "256-mod migration (Task 2)",
        },
        "prepatcher": prepatcher,
        "snapshot": _route_b_snapshot_plan(base),
        "warnings": warnings,
    }


def _apply_enabled_mods(root: Path, spec: dict[str, object]) -> dict[str, object]:
    path_text = spec.get("path")
    path = Path(str(path_text)) if path_text else root / ENABLED_MODS_PATH
    payload = _read_json(path)
    ids: list[str] = []
    if isinstance(payload, dict) and isinstance(payload.get("enabledMods"), list):
        ids = [item for item in payload["enabledMods"]
               if isinstance(item, str)]
    lower = {item.lower() for item in ids}
    raw_add = spec.get("add")
    add = [str(item) for item in raw_add] if isinstance(raw_add, list) else []
    added: list[str] = []
    for mod_id in add:
        if mod_id.lower() not in lower:
            ids.append(mod_id)
            lower.add(mod_id.lower())
            added.append(mod_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps({"enabledMods": ids}, ensure_ascii=False, indent=2) + "\n",
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
    """执行路线 B 计划。默认 dry-run；只有 ``plan["apply"]`` 为真才写盘。"""
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
    if missing:
        raise FileNotFoundError(
            "missing route-b sources: " + ", ".join(missing))

    # 快照先行（M6 的 4 个文件），vmparams 不在 M6 清单里，单独留档。
    raw_snapshot = plan.get("snapshot")
    snapshot = raw_snapshot if isinstance(raw_snapshot, dict) else {}
    dest = snapshot.get("dest")
    label = snapshot.get("label")
    if not dest or not label:
        raise ValueError("route-b plan has no snapshot dest/label")
    snapshot_meta = m6_env_snapshot.snapshot(root, str(dest), str(label))
    snapshot_dir = Path(str(dest)) / str(label)
    vmparams = root / VMPARAMS_PATH
    vmparams_backup: str | None = None
    if vmparams.is_file():
        backup = snapshot_dir / "vmparams.before-route-b"
        shutil.copy2(vmparams, backup)
        vmparams_backup = str(backup)

    with vmparams.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(str(plan["vmparams"]).rstrip("\r\n") + "\n")

    copied: list[str] = []
    for item in copies:
        src = Path(str(item["src"])).resolve()
        dst = Path(str(item["dst"]))
        if item.get("kind") == "tree":
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        copied.append(str(dst))

    raw_enabled = plan.get("enabled_mods")
    enabled = _apply_enabled_mods(
        root, raw_enabled if isinstance(raw_enabled, dict) else {})
    manifest = _apply_install_manifest(root)
    agent = _apply_install_agent(root, agent_jar)
    ok = bool(manifest.get("ok")) and agent.get("returncode") == 0
    return {
        "applied": True,
        "ok": ok,
        "root": str(root),
        "snapshot": snapshot_meta,
        "vmparams_backup": vmparams_backup,
        "vmparams": plan["vmparams"],
        "copied": copied,
        "enabled_mods": enabled,
        "manifest": manifest,
        "agent": agent,
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
