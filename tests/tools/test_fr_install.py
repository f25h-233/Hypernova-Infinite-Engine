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


def test_install_does_not_touch_unrelated_launch_content(tmp_path):
    game = make_game(tmp_path)
    src = make_src(tmp_path)
    vmparams = game / "starsector-core" / "fr.vmparams"
    launch = game / "Miko_Lite.txt"
    vmparams.write_text("-Xmx10g\n", encoding="utf-8")
    launch.write_bytes(b"-javaagent:fr.agent.jar\r\n")
    fr_install.install(src, game, expected=None, version=None)
    # 0.9.8 -> 0.9.8 line already correct: memory settings untouched.
    assert vmparams.read_text(encoding="utf-8") == "-Xmx10g\n"
    assert launch.read_bytes() == b"-javaagent:fr.agent.jar\r\n"


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


# ---- FR 1.0.x：agent 内嵌进 fr.jar，启动行必须随之重指 ----


def make_src_1x(tmp_path: Path, version: str = "v1.0.1") -> Path:
    """1.0.x distribution: fr.jar only, no fr.agent.jar."""
    src = tmp_path / f"src-{version}"
    src.mkdir()
    make_jar(src / "fr.jar", version)
    (src / "fr.version.txt").write_text(version, encoding="utf-8")
    return src


def test_files_for_splits_agent_jar_at_1_0_0():
    assert fr_install.files_for("v0.9.8") == ("fr.jar", "fr.agent.jar")
    assert fr_install.files_for("v0.9.7rc2") == ("fr.jar", "fr.agent.jar")
    assert fr_install.files_for("v1.0.0") == ("fr.jar",)
    assert fr_install.files_for("v1.0.1") == ("fr.jar",)
    assert fr_install.files_for("v1.0.2rc1") == ("fr.jar",)
    assert fr_install.uses_embedded_agent("v1.0.0")
    assert not fr_install.uses_embedded_agent("v0.9.8")


def test_install_1x_keeps_version_file_and_repoints_launch(tmp_path):
    game = make_game(tmp_path)
    src = make_src_1x(tmp_path)
    vmparams = game / "starsector-core" / "fr.vmparams"
    vmparams.write_text(
        "-Xmx10g\n-javaagent:../mods/x.jar\n-javaagent:fr.agent.jar\n", encoding="utf-8")
    res = fr_install.install(src, game, expected=None, version=None)
    assert res["new_version"] == "v1.0.1"
    assert res["launch_files"] == [str(vmparams)]
    text = vmparams.read_text(encoding="utf-8")
    assert "-javaagent:fr.jar\n" in text
    assert "fr.agent.jar" not in text
    assert "-Xmx10g\n" in text, "memory settings must survive"
    assert (game / "starsector-core" / "fr.vmparams.bak-hypernova-v0.9.5").is_file()
    # A stale fr.agent.jar from 0.9.8 is left alone: FR ignores it, and the
    # rollback target may need it.
    assert (game / "starsector-core" / "fr.agent.jar").is_file()


def test_repoint_covers_the_whole_miko_family(tmp_path):
    # 260mods keeps m27/m28/phase/verbose/noagent variants. Leaving one on the
    # removed fr.agent.jar would make that profile refuse to start after an
    # upgrade and look like an incompatibility.
    game = make_game(tmp_path)
    for name in ("Miko_Simple.txt", "Miko_Lite.txt", "Miko_Lite_m27_control.txt",
                 "Miko_Lite_m28_treatment.txt", "Miko_Lite_noagent.txt",
                 "Miko_Lite_phase.txt", "Miko_Lite_verbose.txt"):
        (game / name).write_text("-Xmx4g\n-javaagent:fr.agent.jar\n", encoding="utf-8")
    (game / "Miko_Lite_nofr.txt").write_text(
        "-Xmx4g\n-javaagent:../mods/hypernova_infinite_engine/jars/x.jar\n",
        encoding="utf-8")
    changed = fr_install.repoint_launch_files(game, "v1.0.1", old_version="v0.9.8")
    assert len(changed) == 7
    for name in ("Miko_Simple.txt", "Miko_Lite_m27_control.txt",
                 "Miko_Lite_noagent.txt"):
        assert "-javaagent:fr.jar" in (game / name).read_text(encoding="utf-8")
    # The no-FR profile has no FR line and must not gain one.
    assert (game / "Miko_Lite_nofr.txt").read_text(encoding="utf-8") == (
        "-Xmx4g\n-javaagent:../mods/hypernova_infinite_engine/jars/x.jar\n")


