import json
from pathlib import Path

import pytest

from m6_audit_matrix import scan_environment


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def audit_game(tmp_path):
    root = tmp_path / "game"
    _write(
        root / "starsector-core" / "data" / "config" / "settings.json",
        '{"localeOverride":"en_US","cjkMode":true,'
        '"defaultFont":"graphics/fonts/insignia15LTaa.fnt"}',
    )
    _write(
        root / "starsector-core" / "data" / "strings" / "strings.json",
        '{"a":{"x":"开始游戏","y":"load game"},"b":{"z":"读取存档"}}',
    )
    _write(
        root / "mods" / "enabled_mods.json",
        json.dumps({"enabledMods": ["ChineseInputFix", "FontMod", "UiMod", "missing_mod"]}),
    )
    # ChineseInputFix 的真实形状：尾逗号（标准 json.load 会失败）
    _write(
        root / "mods" / "ChineseInputFix" / "mod_info.json",
        '{"id":"ChineseInputFix","name":"中文输入修复",'
        '"version":{"major":2,"minor":0,"patch":0},}',
    )
    (root / "mods" / "FontMod" / "graphics" / "fonts").mkdir(parents=True)
    _write(root / "mods" / "FontMod" / "mod_info.json", '{"id":"FontMod","name":"Font"}')
    (root / "mods" / "UiMod" / "graphics" / "ui").mkdir(parents=True)
    _write(root / "mods" / "UiMod" / "mod_info.json", '{"id":"UiMod","name":"UI"}')
    _write(
        root / "mods" / "hypernova_infinite_engine" / "data" / "config"
        / "hypernova" / "hypernova.json",
        '{"enabled":true,"eviction":false,"textures":{"enabled":true}}',
    )
    return root


def test_scan_environment_counts_nested_cjk_and_mods(audit_game):
    data = scan_environment(audit_game)
    assert data["locale_override"] == "en_US"
    assert data["cjk_mode"] is True
    assert data["default_font"] == "graphics/fonts/insignia15LTaa.fnt"
    assert data["strings"]["total_strings"] == 3
    assert data["strings"]["cjk_strings"] == 2
    assert data["mods"]["enabled_count"] == 4
    assert data["mods"]["parse_errors"] == {}
    assert data["mods"]["duplicate_ids"] == {}


def test_scan_environment_accepts_tail_comma_mod_info(audit_game):
    data = scan_environment(audit_game)
    assert data["chinese_input_fix"] == {
        "present": True, "enabled": True, "version": "2.0.0"
    }


def test_scan_environment_detects_font_and_ui_overrides(audit_game):
    data = scan_environment(audit_game)
    by_id = {m["mod_id"]: m for m in data["font_ui_mods"]}
    assert by_id["FontMod"]["fonts"] is True
    assert by_id["UiMod"]["ui"] is True
    assert by_id["ChineseInputFix"]["fonts"] is False


def test_scan_environment_reports_hypernova_defaults(audit_game):
    data = scan_environment(audit_game)
    assert data["hypernova"] == {
        "enabled": True,
        "textures_enabled": True,
        "lazy": False,
        "eviction": False,
        "scene_unload": False,
    }


def test_scan_environment_reports_missing_enabled_mod(audit_game):
    data = scan_environment(audit_game)
    assert data["mods"]["enabled_count"] == 4
    # missing_mod 没有目录：scanned_count 只数实际扫描到的 mod
    assert data["mods"]["scanned_count"] == 3
