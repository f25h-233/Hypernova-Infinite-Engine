"""L1 的 core 固定资产：标题 UI/字体/光标/背景/行星/目标点。"""
from __future__ import annotations

from pathlib import Path

from hn_json import load

CORE_STATIC = [
    "graphics/ui/starsector_title_alpha.png",
    "graphics/backgrounds/background4.jpg",
    "graphics/backgrounds/star0.png",
    "graphics/backgrounds/star1.png",
    "graphics/fx/scanline11.png",
    "graphics/fx/noise.png",
    "graphics/planets/atmosphere.png",
    "graphics/planets/atmosphere2.png",
    "graphics/ships/nav_buoy.png",
    "graphics/ships/sensor_array.png",
    "graphics/fonts/orbitron20aa_0.png",
    "graphics/fonts/orbitron20aabold_0.png",
    "graphics/fonts/orbitron24aabold_0.png",
    "graphics/fonts/orbitron12condensed_0.png",
    "graphics/cursors/cursor_blue.png",
    "graphics/cursors/cursor_blue_2x.png",
    "graphics/cursors/cursor_green.png",
    "graphics/cursors/cursor_red.png",
    "graphics/cursors/cursor_red_2x.png",
    "graphics/ui/bgs/ui_border1_n.png",
    "graphics/ui/bgs/ui_border1_ne.png",
    "graphics/ui/bgs/ui_border1_e.png",
    "graphics/ui/bgs/ui_border1_se.png",
    "graphics/ui/bgs/ui_border1_s.png",
    "graphics/ui/bgs/ui_border1_sw.png",
    "graphics/ui/bgs/ui_border1_w.png",
    "graphics/ui/bgs/ui_border1_nw.png",
]

PLANET_TYPES = [
    "cryovolcanic",
    "desert",
    "lava",
    "ice_giant",
    "star_yellow",
    "terran",
    "jungle",
    "gas_giant",
    "arid",
]
PLANET_FIELDS = ("texture", "cloudTexture", "glowTexture")


def core_assets(game_root: Path) -> list[str]:
    paths = list(CORE_STATIC)
    config = game_root / "starsector-core" / "data" / "config" / "planets.json"
    if config.is_file():
        try:
            planets = load(config)
        except Exception:
            planets = {}
        if isinstance(planets, dict):
            for planet_type in PLANET_TYPES:
                entry = planets.get(planet_type)
                if not isinstance(entry, dict):
                    continue
                for field in PLANET_FIELDS:
                    value = entry.get(field)
                    if isinstance(value, str) and value.strip():
                        paths.append(value.replace("\\", "/").lstrip("/"))
    seen = set()
    out = []
    for path in paths:
        key = path.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out
