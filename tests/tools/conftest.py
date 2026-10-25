import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


import json
import struct
from pathlib import Path

import pytest


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _png(w: int, h: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", w, h)
        + b"\x08\x06\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )


@pytest.fixture
def mini_game(tmp_path):
    root = tmp_path / "game"
    _write(
        root / "mods" / "enabled_mods.json",
        json.dumps(
            {
                "enabledMods": [
                    "mod_a",
                    "mod_b",
                    "mod_[x]",
                    "mod_中文",
                    "shaderLib",
                    "GraphicsLib",
                    "missing_mod",
                ]
            },
            ensure_ascii=False,
        ),
    )

    # mod_a: 注释、尾逗号、单引号、skin、module、wing、内置武器
    _write(
        root / "mods" / "mod_a" / "mod_info.json",
        '{ "id": "mod_a", # comment\n "name": "A", }',
    )
    _write(
        root / "mods" / "mod_a" / "data" / "config" / "title_screen_variants.csv",
        'variant id\nva_one\n# comment row\n"va_two"\n',
    )
    _write(
        root / "mods" / "mod_a" / "data" / "variants" / "va_one.variant",
        json.dumps(
            {
                "variantId": "va_one",
                "hullId": "h_alpha",
                "weaponGroups": [{"weapons": {"WS1": "w_gun"}}],
                "modules": [{"M1": "va_module"}],
                "wings": ["wing_one"],
            }
        ),
    )
    _write(
        root / "mods" / "mod_a" / "data" / "variants" / "va_two.variant",
        json.dumps({"variantId": "va_two", "hullId": "h_skin"}),
    )
    _write(
        root / "mods" / "mod_a" / "data" / "variants" / "va_module.variant",
        json.dumps({"variantId": "va_module", "hullId": "h_module"}),
    )
    _write(
        root / "mods" / "mod_a" / "data" / "variants" / "wing_one_Fighter.variant",
        json.dumps({"variantId": "wing_one_Fighter", "hullId": "h_fighter"}),
    )
    _write(
        root / "mods" / "mod_a" / "data" / "hulls" / "h_alpha.ship",
        json.dumps(
            {
                "hullId": "h_alpha",
                "hullSize": "CRUISER",
                "spriteName": "graphics/ships/h_alpha.png",
                "builtInWeapons": {"W1": "w_builtin"},
            }
        ),
    )
    _write(
        root / "mods" / "mod_a" / "data" / "hulls" / "h_module.ship",
        json.dumps(
            {
                "hullId": "h_module",
                "hullSize": "FRIGATE",
                "spriteName": "graphics/ships/h_module.png",
            }
        ),
    )
    _write(
        root / "mods" / "mod_a" / "data" / "hulls" / "h_fighter.ship",
        json.dumps(
            {
                "hullId": "h_fighter",
                "hullSize": "FIGHTER",
                "spriteName": "graphics/ships/h_fighter.png",
            }
        ),
    )
    _write(
        root / "mods" / "mod_a" / "data" / "hulls" / "skins" / "h_skin.skin",
        json.dumps(
            {
                "baseHullId": "h_base",
                "skinHullId": "h_skin",
                "spriteName": "graphics/ships/h_skin.png",
                "builtInWeapons": {"W2": "w_builtin"},
            }
        ),
    )
    _write(
        root / "mods" / "mod_a" / "data" / "hulls" / "h_base.ship",
        json.dumps(
            {
                "hullId": "h_base",
                "hullSize": "DESTROYER",
                "spriteName": "graphics/ships/h_base.png",
            }
        ),
    )
    _write(
        root / "mods" / "mod_a" / "data" / "hulls" / "wing_data.csv",
        "id,variant,tags\nwing_one,wing_one_Fighter,fighter\n",
    )
    _write(
        root / "mods" / "mod_a" / "data" / "weapons" / "w_gun.wpn",
        json.dumps(
            {
                "id": "w_gun",
                "turretSprite": "graphics/weapons/w_gun_t.png",
                "hardpointSprite": "graphics/weapons/w_gun_h.png",
                "turretGlowSprite": "",
                "hardpointGlowSprite": "",
                "turretGunSprite": "",
                "hardpointGunSprite": "",
                "turretUnderSprite": "",
                "hardpointUnderSprite": "",
            }
        ),
    )
    _write(
        root / "mods" / "mod_a" / "data" / "weapons" / "w_builtin.wpn",
        json.dumps({"id": "w_builtin", "turretSprite": "graphics/weapons/w_builtin.png"}),
    )
    for rel, size in {
        "graphics/ships/h_alpha.png": (64, 32),
        "graphics/ships/h_module.png": (8, 8),
        "graphics/ships/h_fighter.png": (8, 8),
        "graphics/ships/h_skin.png": (16, 16),
        "graphics/ships/h_base.png": (16, 16),
        "graphics/weapons/w_gun_t.png": (7, 7),
        "graphics/weapons/w_gun_h.png": (7, 7),
        "graphics/weapons/w_builtin.png": (7, 7),
        "graphics/unlisted.png": (3, 3),
    }.items():
        p = root / "mods" / "mod_a" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(_png(*size))

    # mod_b: 同路径覆盖 + 重复 variant id
    _write(root / "mods" / "mod_b" / "mod_info.json", '{"id": "mod_b"}')
    _write(
        root / "mods" / "mod_b" / "data" / "variants" / "va_one.variant",
        json.dumps({"variantId": "va_one", "hullId": "h_beta"}),
    )
    _write(
        root / "mods" / "mod_b" / "data" / "hulls" / "h_beta.ship",
        json.dumps(
            {
                "hullId": "h_beta",
                "hullSize": "CRUISER",
                "spriteName": "graphics/ships/h_alpha.png",
            }
        ),
    )
    (root / "mods" / "mod_b" / "graphics" / "ships").mkdir(parents=True)
    (root / "mods" / "mod_b" / "graphics" / "ships" / "h_alpha.png").write_bytes(
        _png(64, 32)
    )

    # 带方括号 / 中文的 mod 文件夹
    _write(root / "mods" / "mod_[x]" / "mod_info.json", '{"id": "mod_[x]"}')
    _write(root / "mods" / "mod_中文" / "mod_info.json", '{"id": "mod_中文"}')

    # shader 库（用于 scope 排除）
    _write(root / "mods" / "shaderLib" / "mod_info.json", '{"id": "shaderLib"}')
    _write(root / "mods" / "GraphicsLib" / "mod_info.json", '{"id": "GraphicsLib"}')
    for folder in ("shaderLib", "GraphicsLib"):
        p = root / "mods" / folder / "graphics" / "shader" / "x.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(_png(2, 2))

    # core
    _write(root / "starsector-core" / "data" / "config" / "title_screen_variants.csv",
           "variant id\nv_core\n")
    _write(
        root / "starsector-core" / "data" / "variants" / "v_core.variant",
        json.dumps({"variantId": "v_core", "hullId": "h_core"}),
    )
    _write(
        root / "starsector-core" / "data" / "hulls" / "h_core.ship",
        json.dumps(
            {
                "hullId": "h_core",
                "hullSize": "FRIGATE",
                "spriteName": "graphics/ships/h_core.png",
            }
        ),
    )
    (root / "starsector-core" / "graphics" / "ships").mkdir(parents=True)
    (root / "starsector-core" / "graphics" / "ships" / "h_core.png").write_bytes(
        _png(4, 4)
    )

    # DDSCache：mod_a 两条、core 一条；路径用反斜杠
    _write(
        root / "mods" / "DDSCache" / "mod_a" / "dds_metadata.json",
        json.dumps(
            [
                {
                    "ModFolderName": "mod_a",
                    "RelativeImagePath": "graphics\\ships\\h_alpha.png",
                    "DDSFilePath": "\\mods\\DDSCache\\mod_a\\graphics\\ships\\h_alpha.dds",
                    "Width": 64,
                    "Height": 32,
                },
                {
                    "ModFolderName": "mod_a",
                    "RelativeImagePath": "graphics\\weapons\\w_gun_t.png",
                    "DDSFilePath": "\\mods\\DDSCache\\mod_a\\graphics\\weapons\\w_gun_t.dds",
                    "Width": 7,
                    "Height": 7,
                },
            ]
        ),
    )
    _write(
        root / "mods" / "DDSCache" / "starsector-core" / "dds_metadata.json",
        json.dumps(
            [
                {
                    "ModFolderName": "starsector-core",
                    "RelativeImagePath": "graphics\\ships\\h_core.png",
                    "DDSFilePath": "\\mods\\DDSCache\\starsector-core\\graphics\\ships\\h_core.dds",
                    "Width": 4,
                    "Height": 4,
                }
            ]
        ),
    )
    for rel in (
        "mods/DDSCache/mod_a/graphics/ships/h_alpha.dds",
        "mods/DDSCache/mod_a/graphics/weapons/w_gun_t.dds",
        "mods/DDSCache/starsector-core/graphics/ships/h_core.dds",
    ):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"DDS ")
    return root
