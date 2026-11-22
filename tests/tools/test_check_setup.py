"""Tests for the player-facing self-check.

The check exists so players never have to open a log. Its output must therefore
be actionable: every failure has to name the file to double-click, and the
things that are normal on a given route must not be reported as failures.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "player-tools"))

import check_setup as cs  # noqa: E402
import setup_agent as sa  # noqa: E402

BS = "\\"
MIXIN = f"-javaagent:..{BS}mods{BS}MixinFR{BS}jars{BS}MixinLib-bridge.jar"
AGENT = "-javaagent:../mods/hypernova_infinite_engine/jars/hypernova.agent.jar"
MAIN = "com.fs.starfarer.StarfarerLauncher"


def make_game(tmp_path, *, route="b", with_agent=True, with_jar=True,
              agent_log="", game_log=""):
    game = tmp_path / "game"
    core = game / "starsector-core"
    core.mkdir(parents=True)
    mod_dir = game / "mods/hypernova_infinite_engine/jars"
    mod_dir.mkdir(parents=True)
    if with_jar:
        (mod_dir / "hypernova.agent.jar").write_bytes(b"x")
        (mod_dir / "hypernova.jar").write_bytes(b"x")

    if route == "b":
        lines = ["-Xmx4096m"]
        if with_agent:
            lines.append(AGENT)
        lines += ["-javaagent:fr.agent.jar", MAIN]
        (game / "Miko_Simple.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        tokens = ["java.exe", MIXIN]
        if with_agent:
            tokens.append(AGENT)
        tokens.append(MAIN)
        (game / "vmparams").write_text(" ".join(tokens), encoding="utf-8")

    if agent_log:
        p = game / "saves/hypernova/scripts-agent.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(agent_log, encoding="utf-8")
    if game_log:
        (core / "starsector.log").write_text(game_log, encoding="utf-8")

    (game / "mods/enabled_mods.json").write_text(
        '{"enabledMods":["hypernova_infinite_engine"]}', encoding="utf-8")
    return game


GOOD_AGENT_LOG = (
    "hypernova agent premain; config=...\n"
    "scripts cache transformer registered\n"
    "textures: patched org/dark/shaders/util/TextureData\n"
    "file index: loaded mod_entries=3748\n"
)
MENU_LOG = "12345 [main] INFO sound.H - Playing music with id [miscallenous_main_menu.ogg]\n"


def run(game) -> tuple[int, str]:
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    argv = sys.argv
    sys.argv = ["check_setup.py", "--game", str(game)]
    try:
        with redirect_stdout(buf):
            rc = cs.main()
    finally:
        sys.argv = argv
    return rc, buf.getvalue()


def test_healthy_install_passes(tmp_path):
    game = make_game(tmp_path, agent_log=GOOD_AGENT_LOG, game_log=MENU_LOG)
    rc, out = run(game)
    assert rc == 0
    assert "可以玩" in out
    assert "[!!]" not in out


def test_missing_agent_line_is_actionable(tmp_path):
    game = make_game(tmp_path, with_agent=False)
    rc, out = run(game)
    assert rc == 1
    assert "setup-agent.bat" in out


def test_missing_mod_files_are_reported(tmp_path):
    game = make_game(tmp_path, with_jar=False)
    rc, out = run(game)
    assert rc == 1
    assert "缺文件" in out


def test_mixinfr_route_does_not_call_texture_patch_a_failure(tmp_path):
    """Route A never gets the texture patch; that must read as normal."""
    game = make_game(tmp_path, route="a", agent_log=(
        "hypernova agent premain\n"
        "scripts cache transformer registered\n"
        "textures: unsupported GraphicsLib TextureData (sha256=abc)\n"
        "file index: disabled for FR version 0.9.5 (unsupported)\n"
    ), game_log=MENU_LOG)
    (game / "mods/MixinFR").mkdir(parents=True)
    rc, out = run(game)
    assert rc == 0, out
    assert "MixinFR 的正常现象" in out
    assert "[!!]" not in out


def test_agent_log_without_premain_reports_failure(tmp_path):
    game = make_game(tmp_path, agent_log="something else entirely\n", game_log=MENU_LOG)
    rc, out = run(game)
    assert rc == 1
    assert "没加载" in out


def test_out_of_memory_is_named(tmp_path):
    game = make_game(tmp_path, agent_log=GOOD_AGENT_LOG,
                     game_log="java.lang.OutOfMemoryError: Java heap space\n")
    rc, out = run(game)
    assert rc == 1
    assert "内存不够" in out


def test_no_logs_yet_is_a_reminder_not_a_failure(tmp_path):
    game = make_game(tmp_path)
    rc, out = run(game)
    assert rc == 0, out
    assert "先启动一次游戏" in out


def test_only_last_session_is_examined(tmp_path):
    """An old session that worked must not mask a broken current one."""
    log = ("hypernova agent premain\nscripts cache transformer registered\n"
           "textures: patched x\n" + "noise\n" * 10)
    game = make_game(tmp_path, agent_log=log, game_log=MENU_LOG)
    # append a session whose premain never registered anything useful
    p = game / "saves/hypernova/scripts-agent.log"
    p.write_text(log + "hypernova agent premain\n", encoding="utf-8")
    rc, out = run(game)
    assert "脚本缓存没接管" in out


def test_route_detection_shared_with_installer(tmp_path):
    """The checker and the installer must agree on which route a file is."""
    game = make_game(tmp_path, route="a")
    found = cs.find_launch(game)
    assert found is not None
    route, path = found
    assert route == sa.ROUTE_A and path.name == "vmparams"
