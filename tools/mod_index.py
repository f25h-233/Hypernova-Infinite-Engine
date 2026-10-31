"""模组扫描、资产索引、标题 CSV、wing 表、DDS metadata。"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from hn_json import load

SHADER_LIBS = frozenset({"graphicslib", "shaderlib"})
CORE_FOLDER = "starsector-core"
CORE_MOD_ID = "core"
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})


def normalize_mod_id(value: str) -> str:
    """DDSCache 给 core 写的 ModID 是 starsector-core；清单/运行时统一用 core。"""
    text = str(value or "")
    return CORE_MOD_ID if text.casefold() == CORE_FOLDER else text


@dataclass(frozen=True)
class ModRef:
    mod_id: str
    folder: Path
    order: int
    is_core: bool = False


@dataclass(frozen=True)
class AssetRef:
    mod_id: str
    folder: Path
    absolute: Path
    rel: str
    order: int


@dataclass
class ModScan:
    mods: list[ModRef] = field(default_factory=list)
    missing_ids: list[str] = field(default_factory=list)
    duplicate_ids: dict[str, list[str]] = field(default_factory=dict)
    parse_errors: dict[str, str] = field(default_factory=dict)


@dataclass
class TitleVariants:
    ids: list[str] = field(default_factory=list)
    sources: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class MetadataEntry:
    mod_folder: str
    rel: str
    dds_rel: str
    width: int
    height: int
    mod_id: str = ""


@dataclass
class MetadataIndex:
    entries: list[MetadataEntry] = field(default_factory=list)
    by_key: dict[tuple[str, str], MetadataEntry] = field(default_factory=dict)
    by_rel: dict[str, list[MetadataEntry]] = field(default_factory=dict)
    by_modid_rel: dict[tuple[str, str], list[MetadataEntry]] = field(default_factory=dict)
    fallback_hits: int = 0
    parse_errors: dict[str, str] = field(default_factory=dict)

    def get(
        self, mod_folder: str, rel: str, exclude_core: bool = False
    ) -> MetadataEntry | None:
        key = (mod_folder.casefold(), rel.casefold())
        hit = self.by_key.get(key)
        if hit is not None:
            if exclude_core and hit.mod_folder.casefold() == CORE_FOLDER:
                return None
            return hit
        candidates = [
            me
            for me in (self.by_rel.get(rel.casefold()) or [])
            if not (exclude_core and me.mod_folder.casefold() == CORE_FOLDER)
        ]
        if len(candidates) == 1:
            self.fallback_hits += 1
            return candidates[0]
        return None

    def resolve(self, mod_id: str, mod_folder: str, rel: str,
                exclude_core: bool = False) -> MetadataEntry | None:
        """按稳定身份 (ModID, 相对路径) 解析；文件夹名只作回退。

        顺序：当前文件夹精确命中 → (ModID, 路径) 唯一命中 → 旧版唯一路径回退。
        文件夹改名后 metadata 的 ModFolderName 仍是旧名，但 ModID 不变，
        第二步能把条目重新绑到当前 mod。
        """
        key = (mod_folder.casefold(), rel.casefold())
        hit = self.by_key.get(key)
        if hit is not None:
            if exclude_core and hit.mod_folder.casefold() == CORE_FOLDER:
                return None
            return hit
        candidates = [
            me
            for me in (self.by_modid_rel.get(
                (normalize_mod_id(mod_id).casefold(), rel.casefold())
            ) or [])
            if not (exclude_core and me.mod_folder.casefold() == CORE_FOLDER)
        ]
        if len(candidates) == 1:
            return candidates[0]
        return self.get(mod_folder, rel, exclude_core=exclude_core)


def _norm_rel(rel: str) -> str:
    out = rel.replace("\\", "/").lstrip("/")
    while "//" in out:
        out = out.replace("//", "/")
    return out


def load_enabled_ids(game_root: Path) -> list[str]:
    data = load(game_root / "mods" / "enabled_mods.json")
    ids = data.get("enabledMods") if isinstance(data, dict) else None
    if not isinstance(ids, list):
        raise ValueError("enabled_mods.json has no enabledMods list")
    return [str(x) for x in ids]


def scan_mods(game_root: Path, enabled_ids: list[str], include_core: bool = True) -> ModScan:
    mods_dir = game_root / "mods"
    by_id: dict[str, list[Path]] = {}
    parse_errors: dict[str, str] = {}
    with os.scandir(mods_dir) as it:
        entries = sorted(it, key=lambda e: e.name)
    for entry in entries:
        if not entry.is_dir() or entry.name == "DDSCache":
            continue
        info = Path(entry.path) / "mod_info.json"
        if not info.is_file():
            continue
        try:
            data = load(info)
            mid = data.get("id")
        except Exception as exc:
            parse_errors[entry.name] = str(exc)
            continue
        if mid:
            by_id.setdefault(str(mid), []).append(Path(entry.path))
    duplicate_ids = {
        mid: sorted(p.name for p in paths) for mid, paths in by_id.items() if len(paths) > 1
    }
    scan = ModScan(duplicate_ids=duplicate_ids, parse_errors=parse_errors)
    for order, mid in enumerate(enabled_ids):
        folders = by_id.get(mid)
        if not folders:
            scan.missing_ids.append(mid)
            continue
        scan.mods.append(ModRef(mid, sorted(folders)[0], order))
    if include_core:
        core = game_root / CORE_FOLDER
        if core.is_dir():
            scan.mods.append(ModRef("core", core, len(enabled_ids), True))
    return scan


def iter_assets(mod: ModRef, subdir: str, suffixes: frozenset[str]) -> Iterator[AssetRef]:
    base = mod.folder / "data" / subdir
    if not base.is_dir():
        return
    for dirpath, _dirnames, filenames in os.walk(base):
        for fn in filenames:
            if Path(fn).suffix.casefold() not in suffixes:
                continue
            absolute = Path(dirpath) / fn
            rel = absolute.relative_to(mod.folder).as_posix()
            yield AssetRef(mod.mod_id, mod.folder, absolute, rel, mod.order)


def build_index(
    mods: list[ModRef],
    subdir: str,
    suffixes: frozenset[str],
    key: Callable[[AssetRef], str] | None = None,
) -> dict[str, list[AssetRef]]:
    index: dict[str, list[AssetRef]] = {}
    for mod in mods:
        for asset in iter_assets(mod, subdir, suffixes):
            k = key(asset) if key else Path(asset.rel).stem
            index.setdefault(k, []).append(asset)
    return index


def build_id_index(
    mods: list[ModRef],
    subdir: str,
    suffixes: frozenset[str],
    id_field: str,
    extra_subdirs: tuple[str, ...] = (),
) -> dict[str, list[AssetRef]]:
    """按文件名 stem 与内部 id 双键索引；内部 id 不符时仍可按文件名命中。"""
    index: dict[str, list[AssetRef]] = {}
    for current in (subdir, *extra_subdirs):
        for mod in mods:
            for asset in iter_assets(mod, current, suffixes):
                try:
                    data = load(asset.absolute)
                except Exception:
                    data = {}
                keys = {Path(asset.rel).stem}
                internal = data.get(id_field) if isinstance(data, dict) else None
                if isinstance(internal, str) and internal.strip():
                    keys.add(internal.strip())
                for key in keys:
                    index.setdefault(key, []).append(asset)
    return index


def build_image_index(mods: list[ModRef]) -> dict[str, list[AssetRef]]:
    index: dict[str, list[AssetRef]] = {}
    for mod in mods:
        for dirpath, _dirnames, filenames in os.walk(mod.folder):
            for fn in filenames:
                if Path(fn).suffix.casefold() not in IMAGE_SUFFIXES:
                    continue
                absolute = Path(dirpath) / fn
                rel = absolute.relative_to(mod.folder).as_posix()
                index.setdefault(rel.casefold(), []).append(
                    AssetRef(mod.mod_id, mod.folder, absolute, rel, mod.order)
                )
    return index


def pick(candidates: list[AssetRef]) -> AssetRef | None:
    if not candidates:
        return None
    return min(candidates, key=lambda a: (a.order, a.absolute.as_posix().casefold()))


def read_title_variants(mods: list[ModRef]) -> TitleVariants:
    tv = TitleVariants()
    for mod in mods:
        path = mod.folder / "data" / "config" / "title_screen_variants.csv"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            value = line.split(",", 1)[0].strip().strip('"').strip()
            if not value or value.casefold().startswith("variant"):
                continue
            if value not in tv.sources:
                tv.ids.append(value)
                tv.sources[value] = []
            tv.sources[value].append(mod.mod_id)
    return tv


def read_wing_map(mods: list[ModRef]) -> dict[str, str]:
    wings: dict[str, str] = {}
    for mod in mods:
        path = mod.folder / "data" / "hulls" / "wing_data.csv"
        if not path.is_file():
            continue
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
            for row in csv.reader(fh):
                if len(row) < 2:
                    continue
                wid = row[0].strip().strip('"')
                vid = row[1].strip().strip('"')
                if not wid or wid.startswith("#") or wid.casefold() == "id" or not vid:
                    continue
                wings.setdefault(wid, vid)
    return wings


def read_dds_metadata(game_root: Path) -> MetadataIndex:
    index = MetadataIndex()
    cache = game_root / "mods" / "DDSCache"
    if not cache.is_dir():
        return index
    with os.scandir(cache) as it:
        entries = sorted(it, key=lambda e: e.name)
    for entry in entries:
        if not entry.is_dir():
            continue
        path = Path(entry.path) / "dds_metadata.json"
        if not path.is_file():
            continue
        try:
            records = load(path)
        except Exception as exc:
            index.parse_errors[entry.name] = f"{path.name}: {exc}"
            continue
        if not isinstance(records, list):
            index.parse_errors[entry.name] = f"{path.name}: top-level is not a list"
            continue
        for lineno, record in enumerate(records, 1):
            try:
                if not isinstance(record, dict):
                    raise ValueError("record is not an object")
                mod_folder = str(record.get("ModFolderName") or entry.name)
                rel = _norm_rel(str(record.get("RelativeImagePath") or ""))
                if not rel:
                    raise ValueError("empty RelativeImagePath")
                dds_rel = _norm_rel(str(record.get("DDSFilePath") or ""))
                mod_id = normalize_mod_id(str(record.get("ModID") or mod_folder))
                me = MetadataEntry(
                    mod_folder,
                    rel,
                    dds_rel,
                    int(record.get("Width") or 0),
                    int(record.get("Height") or 0),
                    mod_id,
                )
            except Exception as exc:
                index.parse_errors[entry.name] = f"{path.name} record {lineno}: {exc}"
                continue
            index.entries.append(me)
            index.by_key[(mod_folder.casefold(), rel.casefold())] = me
            index.by_rel.setdefault(rel.casefold(), []).append(me)
            index.by_modid_rel.setdefault(
                (me.mod_id.casefold(), rel.casefold()), []
            ).append(me)
    return index


def in_scope(me: MetadataEntry, scope: str) -> bool:
    folder = me.mod_folder.casefold()
    if scope == "all_mod_metadata":
        return folder != CORE_FOLDER
    if scope == "mod_non_shader":
        return folder != CORE_FOLDER and folder not in SHADER_LIBS
    raise ValueError(f"unknown scope: {scope}")


def folder_in_scope(folder_name: str, scope: str) -> bool:
    folder = folder_name.casefold()
    if scope == "all_mod_metadata":
        return folder != CORE_FOLDER
    if scope == "mod_non_shader":
        return folder != CORE_FOLDER and folder not in SHADER_LIBS
    raise ValueError(f"unknown scope: {scope}")
