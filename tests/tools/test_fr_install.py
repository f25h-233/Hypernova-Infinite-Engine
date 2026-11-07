import json
import zipfile
from pathlib import Path

import pytest

import fr_install


def make_jar(path: Path, version: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        z.writestr("com/genir/renderer/Version.class", b"\xca\xfe\xba\xbe" + version.encode())


def make_game(tmp_path: Path, version: str = "v0.9.5") -> Path:
    game = tmp_path / "Starsector"
    core = game / "starsector-core"
    core.mkdir(parents=True)
    make_jar(core / "fr.jar", version)
    make_jar(core / "fr.agent.jar", version)
    (core / "fr.version.txt").write_text(version, encoding="utf-8")
    return game


def make_src(tmp_path: Path, version: str = "v0.9.7rc2") -> Path:
    src = tmp_path / "src"
    src.mkdir()
    make_jar(src / "fr.jar", version)
    make_jar(src / "fr.agent.jar", version)
    (src / "fr.version.txt").write_text(version, encoding="utf-8")
    return src


def test_jar_version_reads_baked_string(tmp_path):
    jar = tmp_path / "fr.jar"
    make_jar(jar, "v0.9.7rc2")
    assert fr_install.jar_version(jar) == "v0.9.7rc2"


def test_install_backs_up_and_replaces(tmp_path):
    game = make_game(tmp_path)
    src = make_src(tmp_path)
    res = fr_install.install(src, game, expected=None, version=None)
    assert res["old_version"] == "v0.9.5"
    assert res["new_version"] == "v0.9.7rc2"
    core = game / "starsector-core"
    assert (core / "fr.jar.bak-hypernova-v0.9.5").is_file()
    assert (core / "fr.agent.jar.bak-hypernova-v0.9.5").is_file()
    assert fr_install.installed_version(game) == "v0.9.7rc2"


def test_install_is_idempotent(tmp_path):
    game = make_game(tmp_path)
    src = make_src(tmp_path)
    fr_install.install(src, game, expected=None, version=None)
    second = fr_install.install(src, game, expected=None, version=None)
    assert second["changed"] is False
    assert second["backups"] == []
    backups = list((game / "starsector-core").glob("fr.jar.bak-hypernova-*"))
    assert len(backups) == 1


def test_install_refuses_missing_target_jar(tmp_path):
    game = tmp_path / "Starsector"
    (game / "starsector-core").mkdir(parents=True)
    with pytest.raises(fr_install.FrInstallError):
        fr_install.install(make_src(tmp_path), game, expected=None, version=None)


def test_install_verifies_pins(tmp_path):
    game = make_game(tmp_path)
    src = make_src(tmp_path)
    with pytest.raises(fr_install.FrInstallError):
        fr_install.install(src, game, expected={"fr.jar": "0" * 64}, version=None)


def test_install_does_not_touch_launch_files(tmp_path):
    game = make_game(tmp_path)
    src = make_src(tmp_path)
    vmparams = game / "starsector-core" / "fr.vmparams"
    launch = game / "Miko_Lite.txt"
    vmparams.write_text("-Xmx10g\n", encoding="utf-8")
    launch.write_bytes(b"-javaagent:fr.agent.jar\r\n")
    before = (vmparams.read_bytes(), launch.read_bytes())
    fr_install.install(src, game, expected=None, version=None)
    assert (vmparams.read_bytes(), launch.read_bytes()) == before


def test_rollback_restores_and_preserves_current(tmp_path):
    game = make_game(tmp_path)
    src = make_src(tmp_path)
    fr_install.install(src, game, expected=None, version=None)
    res = fr_install.rollback(game, to_version="v0.9.5")
    assert res["from_version"] == "v0.9.7rc2"
    assert res["to_version"] == "v0.9.5"
    assert fr_install.installed_version(game) == "v0.9.5"
    core = game / "starsector-core"
    assert (core / "fr.jar.bak-hypernova-v0.9.7rc2").is_file()


def test_rollback_without_backup_fails(tmp_path):
    game = make_game(tmp_path)
    with pytest.raises(fr_install.FrInstallError):
        fr_install.rollback(game, to_version="v0.9.0")


def test_status_reports_hashes(tmp_path):
    game = make_game(tmp_path)
    data = fr_install.status(game)
    assert data["version"] == "v0.9.5"
    assert data["fr_sha256"]
    assert data["agent_sha256"]


def test_cli_status_returns_json(tmp_path):
    game = make_game(tmp_path)
    import subprocess
    import sys
    r = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[2] / "tools" / "fr_install.py"),
         "--game", str(game), "--action", "status"],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(r.stdout)
    assert data["version"] == "v0.9.5"


def test_pins_cover_both_supported_versions():
    assert set(fr_install.EXPECTED_PINS) == {"v0.9.7rc2", "v0.9.8"}
    assert fr_install.EXPECTED_PINS["v0.9.8"]["fr.jar"] == (
        "c7d91b0c8f7aaaa3380b52d6549681d75a93f6b626ad06a673002b845da04ffd")
    assert fr_install.EXPECTED_PINS["v0.9.8"]["fr.agent.jar"] == (
        "55eecda58608cf1c6a23466acc957bdb93d648d6800d7527769c07450a884cbb")


def test_pins_for_infers_version_from_source(tmp_path):
    src = make_src(tmp_path, "v0.9.8")
    pins, version = fr_install.pins_for(src, None)
    assert version == "v0.9.8"
    assert pins == fr_install.EXPECTED_PINS["v0.9.8"]


def test_pins_for_rejects_unknown_version(tmp_path):
    src = make_src(tmp_path, "v0.9.9")
    with pytest.raises(fr_install.FrInstallError):
        fr_install.pins_for(src, None)
