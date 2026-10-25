import json
import subprocess
import sys
from pathlib import Path

from conftest import _png, _write
from l1_core import CORE_STATIC, PLANET_FIELDS, PLANET_TYPES
from manifest_builder import build_manifest


def _seed_core(mini_game):
    for rel in CORE_STATIC:
        p = mini_game / "starsector-core" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(_png(2, 2))
    planets = {}
    for t in PLANET_TYPES:
        planets[t] = {f: f"graphics/planets/{t}_{f}.jpg" for f in PLANET_FIELDS}
        for f in PLANET_FIELDS:
            p = mini_game / "starsector-core" / planets[t][f]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(_png(2, 2))
    _write(
        mini_game / "starsector-core" / "data" / "config" / "planets.json",
        json.dumps(planets),
    )


def _build(mini_game, **kwargs):
    _seed_core(mini_game)
    return build_manifest(mini_game, **kwargs).manifest


def test_l1_contains_core_and_closure(mini_game):
    m = _build(mini_game)
    paths = {e["path"] for e in m["layers"]["L1"]}
    assert "graphics/ui/starsector_title_alpha.png" in paths
    assert "graphics/ships/h_alpha.png" in paths
    assert "graphics/weapons/w_gun_t.png" in paths
    assert "graphics/ships/h_module.png" in paths
    assert "graphics/ships/h_fighter.png" in paths
    assert "graphics/ships/h_core.png" in paths


def test_l2_entity_pool_contains_orphan_variant(mini_game):
    _write(
        mini_game / "mods" / "mod_a" / "data" / "variants" / "va_orphan.variant",
        '{"variantId": "va_orphan", "hullId": "h_orphan"}',
    )
    _write(
        mini_game / "mods" / "mod_a" / "data" / "hulls" / "h_orphan.ship",
        '{"hullId": "h_orphan", "hullSize": "FRIGATE", '
        '"spriteName": "graphics/ships/h_orphan.png"}',
    )
    p = mini_game / "mods" / "mod_a" / "graphics" / "ships" / "h_orphan.png"
    p.write_bytes(_png(5, 5))
    m = _build(mini_game)
    l2 = {e["path"] for e in m["layers"]["L2"]}
    assert "graphics/ships/h_orphan.png" in l2


def test_l3_contains_remaining_metadata_and_disk_images(mini_game):
    p = mini_game / "mods" / "mod_a" / "graphics" / "other.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_png(9, 9))
    m = _build(mini_game)
    l3 = {e["path"] for e in m["layers"]["L3"]}
    assert "graphics/other.png" in l3
    assert "graphics/unlisted.png" in l3
    assert "graphics/ships/h_alpha.png" not in l3


def test_scope_and_stats(mini_game):
    m = _build(mini_game)
    stats = m["stats"]
    assert stats["scope"] == "mod_non_shader"
    assert stats["metadata_entries"] == 2
    assert stats["core_entries"] == 1
    assert stats["baked"] == 2
    assert stats["coverage"]["metadata"] == 1.0
    assert stats["coverage"]["closure_refs"] == 1.0
    assert stats["coverage"]["l1_sprite_disk"] == 1.0


def test_no_l2_and_no_core(mini_game):
    m = _build(mini_game, include_l2=False, include_core=False)
    assert m["layers"]["L2"] == []
    assert m["stats"]["core_entries"] == 0


def test_manifest_is_deterministic(mini_game):
    a = _build(mini_game)
    b = _build(mini_game)
    assert a["layers"] == b["layers"]
    assert a["stats"] == b["stats"]


def test_cli_writes_manifest(mini_game):
    _seed_core(mini_game)
    out = mini_game / "out.json"
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [
            sys.executable,
            "-I",
            str(root / "tools" / "gen_manifest.py"),
            "--game-root",
            str(mini_game),
            "--out",
            str(out),
            "--no-l2",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema"] == 1
    assert data["layers"]["L1"]
