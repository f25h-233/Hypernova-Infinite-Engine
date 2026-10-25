"""把 core 资产 + 标题闭包 + 全量实体池 + 元数据余量组装成 manifest。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from image_probe import probe
from l1_core import CoreAssets, core_assets_result
from mod_index import (
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


@dataclass
class BuildResult:
    manifest: dict
    warnings: list[str] = field(default_factory=list)


def _folder_path(game_root: Path, folder: str) -> Path:
    root = Path(game_root).resolve()
    if folder.casefold() == "starsector-core":
        return root / "starsector-core"
    return root / "mods" / folder


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
        meta = metadata.get(owner.folder.name, rel)
    else:
        candidates = [
            me
            for me in (metadata.by_rel.get(rel.casefold()) or [])
            if include_core or me.mod_folder.casefold() != "starsector-core"
        ]
        if len(candidates) == 1:
            meta = candidates[0]

    if owner is not None:
        absolute = owner.absolute.resolve().as_posix()
        mod_id = owner.mod_id
    elif meta is not None:
        absolute = (
            _folder_path(root, meta.mod_folder) / meta.rel
        ).resolve().as_posix()
        mod_id = "core" if meta.mod_folder.casefold() == "starsector-core" else meta.mod_folder
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
            dds = (root / meta.dds_rel).resolve().as_posix()
    elif owner is not None:
        w, h = probe(owner.absolute)
        src = "header_probe" if w and h else "spec_scan"

    owner_key = None
    if owner is not None:
        owner_key = (owner.folder.name.casefold(), rel.casefold())
    elif meta is not None:
        owner_key = (meta.mod_folder.casefold(), meta.rel.casefold())
    return _entry(mod_id, rel, absolute, dds, w, h, baked, src), owner_key


def _metadata_entry(me: MetadataEntry, game_root: Path, folder_to_id: dict[str, str]) -> dict:
    absolute = (
        _folder_path(game_root, me.mod_folder) / me.rel
    ).resolve().as_posix()
    dds = (
        (Path(game_root).resolve() / me.dds_rel).resolve().as_posix()
        if me.dds_rel
        else None
    )
    if me.mod_folder.casefold() == "starsector-core":
        mod_id = "core"
    else:
        mod_id = folder_to_id.get(me.mod_folder.casefold(), me.mod_folder)
    return _entry(
        mod_id,
        me.rel,
        absolute,
        dds,
        me.width,
        me.height,
        True,
        "dds_metadata",
    )


def build_manifest(
    game_root: Path,
    scope: str = "mod_non_shader",
    include_core: bool = True,
    include_l2: bool = True,
    variant_limit: int = 0,
) -> BuildResult:
    root = Path(game_root).resolve()
    enabled = load_enabled_ids(root)
    scan = scan_mods(root, enabled, include_core=include_core)
    lookup = build_lookup(scan.mods)
    title = read_title_variants(scan.mods)
    metadata = read_dds_metadata(root)

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

    folder_to_id = {m.folder.name.casefold(): m.mod_id for m in scan.mods}
    enabled_folders = {m.folder.name.casefold() for m in scan.mods}
    # 同人口：metadata 计数、磁盘图计数、未烘焙计数都只覆盖已启用 mod（含 core）。
    scope_meta = [
        me
        for me in metadata.entries
        if in_scope(me, scope) and me.mod_folder.casefold() in enabled_folders
    ]
    core_meta = [
        me
        for me in metadata.entries
        if me.mod_folder.casefold() == "starsector-core" and include_core
    ]
    for me in scope_meta + core_meta:
        key = (me.mod_folder.casefold(), me.rel.casefold())
        if key in seen_meta:
            continue
        seen_meta.add(key)
        add_l3(_metadata_entry(me, root, folder_to_id))

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
        (me.mod_folder.casefold(), me.rel.casefold())
        for me in scope_meta + core_meta
    }
    for asset in scope_images + core_images:
        key = (asset.folder.name.casefold(), asset.rel.casefold())
        if key in meta_keys or asset.rel.casefold() in seen_paths:
            continue
        w, h = probe(asset.absolute)
        add_l3(
            _entry(
                asset.mod_id,
                asset.rel,
                asset.absolute.resolve().as_posix(),
                None,
                w,
                h,
                False,
                "header_probe" if w and h else "spec_scan",
            )
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
        if (me.mod_folder.casefold(), me.rel.casefold()) in seen_meta
    )
    disk_images = len(scope_images)
    scope_meta_keys = {
        (me.mod_folder.casefold(), me.rel.casefold()) for me in scope_meta
    }
    unbaked = sum(
        1
        for asset in scope_images
        if (asset.folder.name.casefold(), asset.rel.casefold()) not in scope_meta_keys
    )

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
                "l1_sprite_disk": (l1_disk / len(l1)) if l1 else 1.0,
                "l1_baked": (l1_baked / len(l1)) if l1 else 1.0,
                "closure_refs": (refs_ok / refs_total) if refs_total else 1.0,
                "metadata": (
                    0.0
                    if metadata.parse_errors
                    else ((meta_seen / meta_all) if meta_all else None)
                ),
            },
            "missing": closure_stats.missing,
            "parse_errors": closure_stats.parse_errors,
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
    return BuildResult(manifest, warnings)
