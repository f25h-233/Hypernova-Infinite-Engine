from mod_index import load_enabled_ids, scan_mods
from sprite_closure import build_closure, build_lookup


def _lookup(mini_game):
    scan = scan_mods(mini_game, load_enabled_ids(mini_game))
    return build_lookup(scan.mods)


def test_closure_follows_hull_weapons_module_and_wing(mini_game):
    result = build_closure(["va_one"], _lookup(mini_game))
    assert set(result.sprites) == {
        "graphics/ships/h_alpha.png",
        "graphics/weapons/w_gun_t.png",
        "graphics/weapons/w_gun_h.png",
        "graphics/weapons/w_builtin.png",
        "graphics/ships/h_module.png",
        "graphics/ships/h_fighter.png",
    }
    assert result.stats.variants_resolved == 3  # va_one + va_module + wing variant
    assert result.stats.hulls_resolved == 3
    assert result.stats.weapons_resolved == 2
    assert result.stats.wings_resolved == 1


def test_skin_uses_own_sprite_and_base_builtins(mini_game):
    result = build_closure(["va_two"], _lookup(mini_game))
    assert "graphics/ships/h_skin.png" in result.sprites
    assert "graphics/ships/h_base.png" not in result.sprites
    assert "graphics/weapons/w_builtin.png" in result.sprites


def test_missing_variant_is_recorded_not_raised(mini_game):
    result = build_closure(["va_missing"], _lookup(mini_game))
    assert result.sprites == {}
    assert result.stats.missing["variant"] == ["va_missing"]


def test_sprite_owner_prefers_mod_a(mini_game):
    result = build_closure(["va_one"], _lookup(mini_game))
    assert result.sprites["graphics/ships/h_alpha.png"].owner.mod_id == "mod_a"


def test_missing_hull_and_weapon_are_categorized(mini_game):
    from conftest import _write
    _write(
        mini_game / "mods" / "mod_a" / "data" / "variants" / "va_bad.variant",
        '{"variantId": "va_bad", "hullId": "h_nope", '
        '"weaponGroups": [{"weapons": {"WS1": "w_nope"}}]}',
    )
    result = build_closure(["va_bad"], _lookup(mini_game))
    assert result.stats.missing["hull"] == ["h_nope"]
    assert result.stats.missing["weapon"] == ["w_nope"]
    assert result.sprites == {}


def test_index_by_internal_ids_and_shipsystems_wpn(mini_game):
    from conftest import _write
    _write(
        mini_game / "mods" / "mod_a" / "data" / "variants" / "file_stem.variant",
        '{"variantId": "internal_v", "hullId": "h_alpha", '
        '"weaponGroups": [{"weapons": {"WS1": "internal_w"}}]}',
    )
    _write(
        mini_game / "mods" / "mod_a" / "data" / "shipsystems" / "wpn" / "internal_w.wpn",
        '{"id": "internal_w", "turretSprite": "graphics/weapons/w_gun_t.png"}',
    )
    result = build_closure(["internal_v"], _lookup(mini_game))
    assert "graphics/ships/h_alpha.png" in result.sprites
    assert "graphics/weapons/w_gun_t.png" in result.sprites
    # h_alpha.ship 自带 builtInWeapons w_builtin，故为 internal_w + w_builtin = 2；
    # addendum 原写 1 与 conftest fixture 矛盾，按实际断言 2（仍可捕获 shipsystems/wpn 索引失效）。
    assert result.stats.weapons_resolved == 2


def test_double_slash_sprite_is_normalized(mini_game):
    from conftest import _write
    _write(
        mini_game / "mods" / "mod_a" / "data" / "hulls" / "h_alpha.ship",
        '{"hullId": "h_alpha", "hullSize": "CRUISER", '
        '"spriteName": "graphics//ships//h_alpha.png"}',
    )
    result = build_closure(["va_one"], _lookup(mini_game))
    assert "graphics/ships/h_alpha.png" in result.sprites
    assert result.sprites["graphics/ships/h_alpha.png"].owner is not None
    assert "sprite" not in result.stats.missing


def test_skin_parse_error_is_recorded(mini_game):
    from conftest import _write
    _write(mini_game / "mods" / "mod_a" / "data" / "hulls" / "skins" / "bad.skin", "{not json")
    # 非 dict 顶层：data.get 若在 try 外会抛 AttributeError 并中断 build_lookup
    _write(mini_game / "mods" / "mod_a" / "data" / "hulls" / "skins" / "list.skin", "[1, 2]")
    scan = scan_mods(mini_game, load_enabled_ids(mini_game))
    lookup = build_lookup(scan.mods)
    result = build_closure(["va_one"], lookup)
    skin_errors = result.stats.parse_errors.get("skin", [])
    assert any("bad.skin" in k for k in skin_errors)
    assert any("list.skin" in k for k in skin_errors)


def test_missing_sprite_is_recorded(mini_game):
    from conftest import _write
    _write(
        mini_game / "mods" / "mod_a" / "data" / "variants" / "va_bad_sprite.variant",
        '{"variantId": "va_bad_sprite", "hullId": "h_bad_sprite"}',
    )
    _write(
        mini_game / "mods" / "mod_a" / "data" / "hulls" / "h_bad_sprite.ship",
        '{"hullId": "h_bad_sprite", "hullSize": "FRIGATE", '
        '"spriteName": "graphics/ships/nope.png"}',
    )
    result = build_closure(["va_bad_sprite"], _lookup(mini_game))
    assert result.stats.missing["sprite"] == ["graphics/ships/nope.png"]
