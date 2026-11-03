import json
from pathlib import Path

import pytest

from m6_audit_matrix import main, scan_environment

HN_REL = (
    Path("mods")
    / "hypernova_infinite_engine"
    / "data"
    / "config"
    / "hypernova"
    / "hypernova.json"
)
REQUIRED_FILES = (
    Path("starsector-core") / "data" / "config" / "settings.json",
    Path("starsector-core") / "data" / "strings" / "strings.json",
    Path("mods") / "enabled_mods.json",
    HN_REL,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _minimal_root(tmp_path: Path) -> Path:
    root = tmp_path / "minimal-game"
    _write(root / "starsector-core" / "data" / "config" / "settings.json", "{}")
    _write(root / "starsector-core" / "data" / "strings" / "strings.json", "{}")
    _write(root / "mods" / "enabled_mods.json", '{"enabledMods": []}')
    _write(root / HN_REL, "{}")
    return root


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
        '{"enabled":true,"textures":{"enabled":true,"lazy":{"enabled":true,'
        '"eviction":{"enabled":true,"scene_unload":{"enabled":true}}}}}',
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


def test_scan_environment_reports_hypernova_nested_flags(audit_game):
    data = scan_environment(audit_game)
    assert data["hypernova"] == {
        "enabled": True,
        "textures_enabled": True,
        "lazy": True,
        "eviction": True,
        "scene_unload": True,
        "textures_present": True,
        "enabled_explicit": True,
    }


def test_scan_environment_reports_missing_enabled_mod(audit_game):
    data = scan_environment(audit_game)
    assert data["mods"]["enabled_count"] == 4
    # missing_mod 没有目录：scanned_count 只数实际扫描到的 mod
    assert data["mods"]["scanned_count"] == 3
    assert data["mods"]["scanned_total"] == 3
    assert data["mods"]["missing_enabled_ids"] == ["missing_mod"]


def test_scan_environment_uses_product_defaults_when_missing(tmp_path):
    data = scan_environment(_minimal_root(tmp_path))
    assert data["hypernova"] == {
        "enabled": True,
        "textures_enabled": True,
        "lazy": False,
        "eviction": False,
        "scene_unload": False,
        "textures_present": False,
        "enabled_explicit": False,
    }


def test_scan_environment_distinguishes_explicit_disable(tmp_path):
    root = _minimal_root(tmp_path)
    _write(root / HN_REL, '{"enabled": false, "textures": {"enabled": false}}')
    hypernova = scan_environment(root)["hypernova"]
    assert hypernova["enabled"] is False
    assert hypernova["enabled_explicit"] is True
    assert hypernova["textures_enabled"] is False
    assert hypernova["textures_present"] is True


def test_scan_environment_keeps_raw_ids_with_trailing_space(tmp_path):
    root = _minimal_root(tmp_path)
    _write(root / "mods" / "enabled_mods.json", '{"enabledMods": ["tail "]}')
    _write(root / "mods" / "tail_mod" / "mod_info.json", '{"id": "tail "}')
    mods = scan_environment(root)["mods"]
    assert mods["enabled_count"] == 1
    assert mods["scanned_total"] == 1
    assert mods["scanned_count"] == 1
    assert mods["missing_enabled_ids"] == []


def test_scan_environment_reports_duplicate_ids(tmp_path):
    root = _minimal_root(tmp_path)
    for folder in ("dup_a", "dup_b"):
        _write(root / "mods" / folder / "mod_info.json", '{"id": "dup_same"}')
    mods = scan_environment(root)["mods"]
    assert mods["duplicate_ids"] == {"dup_same": ["dup_a", "dup_b"]}
    assert mods["scanned_total"] == 1


@pytest.mark.parametrize("rel", REQUIRED_FILES)
def test_cli_missing_required_file_fails_closed(tmp_path, capsys, rel):
    root = _minimal_root(tmp_path)
    (root / rel).unlink()
    rc = main(["--game-root", str(root)])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    err_lines = captured.err.strip().splitlines()
    assert len(err_lines) == 1
    assert err_lines[0].startswith("FATAL: missing ")
    assert rel.name in err_lines[0]


def test_cli_out_write_failure_fails_closed(tmp_path, capsys):
    root = _minimal_root(tmp_path)
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    rc = main(["--game-root", str(root), "--out", str(blocker / "out.json")])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    err_lines = captured.err.strip().splitlines()
    assert len(err_lines) == 1
    assert err_lines[0].startswith("FATAL: ")