def test_install_1x_does_not_require_target_agent_jar(tmp_path):
    game = tmp_path / "Starsector"
    core = game / "starsector-core"
    core.mkdir(parents=True)
    make_jar(core / "fr.jar", "v0.9.8")
    (core / "fr.version.txt").write_text("v0.9.8", encoding="utf-8")
    # No fr.agent.jar in the target at all: installing 1.0.1 must still work.
    fr_install.install(make_src_1x(tmp_path), game, expected=None, version=None)
    assert fr_install.installed_version(game) == "v1.0.1"


def test_install_1x_can_skip_repoint(tmp_path):
    game = make_game(tmp_path)
    src = make_src_1x(tmp_path)
    vmparams = game / "starsector-core" / "fr.vmparams"
    vmparams.write_text("-javaagent:fr.agent.jar\n", encoding="utf-8")
    res = fr_install.install(src, game, expected=None, version=None, repoint=False)
    assert res["launch_files"] == []
    assert vmparams.read_text(encoding="utf-8") == "-javaagent:fr.agent.jar\n"


def test_rollback_1x_to_098_restores_agent_jar_and_line(tmp_path):
    game = make_game(tmp_path)
    src = make_src(tmp_path, "v0.9.8")
    fr_install.install(src, game, expected=None, version=None)
    res = fr_install.rollback(game, to_version="v0.9.5")
    assert res["to_version"] == "v0.9.5"
    assert fr_install.installed_version(game) == "v0.9.5"
    # The 0.9.5 target ships fr.agent.jar, so the rollback must restore it.
    core = game / "starsector-core"
    assert any(p.endswith("fr.agent.jar") for p in res["restored"])


def test_rollback_from_098_to_1x_targets_only_fr_jar(tmp_path):
    game = make_game(tmp_path)
    core = game / "starsector-core"
    # synthesize a 1.0.1 backup the user could have made
    make_jar(core / "fr.jar.bak-hypernova-v1.0.1", "v1.0.1")
    res = fr_install.rollback(game, to_version="v1.0.1")
    assert res["to_version"] == "v1.0.1"
    assert len(res["restored"]) == 1
    assert res["restored"][0].endswith("fr.jar")


def test_repoint_is_idempotent(tmp_path):
    game = make_game(tmp_path)
    src = make_src_1x(tmp_path)
    vmparams = game / "starsector-core" / "fr.vmparams"
    vmparams.write_text("-javaagent:fr.agent.jar\n", encoding="utf-8")
    fr_install.install(src, game, expected=None, version=None)
    assert fr_install.repoint_launch_files(
        game, "v1.0.1") == [], "already correct must report no change"


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


def test_pins_cover_all_supported_versions():
    assert set(fr_install.EXPECTED_PINS) == {
        "v0.9.7rc2", "v0.9.8", "v1.0.0", "v1.0.1"}
    assert fr_install.EXPECTED_PINS["v0.9.8"]["fr.jar"] == (
        "c7d91b0c8f7aaaa3380b52d6549681d75a93f6b626ad06a673002b845da04ffd")
    assert fr_install.EXPECTED_PINS["v0.9.8"]["fr.agent.jar"] == (
        "55eecda58608cf1c6a23466acc957bdb93d648d6800d7527769c07450a884cbb")
    # 1.0.x ships no fr.agent.jar: the agent classes live inside fr.jar.
    for v in ("v1.0.0", "v1.0.1"):
        assert set(fr_install.EXPECTED_PINS[v]) == {"fr.jar"}
    assert fr_install.EXPECTED_PINS["v1.0.1"]["fr.jar"] == (
        "150ebc21f0191acb4c1452aaa809f3fc129f98933d9e7c8f5b366e2888291187")


def test_pins_for_infers_version_from_source(tmp_path):
    src = make_src(tmp_path, "v0.9.8")
    pins, version = fr_install.pins_for(src, None)
    assert version == "v0.9.8"
    assert pins == fr_install.EXPECTED_PINS["v0.9.8"]


def test_pins_for_rejects_unknown_version(tmp_path):
    src = make_src(tmp_path, "v0.9.9")
    with pytest.raises(fr_install.FrInstallError):
        fr_install.pins_for(src, None)
