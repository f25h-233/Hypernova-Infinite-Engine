"""从标题 variant 集合展开出全部 sprite 路径（递归 modules/wings/skins）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from hn_json import load
from mod_index import (
    AssetRef,
    ModRef,
    build_id_index,
    build_image_index,
    pick,
    read_wing_map,
)

WEAPON_SPRITE_FIELDS = (
    "turretSprite",
    "hardpointSprite",
    "turretGlowSprite",
    "hardpointGlowSprite",
    "turretGunSprite",
    "hardpointGunSprite",
    "turretUnderSprite",
    "hardpointUnderSprite",
)


@dataclass(frozen=True)
class SpriteRef:
    rel: str
    owner: AssetRef | None


@dataclass
class ClosureStats:
    variants_total: int = 0
    variants_resolved: int = 0
    hulls_total: int = 0
    hulls_resolved: int = 0
    weapons_total: int = 0
    weapons_resolved: int = 0
    wings_total: int = 0
    wings_resolved: int = 0
    missing: dict[str, list[str]] = field(default_factory=dict)
    parse_errors: dict[str, list[str]] = field(default_factory=dict)

    def miss(self, kind: str, name: str) -> None:
        self.missing.setdefault(kind, []).append(name)

    def parse_fail(self, kind: str, name: str) -> None:
        self.parse_errors.setdefault(kind, []).append(name)


@dataclass
class ClosureResult:
    sprites: dict[str, SpriteRef] = field(default_factory=dict)
    stats: ClosureStats = field(default_factory=ClosureStats)


@dataclass
class AssetLookup:
    variants: dict[str, list[AssetRef]]
    ships: dict[str, list[AssetRef]]
    skins: dict[str, list[AssetRef]]
    weapons: dict[str, list[AssetRef]]
    images: dict[str, list[AssetRef]]
    wings: dict[str, str]
    skin_errors: dict[str, str] = field(default_factory=dict)


def _build_skin_index(
    mods: list[ModRef],
) -> tuple[dict[str, list[AssetRef]], dict[str, str]]:
    out: dict[str, list[AssetRef]] = {}
    errors: dict[str, str] = {}
    for mod in mods:
        base = mod.folder / "data" / "hulls"
        if not base.is_dir():
            continue
        import os

        for dirpath, _dirnames, filenames in os.walk(base):
            for fn in filenames:
                if Path(fn).suffix.casefold() != ".skin":
                    continue
                absolute = Path(dirpath) / fn
                try:
                    data = load(absolute)
                    if not isinstance(data, dict):
                        raise ValueError("skin is not an object")
                    sid = str(data.get("skinHullId") or Path(fn).stem)
                except Exception as exc:
                    errors[str(absolute)] = f"{fn}: {exc}"
                    continue
                rel = absolute.relative_to(mod.folder).as_posix()
                for key in {sid, Path(fn).stem}:
                    out.setdefault(key, []).append(
                        AssetRef(mod.mod_id, mod.folder, absolute, rel, mod.order)
                    )
    return out, errors


def build_lookup(mods: list[ModRef]) -> AssetLookup:
    skins, skin_errors = _build_skin_index(mods)
    return AssetLookup(
        variants=build_id_index(mods, "variants", frozenset({".variant"}), "variantId"),
        ships=build_id_index(mods, "hulls", frozenset({".ship"}), "hullId"),
        skins=skins,
        weapons=build_id_index(
            mods, "weapons", frozenset({".wpn"}), "id", ("shipsystems/wpn",)
        ),
        images=build_image_index(mods),
        wings=read_wing_map(mods),
        skin_errors=skin_errors,
    )


def _norm_path(value) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    rel = value.replace("\\", "/").lstrip("/")
    while "//" in rel:
        rel = rel.replace("//", "/")
    return rel


class _Walker:
    def __init__(self, lookup: AssetLookup):
        self.lookup = lookup
        self.result = ClosureResult()
        self._variants: set[str] = set()
        self._hulls: set[str] = set()
        self._weapons: set[str] = set()
        self._wings: set[str] = set()

    def add_sprite(self, value) -> None:
        rel = _norm_path(value)
        if not rel:
            return
        key = rel.casefold()
        if key in self.result.sprites:
            return
        owner = pick(self.lookup.images.get(key) or [])
        self.result.sprites[key] = SpriteRef(rel, owner)
        if owner is None:
            self.result.stats.miss("sprite", rel)

    def add_weapon(self, wid) -> None:
        if not isinstance(wid, str) or not wid:
            return
        if wid in self._weapons:
            return
        self._weapons.add(wid)
        self.result.stats.weapons_total += 1
        asset = pick(self.lookup.weapons.get(wid) or [])
        if asset is None:
            self.result.stats.miss("weapon", wid)
            return
        self.result.stats.weapons_resolved += 1
        try:
            data = load(asset.absolute)
        except Exception:
            self.result.stats.parse_fail("weapon", wid)
            return
        for name in WEAPON_SPRITE_FIELDS:
            self.add_sprite(data.get(name))

    def add_hull(self, hid) -> None:
        if not isinstance(hid, str) or not hid:
            return
        if hid in self._hulls:
            return
        self._hulls.add(hid)
        self.result.stats.hulls_total += 1
        skin = pick(self.lookup.skins.get(hid) or [])
        ship = pick(self.lookup.ships.get(hid) or [])
        if skin is None and ship is None:
            self.result.stats.miss("hull", hid)
            return
        self.result.stats.hulls_resolved += 1
        skin_data = {}
        if skin is not None:
            try:
                skin_data = load(skin.absolute)
            except Exception:
                self.result.stats.parse_fail("skin", hid)
            else:
                self.add_sprite(skin_data.get("spriteName"))
                self._builtins(skin_data)
                base_id = skin_data.get("baseHullId")
                if isinstance(base_id, str):
                    base = pick(self.lookup.ships.get(base_id) or [])
                    if base is not None:
                        try:
                            base_data = load(base.absolute)
                        except Exception:
                            base_data = {}
                        if not skin_data.get("spriteName"):
                            self.add_sprite(base_data.get("spriteName"))
                        self._builtins(base_data)
        if ship is not None:
            try:
                ship_data = load(ship.absolute)
            except Exception:
                self.result.stats.parse_fail("hull", hid)
                return
            self.add_sprite(ship_data.get("spriteName"))
            self._builtins(ship_data)
            if str(ship_data.get("hullSize") or "").upper() == "FIGHTER":
                self._wings.add(hid)

    def _builtins(self, data: dict) -> None:
        weapons = data.get("builtInWeapons") or {}
        if isinstance(weapons, dict):
            for wid in weapons.values():
                self.add_weapon(wid)
        elif isinstance(weapons, list):
            for wid in weapons:
                self.add_weapon(wid)
        wings = data.get("builtInWings") or []
        if isinstance(wings, list):
            for wing in wings:
                self.add_wing(wing)

    def add_wing(self, wing_id) -> None:
        if not isinstance(wing_id, str) or not wing_id:
            return
        if wing_id in self._wings:
            return
        self._wings.add(wing_id)
        self.result.stats.wings_total += 1
        variant_id = self.lookup.wings.get(wing_id)
        if variant_id:
            self.result.stats.wings_resolved += 1
            self.add_variant(variant_id)
            return
        # 少数 mod 直接把 wing 写成 hull id
        if wing_id in self.lookup.ships or wing_id in self.lookup.skins:
            self.result.stats.wings_resolved += 1
            self.add_hull(wing_id)
            return
        self.result.stats.miss("wing", wing_id)

    def add_variant(self, vid) -> None:
        if not isinstance(vid, str) or not vid:
            return
        if vid in self._variants:
            return
        self._variants.add(vid)
        self.result.stats.variants_total += 1
        asset = pick(self.lookup.variants.get(vid) or [])
        if asset is None:
            self.result.stats.miss("variant", vid)
            return
        try:
            data = load(asset.absolute)
        except Exception:
            self.result.stats.parse_fail("variant", vid)
            return
        self.result.stats.variants_resolved += 1
        self.add_hull(data.get("hullId"))
        for group in data.get("weaponGroups") or []:
            if isinstance(group, dict):
                for wid in (group.get("weapons") or {}).values():
                    self.add_weapon(wid)
        modules = data.get("modules") or []
        if isinstance(modules, dict):
            modules = [modules]
        for module in modules:
            if isinstance(module, dict):
                for ref in module.values():
                    self.add_variant(ref)
        for wing in data.get("wings") or []:
            self.add_wing(wing)


def build_closure(variant_ids: list[str], lookup: AssetLookup) -> ClosureResult:
    walker = _Walker(lookup)
    for vid in variant_ids:
        walker.add_variant(vid)
    if lookup.skin_errors:
        walker.result.stats.parse_errors.setdefault("skin", []).extend(
            sorted(lookup.skin_errors)
        )
    for key in ("missing", "parse_errors"):
        bucket = getattr(walker.result.stats, key)
        for names in bucket.values():
            names.sort()
    return walker.result
