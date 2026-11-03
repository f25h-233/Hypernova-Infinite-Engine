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

    M7 migrates mods with junctions. ``Path.resolve()`` would follow a
    junction into the source install and put a path outside the experimental
    game root into ``absolutePath``, which then fails manifest validation.
    """
    return Path(os.path.abspath(os.fspath(path)))


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
    game_root: Path,
    include_core: bool = True,
) -> tuple[dict, tuple[str, str] | None]:
    root = Path(game_root).resolve()
    owner = pick(lookup.images.get(rel.casefold()) or [])
    meta: MetadataEntry | None = None
    if owner is not None:
        meta = metadata.resolve(
            owner.mod_id, owner.folder.name, rel, exclude_core=not include_core
        )
    else:
        candidates = [
            me
            for me in (metadata.by_rel.get(rel.casefold()) or [])
            if include_core or me.mod_folder.casefold() != CORE_FOLDER
        ]
        if len(candidates) == 1:
            meta = candidates[0]

    if owner is not None:
        absolute = _lexical_abs(owner.absolute).as_posix()
        mod_id = owner.mod_id
    elif meta is not None:
        absolute = _lexical_abs(
            _folder_path(root, meta.mod_folder) / meta.rel).as_posix()
        mod_id = "core" if meta.mod_folder.casefold() == CORE_FOLDER else meta.mod_folder
    else:
        absolute = ""
        mod_id = "unknown"

    dds = None
    w = h = 0
    baked = False
    src = "spec_scan"
    if meta is not None:
        baked = True
        src = "dds_metadata"
        w, h = meta.width, meta.height
        if meta.dds_rel:
            dds = _lexical_abs(root / meta.dds_rel).as_posix()
    elif owner is not None:
        w, h = probe(owner.absolute)
        src = "header_probe" if w and h else "spec_scan"

    owner_key = None
    if owner is not None:
        owner_key = (owner.mod_id.casefold(), rel.casefold())
    elif meta is not None:
        owner_key = (meta.mod_id.casefold(), meta.rel.casefold())
    return _entry(mod_id, rel, absolute, dds, w, h, baked, src), owner_key


def _metadata_entry(me: MetadataEntry, game_root: Path,
                    folder_to_id: dict[str, str],
                    folder_by_modid: dict[str, str],
                    current_folders: set[str]) -> dict:
    is_core = me.mod_folder.casefold() == CORE_FOLDER
    if is_core:
        folder = CORE_FOLDER
    elif me.mod_folder.casefold() in current_folders:
        folder = me.mod_folder
    else:
        folder = folder_by_modid.get(me.mod_id.casefold(), me.mod_folder)
    absolute = _lexical_abs(
        _folder_path(game_root, folder) / me.rel).as_posix()
    dds = (
        _lexical_abs(Path(game_root).resolve() / me.dds_rel).as_posix()
        if me.dds_rel
        else None
    )
    if is_core:
        mod_id = "core"
    else:
        mod_id = folder_to_id.get(folder.casefold()) or me.mod_id or folder
    return _entry(
        mod_id, me.rel, absolute, dds, me.width, me.height, True, "dds_metadata"
    )


def build_manifest(
    game_root: Path,
    scope: str = "mod_non_shader",
    include_core: bool = True,
    include_l2: bool = True,
    variant_limit: int = 0,
    tier_overrides: dict[str, str] | None = None,
) -> BuildResult:
    root = Path(game_root).resolve()
    enabled = load_enabled_ids(root)
    scan = scan_mods(root, enabled, include_core=include_core)
    lookup = build_lookup(scan.mods)
    title = read_title_variants(scan.mods)
    metadata = read_dds_metadata(root)

    enabled_ids = {str(i).casefold() for i in enabled}
    enabled_folders = {m.folder.name.casefold() for m in scan.mods if not m.is_core}
    current_folders = set(enabled_folders)
    folder_by_modid = {
        m.mod_id.casefold(): m.folder.name for m in scan.mods if not m.is_core
    }
    folder_to_id = {m.folder.name.casefold(): m.mod_id for m in scan.mods}
    known_ids = {
        ("core" if m.is_core else m.mod_id).casefold() for m in scan.mods
    }

    l1: list[dict] = []
    seen_paths: set[str] = set()
    seen_meta: set[tuple[str, str]] = set()

    def add_sprite(rel: str) -> None:
        key = rel.casefold()
        if key in seen_paths:
            return
        seen_paths.add(key)
        entry, owner_key = _sprite_entry(
            rel, lookup, metadata, root, include_core=include_core
        )
        l1.append(entry)
        if owner_key:
            seen_meta.add(owner_key)

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
            entry, owner_key = _sprite_entry(
                ref.rel, lookup, metadata, root, include_core=include_core
            )
            l2.append(entry)
            if owner_key:
                seen_meta.add(owner_key)

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
    for me in scope_meta + core_meta:
        key = (me.mod_id.casefold(), me.rel.casefold())
        if key in seen_meta:
            continue
        seen_meta.add(key)
        add_l3(
            _metadata_entry(
                me, root, folder_to_id, folder_by_modid, current_folders
            )
        )

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
        (me.mod_id.casefold(), me.rel.casefold())
        for me in scope_meta + core_meta
    }
    for asset in scope_images + core_images:
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
    meta_total = len(scope_meta)
    meta_all = len(scope_meta) + len(core_meta)
    meta_seen = sum(
        1
        for me in scope_meta + core_meta
        if (me.mod_id.casefold(), me.rel.casefold()) in seen_meta
    )
    disk_images = len(scope_images)
    scope_meta_keys = {
        (me.mod_id.casefold(), me.rel.casefold()) for me in scope_meta
    }
    unbaked = sum(
        1
        for asset in scope_images
        if (asset.mod_id.casefold(), asset.rel.casefold()) not in scope_meta_keys
    )

    by_meta_key: dict[tuple[str, str], dict] = {}
    for entries in (l1, l2, l3):
        for entry in entries:
            by_meta_key[
                (str(entry["modId"]).casefold(), str(entry["path"]).casefold())
            ] = entry
    baked_expected = len(scope_meta) + len(core_meta)
    baked_resolved = 0
    unresolved: list[str] = []
    for me in scope_meta + core_meta:
        entry = by_meta_key.get((me.mod_id.casefold(), me.rel.casefold()))
        absolute_ok = (
            entry is not None
            and bool(entry.get("absolutePath"))
            and Path(str(entry["absolutePath"])).is_file()
        )
        dds_ok = (
            entry is not None
            and bool(entry.get("ddsPath"))
            and Path(str(entry["ddsPath"])).is_file()
        )
        if absolute_ok and dds_ok:
            baked_resolved += 1
        else:
            unresolved.append(f"{me.mod_id}/{me.rel}")
    unresolved.sort()

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
            "metadata_entries_core": len(core_meta),
            "metadata_entries_all": len(metadata.entries),
            "metadata_unused": len(metadata.entries) - meta_all,
            "baked": meta_total,
            "unbaked": unbaked,
            "disk_images": disk_images,
            "core_entries": len(core_meta),
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
    if scan.missing_ids:
        warnings.append(f"missing mods: {scan.missing_ids}")
    if scan.duplicate_ids:
        warnings.append(f"duplicate mod ids: {scan.duplicate_ids}")
    if tiers_unknown:
        warnings.append(f"unknown tier mods: {tiers_unknown}")
    return BuildResult(manifest, warnings)
