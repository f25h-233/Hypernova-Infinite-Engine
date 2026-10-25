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
