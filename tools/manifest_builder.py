"""把 core 资产 + 标题闭包 + 全量实体池 + 元数据余量组装成 manifest。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from image_probe import probe
from l1_core import CoreAssets, core_assets_result
from mod_index import (
    CORE_FOLDER,
    MetadataEntry,
    MetadataIndex,
    ModScan,
    folder_in_scope,
    in_scope,
    load_enabled_ids,
    pick,
    read_dds_metadata,
    read_title_variants,
    scan_mods,
)
from sprite_closure import AssetLookup, build_closure, build_lookup

SCHEMA = 1
LAYERS = ("L1", "L2", "L3")


@dataclass
class BuildResult:
    manifest: dict
    warnings: list[str] = field(default_factory=list)


def _folder_path(game_root: Path, folder: str) -> Path:
    root = Path(game_root).resolve()
    if folder.casefold() == CORE_FOLDER:
        return root / CORE_FOLDER
    return root / "mods" / folder


def _lexical_abs(path: Path | str) -> Path:
    """Absolute path without following junctions/symlinks.

    Windows junction-based installs (e.g. ``--link``) are supported.
    ``Path.resolve()`` would follow a junction into the source install and put
    a path outside the experimental game root into ``absolutePath``, which then
    fails manifest validation.
    """
    return Path(os.path.abspath(os.fspath(path)))


@dataclass(frozen=True)
class _ResolvedMetadata:
    mod_id: str
    rel: str
    absolute: Path
    dds: Path | None


def _safe_rel(value: str) -> str | None:
    """Normalize a cache-record path; reject anything that can escape the root."""
    rel = str(value or "").replace("\\", "/").strip()
    if not rel or rel.startswith("/") or (len(rel) >= 2 and rel[1] == ":"):
        return None
    parts = [part for part in rel.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return None
    return "/".join(parts)


class _MetadataResolver:
    """把 DDSCache 记录落到磁盘上真实存在的文件。

    DDSCache 是持久缓存，会跨 mod 更新/改名保留下来：``ModFolderName`` 可能
    指向已经不存在的旧目录，而同一个 ModID 现在在另一个目录里（玩家装了两份
    同 id 的汉化/原版时尤其常见）。这里只把缓存记录当线索，最终以磁盘为准；
    找不到原图的记录由调用方按失效缓存跳过，而不是让整份清单失败。
    """

    def __init__(
        self,
        root: Path,
        scan: ModScan,
        enabled_ids: set[str],
        enabled_folders: set[str],
        folder_by_modid: dict[str, str],
        folder_to_id: dict[str, str],
    ) -> None:
        self.root = Path(root)
        self.enabled_ids = enabled_ids
        self.enabled_folders = enabled_folders
        self.folder_by_modid = folder_by_modid
        self.folder_to_id = folder_to_id
        self._by_id: dict[str, list[Path]] = {}
        for mod_id, folders in scan.folders_by_id.items():
            key = mod_id.casefold()
            picked = folder_by_modid.get(key)
            ordered = sorted(
                folders,
                key=lambda p: (
                    p.name.casefold() != (picked or "").casefold(),
                    p.name.casefold(),
                ),
            )
            self._by_id.setdefault(key, []).extend(ordered)

    def candidates(self, me: MetadataEntry) -> list[tuple[str, Path]]:
        out: list[tuple[str, Path]] = []
        seen: set[str] = set()

        def add(mod_id: str, folder: Path) -> None:
            key = _lexical_abs(folder).as_posix().casefold()
            if key in seen or not folder.is_dir():
                return
            seen.add(key)
            out.append((mod_id, folder))

        if me.mod_folder.casefold() == CORE_FOLDER:
            add("core", self.root / CORE_FOLDER)
            return out
        # 记录里的目录名本身仍是启用目录时优先（ModID 缺失/写错的缓存容错）。
        if me.mod_folder.casefold() in self.enabled_folders:
            mod_id = self.folder_to_id.get(
                me.mod_folder.casefold(), me.mod_id or me.mod_folder
            )
            add(mod_id, _folder_path(self.root, me.mod_folder))
        # 同一 ModID 的所有当前目录；扫描时选中的目录排最前，其余按名字排序。
        if me.mod_id.casefold() in self.enabled_ids:
            for folder in self._by_id.get(me.mod_id.casefold(), []):
                add(me.mod_id, folder)
        # ModID 被 normalize 成 core 的缓存记录。
        if me.mod_id.casefold() == "core":
            add("core", self.root / CORE_FOLDER)
        return out

    def resolve(self, me: MetadataEntry) -> _ResolvedMetadata | None:
        rel = _safe_rel(me.rel)
        if rel is None:
            return None
        for mod_id, folder in self.candidates(me):
            absolute = folder / rel
            if absolute.is_file():
                return _ResolvedMetadata(
                    mod_id, rel, _lexical_abs(absolute), self._dds(me)
                )
        return None

    def _dds(self, me: MetadataEntry) -> Path | None:
        rel = _safe_rel(me.dds_rel)
        if rel is None:
            return None
        path = _lexical_abs(self.root / rel)
        return path if path.is_file() else None


def load_tier_overrides(path: Path) -> dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    mods = data.get("mods") if isinstance(data, dict) else None
    if not isinstance(mods, dict):
        raise ValueError('tiers file must be {"mods": {"<modId>": "L1|L2|L3"}}')
    return {str(k): str(v).upper() for k, v in mods.items()}


def apply_tier_overrides(layers: dict[str, list[dict]], overrides: dict[str, str],
                         known_ids: set[str]) -> tuple[dict[str, list[dict]], list[str]]:
    """把指定 mod 的全部条目移到目标层；未知 mod 只报告、不移动。"""
    if not overrides:
        return {name: list(layers.get(name, [])) for name in LAYERS}, []
    forced: dict[str, str] = {}
    unknown: list[str] = []
    for raw_key, raw_layer in overrides.items():
        key = str(raw_key).casefold()
        layer = str(raw_layer).upper()
        if layer not in LAYERS:
            raise ValueError(f"unknown tier {raw_layer!r} for mod {raw_key!r}")
        if key not in known_ids:
            unknown.append(str(raw_key))
            continue
        forced[key] = layer
    out: dict[str, list[dict]] = {name: [] for name in LAYERS}
    seen: dict[str, set[tuple[str, str]]] = {name: set() for name in LAYERS}
    for name in LAYERS:
        for entry in layers.get(name, []):
            target = forced.get(str(entry.get("modId", "")).casefold(), name)
            key = (
                str(entry.get("modId", "")).casefold(),
                str(entry.get("path", "")).casefold(),
            )
            if key in seen[target]:
                continue
            seen[target].add(key)
            out[target].append(entry)
    return out, unknown


def build_mods_summary(scan, layers: dict[str, list[dict]],
                       tier_map: dict[str, str]) -> list[dict]:
    """每个 mod 的分层条目数；包含零纹理 mod，保证 validator 能守恒校验。"""
    agg: dict[str, dict] = {}
    for name in LAYERS:
        for entry in layers.get(name, []):
            mid = str(entry.get("modId", "unknown"))
            rec = agg.setdefault(mid.casefold(), {
                "modId": mid,
                "folder": "",
                "order": -1,
                "baked": 0,
                "unbaked": 0,
                "layers": {layer: 0 for layer in LAYERS},
            })
            rec["layers"][name] += 1
            if entry.get("baked"):
                rec["baked"] += 1
            else:
                rec["unbaked"] += 1
    for mod in scan.mods:
        mid = "core" if mod.is_core else mod.mod_id
        rec = agg.setdefault(mid.casefold(), {
            "modId": mid,
            "folder": "",
            "order": -1,
            "baked": 0,
            "unbaked": 0,
            "layers": {layer: 0 for layer in LAYERS},
        })
        rec["folder"] = CORE_FOLDER if mod.is_core else mod.folder.name
        rec["order"] = mod.order
    out = []
    for key, rec in agg.items():
        rec["tier"] = tier_map.get(key, "auto")
        out.append(rec)
    out.sort(key=lambda r: (
        r["order"] if r["order"] >= 0 else 10 ** 9,
        r["modId"].casefold(),
    ))
    return out


def _entry(
    mod_id: str,
    path: str,
    absolute: str,
    dds: str | None,
    w: int,
    h: int,
    baked: bool,
    src: str,
) -> dict:
    return {
        "modId": mod_id,
        "path": path,
        "absolutePath": absolute,
        "ddsPath": dds,
        "w": int(w),
        "h": int(h),
        "baked": bool(baked),
        "src": src,
    }


def _sprite_entry(
    rel: str,
    lookup: AssetLookup,
    metadata: MetadataIndex,
    resolver: _MetadataResolver,
    include_core: bool = True,
) -> tuple[dict | None, set[tuple[str, str]]]:
    """解析一条 sprite 引用；磁盘上找不到原图时返回 None（调用方跳过并记账）。"""
    owner = pick(lookup.images.get(rel.casefold()) or [])
    meta: MetadataEntry | None = None
    resolved: _ResolvedMetadata | None = None
    if owner is not None:
        meta = metadata.resolve(
            owner.mod_id, owner.folder.name, rel, exclude_core=not include_core
        )
        if meta is not None:
            resolved = resolver.resolve(meta)
    else:
        candidates = [
            me
            for me in (metadata.by_rel.get(rel.casefold()) or [])
            if include_core
            or (
                me.mod_folder.casefold() != CORE_FOLDER
                and me.mod_id.casefold() != "core"
            )
        ]
        # 没有索引 owner 时（重复 ModID、目录改名）逐条按磁盘验证，只认真的存在的。
        for me in candidates:
            resolved = resolver.resolve(me)
            if resolved is not None:
                meta = me
                break

    keys: set[tuple[str, str]] = set()
    if owner is not None:
        absolute = _lexical_abs(owner.absolute)
        mod_id = owner.mod_id
        if (
            resolved is not None
            and meta is not None
            and meta.width > 0
            and meta.height > 0
        ):
            w, h = meta.width, meta.height
        else:
            w, h = probe(absolute)
        keys.add((owner.mod_id.casefold(), rel.casefold()))
    elif resolved is not None and meta is not None:
        absolute = resolved.absolute
        mod_id = resolved.mod_id
        w, h = meta.width, meta.height
        if w <= 0 or h <= 0:
            w, h = probe(absolute)
    else:
        return None, keys

    if meta is not None and resolved is not None:
        keys.add((resolved.mod_id.casefold(), meta.rel.casefold()))
    baked = resolved is not None and resolved.dds is not None
    dds = resolved.dds.as_posix() if baked and resolved is not None else None
    src = "dds_metadata" if meta is not None else (
        "header_probe" if w and h else "spec_scan"
    )
    return (
        _entry(mod_id, rel, absolute.as_posix(), dds, w, h, baked, src),
        keys,
    )


def _metadata_entry(me: MetadataEntry, resolved: _ResolvedMetadata) -> dict:
    w, h = me.width, me.height
    if w <= 0 or h <= 0:
        w, h = probe(resolved.absolute)
    baked = resolved.dds is not None
    src = "dds_metadata" if (me.width > 0 and me.height > 0) else (
        "header_probe" if w and h else "spec_scan"
    )
    return _entry(
        resolved.mod_id,
        resolved.rel,
        resolved.absolute.as_posix(),
        resolved.dds.as_posix() if baked and resolved.dds is not None else None,
        w,
        h,
        baked,
        src,
    )


def build_manifest(
    game_root: Path,
    scope: str = "mod_non_shader",
    include_core: bool = True,
    include_l2: bool = True,
    variant_limit: int = 0,
    tier_overrides: dict[str, str] | None = None,
    progress=None,
) -> BuildResult:
    """progress: 可选回调，签名 (str) -> None，用于给玩家侧显示进度。"""

    def note(msg: str) -> None:
        if progress is not None:
            progress(msg)

    root = Path(game_root).resolve()
    note("扫描 mod 目录")
    enabled = load_enabled_ids(root)
    scan = scan_mods(root, enabled, include_core=include_core)
    if enabled is None:
        # 没有启用列表：按扫到的全部 mod 往下走，别在这里崩。
        enabled = [m.mod_id for m in scan.mods if not m.is_core]
        note("没找到启用列表，按 mods 目录里全部 mod 生成")
    note(f"读取舰船/武器定义（{len(scan.mods)} 个 mod）")
    lookup = build_lookup(scan.mods)
    title = read_title_variants(scan.mods)
    metadata = read_dds_metadata(root)

    enabled_ids = {str(i).casefold() for i in enabled}
    enabled_folders = {m.folder.name.casefold() for m in scan.mods if not m.is_core}
    folder_by_modid = {
        m.mod_id.casefold(): m.folder.name for m in scan.mods if not m.is_core
    }
    folder_to_id = {m.folder.name.casefold(): m.mod_id for m in scan.mods}
    known_ids = {
        ("core" if m.is_core else m.mod_id).casefold() for m in scan.mods
    }
    resolver = _MetadataResolver(
        root, scan, enabled_ids, enabled_folders, folder_by_modid, folder_to_id
    )

    l1: list[dict] = []
    seen_paths: set[str] = set()
    seen_meta: set[tuple[str, str]] = set()
    unresolved_refs: list[str] = []

    def add_sprite(rel: str) -> None:
        key = rel.casefold()
        if key in seen_paths:
            return
        seen_paths.add(key)
        entry, meta_keys = _sprite_entry(
            rel, lookup, metadata, resolver, include_core=include_core
        )
        if entry is None:
            unresolved_refs.append(rel)
            return
        l1.append(entry)
        seen_meta.update(meta_keys)

    core: CoreAssets = core_assets_result(root) if include_core else CoreAssets()
    for rel in core.paths:
        add_sprite(rel)

    title_closure = build_closure(title.ids, lookup)
    for ref in title_closure.sprites.values():
        add_sprite(ref.rel)

    l2: list[dict] = []
    if include_l2:
        variants = sorted(lookup.variants)
        if variant_limit and variant_limit > 0:
            variants = variants[:variant_limit]
        pool = build_closure(variants, lookup)
        for ref in pool.sprites.values():
            key = ref.rel.casefold()
            if key in seen_paths:
                continue
            seen_paths.add(key)
            entry, meta_keys = _sprite_entry(
                ref.rel, lookup, metadata, resolver, include_core=include_core
            )
            if entry is None:
                unresolved_refs.append(ref.rel)
                continue
            l2.append(entry)
            seen_meta.update(meta_keys)

    l3: list[dict] = []
    l3_keys: set[tuple[str, str]] = set()

    def add_l3(entry: dict) -> None:
        key = (str(entry["modId"]).casefold(), str(entry["path"]).casefold())
        if key in l3_keys:
            return
        l3_keys.add(key)
        l3.append(entry)

    # 同人口：metadata 计数、磁盘图计数、未烘焙计数都只覆盖已启用 mod（含 core）。
    scope_meta = [
        me
        for me in metadata.entries
        if in_scope(me, scope)
        and (
            me.mod_id.casefold() in enabled_ids
            or me.mod_folder.casefold() in enabled_folders
        )
    ]
    core_meta = [
        me
        for me in metadata.entries
        if me.mod_folder.casefold() == CORE_FOLDER and include_core
    ]
    # 缓存记录先落到磁盘：原图不存在的按失效缓存跳过；DDS 缺失的退化为未烘焙。
    resolved_scope: list[tuple[MetadataEntry, _ResolvedMetadata]] = []
    stale_meta: list[str] = []
    for me in scope_meta:
        resolved = resolver.resolve(me)
        if resolved is None:
            stale_meta.append(f"{me.mod_id}/{me.rel}")
            continue
        resolved_scope.append((me, resolved))
    resolved_core: list[tuple[MetadataEntry, _ResolvedMetadata]] = []
    for me in core_meta:
        resolved = resolver.resolve(me)
        if resolved is None:
            stale_meta.append(f"{me.mod_id}/{me.rel}")
            continue
        resolved_core.append((me, resolved))
    live_meta = resolved_scope + resolved_core
    stale_meta.sort()

    for me, resolved in live_meta:
        key = (resolved.mod_id.casefold(), me.rel.casefold())
        if key in seen_meta:
            continue
        seen_meta.add(key)
        add_l3(_metadata_entry(me, resolved))

    scope_images = []
    core_images = []
    for assets in lookup.images.values():
        for asset in assets:
            if asset.mod_id == "core":
                if include_core:
                    core_images.append(asset)
            elif folder_in_scope(asset.folder.name, scope):
                scope_images.append(asset)
    meta_keys = {
        (resolved.mod_id.casefold(), me.rel.casefold())
        for me, resolved in live_meta
    }
    all_images = scope_images + core_images
    probe_total = len(all_images)
    note(f"解析贴图头（{probe_total} 张）")
    for probe_index, asset in enumerate(all_images):
        if progress is not None and probe_index and probe_index % 2000 == 0:
            progress(f"解析贴图头 {probe_index}/{probe_total}")
        key = (asset.mod_id.casefold(), asset.rel.casefold())
        if key in meta_keys or asset.rel.casefold() in seen_paths:
            continue
        w, h = probe(asset.absolute)
        add_l3(
            _entry(
                asset.mod_id,
                asset.rel,
                _lexical_abs(asset.absolute).as_posix(),
                None,
                w,
                h,
                False,
                "header_probe" if w and h else "spec_scan",
            )
        )

    tiers_normalized = {
        str(k).casefold(): str(v).upper() for k, v in (tier_overrides or {}).items()
    }
    layers, tiers_unknown = apply_tier_overrides(
        {"L1": l1, "L2": l2, "L3": l3}, tier_overrides or {}, known_ids
    )
    l1, l2, l3 = layers["L1"], layers["L2"], layers["L3"]

    path_conflicts: list[dict] = []
    path_records: dict[str, dict] = {}
    for layer_name, entries in (("L1", l1), ("L2", l2), ("L3", l3)):
        for e in entries:
            key = str(e["path"]).casefold()
            rec = path_records.setdefault(
                key, {"path": e["path"], "layers": [], "sizes": []}
            )
            if layer_name not in rec["layers"]:
                rec["layers"].append(layer_name)
            size = f"{e['w']}x{e['h']}"
            if size not in rec["sizes"]:
                rec["sizes"].append(size)
    for rec in path_records.values():
        if len(rec["layers"]) > 1:
            path_conflicts.append(
                {**rec, "content_differs": len(rec["sizes"]) > 1}
            )

    l1_disk = sum(
        1 for e in l1 if e["absolutePath"] and Path(e["absolutePath"]).is_file()
    )
    l1_baked = sum(1 for e in l1 if e["baked"])
    refs_total = sum(
        getattr(title_closure.stats, name)
        for name in (
            "variants_total",
            "hulls_total",
            "weapons_total",
            "wings_total",
        )
    )
    refs_ok = sum(
        getattr(title_closure.stats, name)
        for name in (
            "variants_resolved",
            "hulls_resolved",
            "weapons_resolved",
            "wings_resolved",
        )
    )
    live_scope_meta = [me for me, _ in resolved_scope]
    meta_total = len(live_scope_meta)
    meta_all = len(live_meta)
    layer_paths = {
        str(entry["path"]).casefold()
        for entries in (l1, l2, l3)
        for entry in entries
    }
    # 同人口只在「活的」缓存记录里算：失效记录不是漏生成，不该压低覆盖率。
    meta_seen = sum(
        1 for me, _ in live_meta if me.rel.casefold() in layer_paths
    )
    disk_images = len(scope_images)
    scope_meta_keys = {
        (resolved.mod_id.casefold(), me.rel.casefold())
        for me, resolved in resolved_scope
    }
    unbaked = sum(
        1
        for asset in scope_images
        if (asset.mod_id.casefold(), asset.rel.casefold()) not in scope_meta_keys
    )

    baked_paths = {
        str(entry["path"]).casefold()
        for entries in (l1, l2, l3)
        for entry in entries
        if entry.get("baked")
        and entry.get("ddsPath")
        and Path(str(entry["ddsPath"])).is_file()
    }
    expected = [
        (me, resolved) for me, resolved in live_meta if resolved.dds is not None
    ]
    baked_expected = len(expected)
    baked_resolved = 0
    unresolved: list[str] = []
    for me, _resolved in expected:
        if me.rel.casefold() in baked_paths:
            baked_resolved += 1
        else:
            unresolved.append(f"{me.mod_id}/{me.rel}")
    unresolved.sort()
    dds_missing = sorted(
        f"{me.mod_id}/{me.rel}"
        for me, resolved in live_meta
        if resolved.dds is None
    )
    refs_unique = sorted(set(unresolved_refs))
    meta_scope_all = len(scope_meta) + len(core_meta)

    closure_stats = title_closure.stats
    manifest = {
        "schema": SCHEMA,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "baseline": {
            "game": "0.98a-RC8",
            "fr": None,
            "enabled_mods": len(enabled),
        },
        "scope": scope,
        "include_core": include_core,
        "layers": {"L1": l1, "L2": l2, "L3": l3},
        "mods": build_mods_summary(
            scan, {"L1": l1, "L2": l2, "L3": l3}, tiers_normalized
        ),
        "stats": {
            "scope": scope,
            "include_core": include_core,
            "metadata_entries": meta_total,
            "metadata_entries_scope": meta_total,
            "metadata_entries_core": len(resolved_core),
            "metadata_entries_all": len(metadata.entries),
            "metadata_unused": len(metadata.entries) - meta_scope_all,
            "baked": sum(
                1 for _me, resolved in resolved_scope if resolved.dds is not None
            ),
            "unbaked": unbaked,
            "disk_images": disk_images,
            "core_entries": len(resolved_core),
            "l1_count": len(l1),
            "l2_count": len(l2),
            "l3_count": len(l3),
            "closure": {
                "variants": [closure_stats.variants_total, closure_stats.variants_resolved],
                "hulls": [closure_stats.hulls_total, closure_stats.hulls_resolved],
                "weapons": [closure_stats.weapons_total, closure_stats.weapons_resolved],
                "wings": [closure_stats.wings_total, closure_stats.wings_resolved],
            },
            "coverage": {
                "l1_sprite_disk": (l1_disk / len(l1)) if l1 else 0.0,
                "l1_baked": (l1_baked / len(l1)) if l1 else 1.0,
                "closure_refs": (refs_ok / refs_total) if refs_total else 1.0,
                "metadata": (
                    0.0
                    if metadata.parse_errors
                    else ((meta_seen / meta_all) if meta_all else None)
                ),
                "baked_expected": baked_expected,
                "baked_resolved": baked_resolved,
                "baked": (baked_resolved / baked_expected) if baked_expected else 1.0,
            },
            "unresolved_baked": unresolved[:100],
            "unresolved_baked_count": len(unresolved),
            "stale_metadata": stale_meta[:100],
            "stale_metadata_count": len(stale_meta),
            "dds_missing": dds_missing[:100],
            "dds_missing_count": len(dds_missing),
            "unresolved_refs": refs_unique[:100],
            "unresolved_refs_count": len(refs_unique),
            "tiers": {
                key: layer for key, layer in tiers_normalized.items()
                if key in known_ids
            },
            "tiers_unknown": tiers_unknown,
            "missing": closure_stats.missing,
            "parse_errors": closure_stats.parse_errors,
            "path_conflicts": path_conflicts,
            "conflicts": {
                "duplicate_mod_ids": scan.duplicate_ids,
                "mod_parse_errors": scan.parse_errors,
                "missing_mod_ids": scan.missing_ids,
            },
            "metadata_fallback_hits": metadata.fallback_hits,
            "metadata_parse_errors": metadata.parse_errors,
            "core_parse_errors": core.parse_errors,
            "core_parse_errors_skipped": not include_core,
            "source_mode": "disk_scan" if meta_all == 0 else "dds_metadata",
            "precedence": "enabled_order_then_core",
        },
    }
    warnings = []
    if scan.enabled_list_missing:
        warnings.append(
            "没有找到 enabled_mods.json，已按 mods 目录下全部 mod 生成"
            "（清单会偏大；如果你只想算启用的那些，先在启动器里保存一次 mod 选择）"
        )
    if scan.missing_ids:
        warnings.append(f"missing mods: {scan.missing_ids}")
    if scan.duplicate_ids:
        warnings.append(f"duplicate mod ids: {scan.duplicate_ids}")
    if tiers_unknown:
        warnings.append(f"unknown tier mods: {tiers_unknown}")
    if stale_meta:
        warnings.append(
            f"stale DDSCache entries skipped ({len(stale_meta)}): "
            + ", ".join(stale_meta[:5])
        )
    if dds_missing:
        warnings.append(
            f"DDSCache entries without DDS included as unbaked ({len(dds_missing)}): "
            + ", ".join(dds_missing[:5])
        )
    if refs_unique:
        warnings.append(
            f"unresolved sprite refs skipped ({len(refs_unique)}): "
            + ", ".join(refs_unique[:5])
        )
    return BuildResult(manifest, warnings)
