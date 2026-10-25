import json

from conftest import _write
from l1_core import CORE_STATIC, core_assets


def test_core_static_is_deduped_and_planets_read(mini_game):
    _write(
        mini_game / "starsector-core" / "data" / "config" / "planets.json",
        json.dumps(
            {
                "desert": {"texture": "graphics/planets/desert.jpg"},
                "arid": {"texture": "graphics/planets/arid.jpg"},
            }
        ),
    )
    got = core_assets(mini_game)
    assert "graphics/ui/starsector_title_alpha.png" in got
    assert "graphics/planets/desert.jpg" in got
    assert got.count("graphics/planets/desert.jpg") == 1


def test_missing_planets_json_falls_back_to_static(tmp_path):
    assert core_assets(tmp_path) == CORE_STATIC


def test_bad_planets_json_is_recorded_not_swallowed(mini_game):
    from l1_core import core_assets_result
    _write(
        mini_game / "starsector-core" / "data" / "config" / "planets.json",
        "{not json",
    )
    result = core_assets_result(mini_game)
    assert result.paths == CORE_STATIC
    assert any("planets.json" in key for key in result.parse_errors)


def test_good_planets_json_has_no_errors(mini_game):
    from l1_core import core_assets_result
    _write(
        mini_game / "starsector-core" / "data" / "config" / "planets.json",
        '{"desert": {"texture": "graphics/planets/desert.jpg"}}',
    )
    result = core_assets_result(mini_game)
    assert result.parse_errors == {}
    assert "graphics/planets/desert.jpg" in result.paths
