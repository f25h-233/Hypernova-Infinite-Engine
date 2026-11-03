import json
from pathlib import Path

import pytest

from m7_stack import inspect_root


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def mini_install(tmp_path):
    root = tmp_path / "install"
    _write(root / "starsector-core/localization_version.json", json.dumps({
        "name": "远行星号中文汉化包", "author": "远星汉化组",
        "version": "2026.10.15", "branch": "startup-optimization",
        "language": "zh-Hans", "game_version": "0.98a-RC8",
    }))
    _write(root / "starsector-core/graphics/fonts/dyn_font/chars.txt", "a\n")
    (root / "starsector-core/native/windows").mkdir(parents=True)
    (root / "starsector-core/native/windows/ssime.dll").write_bytes(b"x")
    _write(root / "vmparams", "java.exe -Xmx2g com.fs.starfarer.StarfarerLauncher\n")
    _write(root / "mods/enabled_mods.json", json.dumps({"enabledMods": []}))
    _write(root / "jre/release", "JAVA_VERSION=\"17.0.10\"\n")
    return root


def test_inspect_root_reports_chinese_optimized_build(mini_install):
    data = inspect_root(mini_install)
    assert data["localization"]["version"] == "2026.10.15"
    assert data["localization"]["branch"] == "startup-optimization"
    assert data["dyn_font"] is True
    assert data["ssime_dll"] is True
    assert data["jre_version"] == "17.0.10"
    assert data["vmparams"]["has_agent"] is False
    assert data["mods"]["enabled_count"] == 0


def test_inspect_root_detects_agents_and_flags(mini_install):
    _write(mini_install / "vmparams",
           "java.exe -javaagent:..\\mods\\MixinFR\\jars\\MixinLib-bridge.jar "
           "-Dhypernova.frameProbe=true com.fs.starfarer.StarfarerLauncher\n")
    data = inspect_root(mini_install)
    assert data["vmparams"]["has_agent"] is True
    assert "MixinLib-bridge.jar" in data["vmparams"]["agents"][0]
    assert "frameProbe" in data["vmparams"]["hypernova_flags"][0]
