import argparse
import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
# pytest under `python -I` does not put the repo root on sys.path; the
# tools/ directory is not a package, so make `tools.smoke_run` importable.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
_spec = importlib.util.spec_from_file_location("smoke_run", REPO / "tools" / "smoke_run.py")
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)


def test_nofr_profile_points_at_generated_file():
    profile = smoke.PROFILES["miko-lite-nofr"]
    assert profile["game"] == "Starsector-098-260mods"
    assert profile["java"] == "jdk-28+13/bin/java.exe"
    assert profile["vmparams"] == "../Miko_Lite_nofr.txt"
    assert profile["cwd"] == "starsector-core"


def test_build_command_puts_jvm_args_before_argfile():
    cmd = smoke.build_command(
        "java.exe", "../Miko_Lite.txt",
        ["-DlaunchDirect=true"], ["-Dhypernova.textures=false"])
    assert cmd == [
        "java.exe",
        "-DlaunchDirect=true",
        "-Dhypernova.textures=false",
        "@../Miko_Lite.txt",
    ]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only I/O counters")
def test_io_read_bytes_for_own_process():
    value = smoke.io_read_bytes(os.getpid())
    assert value is not None
    assert value > 0


def test_session_anchor_accepts_097rc2(tmp_path):
    log = tmp_path / "starsector.log"
    old = b"1000 [main] INFO  com.genir.renderer.agent.Agent  - Fast Rendering: v0.9.5\n"
    new = b"2000 [main] INFO  com.genir.renderer.agent.Agent  - Fast Rendering: v0.9.7rc2\n"
    data = old + b"middle\n" + new
    log.write_bytes(data)
    assert smoke.session_offset(log) == data.rfind(smoke.SESSION_ANCHOR)
    assert smoke.session_offset(log) > len(old)


def test_miko_lite_phase_profile_uses_derived_file():
    from tools.smoke_run import PROFILES
    cfg = PROFILES["miko-lite-phase"]
    assert cfg["game"] == "Starsector-098-260mods"
    assert cfg["vmparams"] == "../Miko_Lite_phase.txt"
    assert cfg["cwd"] == "starsector-core"


def test_index_path_for_points_at_saves_index():
    game = Path("game-root")
    assert smoke.index_path_for(game) == game / "saves" / "hypernova" / "file-index.idx.gz"


def test_clear_index_removes_only_the_index(tmp_path):
    index = smoke.index_path_for(tmp_path)
    index.parent.mkdir(parents=True)
    index.write_bytes(b"x")
    keep = index.parent / "scripts-cache"
    keep.mkdir()
    (keep / "x").write_bytes(b"keep")
    assert smoke.clear_index(tmp_path) is True
    assert not index.exists()
    assert keep.exists()
    assert smoke.clear_index(tmp_path) is False


def _fake_profile(tmp_path, monkeypatch):
    game = tmp_path / "game"
    (game / "jre").mkdir(parents=True)
    (game / "jre" / "java").write_text("")
    (game / "starsector-core").mkdir()
    (game / "starsector-core" / "vm.txt").write_text("")
    monkeypatch.setattr(smoke, "ROOT", tmp_path)
    monkeypatch.setattr(smoke, "PROFILES", {"fake": {
        "game": "game", "java": "jre/java",
        "vmparams": "vm.txt", "cwd": "starsector-core"}})
    monkeypatch.setattr(smoke.time, "sleep", lambda seconds: None)
    return game


def _install_loop_spies(monkeypatch, events, real_clear):
    def spy_clear(game):
        events.append("clear")
        return real_clear(game)

    def fake_round(cfg, game, args):
        events.append("round")
        index = smoke.index_path_for(game)
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_bytes(b"x")  # simulate the build writing a fresh index
        return {"ok": True, "menu_s": 1.0, "wall_s": 1.0, "stop": "forced"}

    monkeypatch.setattr(smoke, "clear_index", spy_clear)
    monkeypatch.setattr(smoke, "one_round", fake_round)


def test_main_clears_the_index_before_every_round(tmp_path, monkeypatch):
    game = _fake_profile(tmp_path, monkeypatch)
    events = []
    _install_loop_spies(monkeypatch, events, smoke.clear_index)
    monkeypatch.setattr(sys, "argv", ["smoke_run.py", "--profile", "fake",
                                      "--rounds", "3", "--clear-index-each-round"])
    assert smoke.main() == 0
    assert events == ["clear", "round", "clear", "round", "clear", "round"], events


def test_main_leaves_the_index_alone_without_the_flag(tmp_path, monkeypatch):
    game = _fake_profile(tmp_path, monkeypatch)
    events = []
    _install_loop_spies(monkeypatch, events, smoke.clear_index)
    monkeypatch.setattr(sys, "argv", ["smoke_run.py", "--profile", "fake",
                                      "--rounds", "2"])
    assert smoke.main() == 0
    assert events == ["round", "round"], events


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only process memory")
def test_process_memory_reads_self():
    value = smoke.process_memory_mb(os.getpid())
    assert value is not None
    assert value > 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only process memory")
def test_process_private_reads_self():
    value = smoke.process_private_mb(os.getpid())
    assert value is not None
    assert value > 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only physical memory")
def test_free_physical_mb_reads_self():
    value = smoke.free_physical_mb()
    assert value is not None
    assert value > 0


def test_gpu_memory_mb_returns_none_without_command(monkeypatch):
    def boom(*args, **kwargs):
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr(smoke.subprocess, "run", boom)
    assert smoke.gpu_memory_mb() is None


def test_gpu_memory_mb_sums_devices(monkeypatch):
    class Result:
        returncode = 0
        stdout = "1024\n512\n"

    monkeypatch.setattr(smoke.subprocess, "run", lambda *a, **k: Result())
    assert smoke.gpu_memory_mb() == 1536.0


def test_one_round_records_memory_samples(tmp_path, monkeypatch):
    game = tmp_path / "game"
    (game / "starsector-core").mkdir(parents=True)
    cfg = {"java": "jre/java", "vmparams": "vm.txt", "cwd": "starsector-core"}

    class FakeProc:
        pid = 424242

    monkeypatch.setattr(smoke.subprocess, "Popen", lambda *a, **k: FakeProc())
    monkeypatch.setattr(smoke, "wait_for_menu", lambda *a, **k: 12.5)
    monkeypatch.setattr(smoke, "io_read_bytes", lambda pid: 7)
    monkeypatch.setattr(smoke, "process_memory_mb", lambda pid: 1234.56)
    monkeypatch.setattr(smoke, "process_private_mb", lambda pid: 2345.67)
    monkeypatch.setattr(smoke, "gpu_memory_mb", lambda: 4096.0)
    monkeypatch.setattr(smoke, "process_gpu_memory_mb", lambda pid: (3500.0, 100.0))
    monkeypatch.setattr(smoke, "free_physical_mb", lambda: 15000.0)
    monkeypatch.setattr(smoke, "graceful_stop", lambda proc: "forced")
    monkeypatch.setattr(smoke.time, "sleep", lambda seconds: None)

    args = argparse.Namespace(start_res="1707x1067", fullscreen=False,
                              jvm_arg=[], wait_menu=1, linger=0)
    row = smoke.one_round(cfg, game, args)
    assert row["ok"] is True
    assert row["ws_menu_mb"] == 1234.6
    assert row["ws_exit_mb"] == 1234.6
    assert row["private_menu_mb"] == 2345.7
    assert row["private_exit_mb"] == 2345.7
    assert row["gpu_menu_mb"] == 4096.0
    assert row["gpu_process_dedicated_mb"] == 3500.0
    assert row["gpu_process_shared_mb"] == 100.0
    assert row["gpu_process_dedicated_exit_mb"] == 3500.0
    assert row["gpu_process_shared_exit_mb"] == 100.0
    assert row["free_mb_menu"] == 15000.0
    assert row["free_mb_exit"] == 15000.0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only GPU counters")
def test_process_gpu_memory_parses_wmi_output(monkeypatch):
    class R:
        returncode = 0
        stdout = "1048576 524288\n"

    monkeypatch.setattr(smoke.subprocess, "run", lambda *a, **k: R())
    assert smoke.process_gpu_memory_mb(1234) == (1.0, 0.5)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only GPU counters")
def test_process_gpu_memory_empty_or_error(monkeypatch):
    class Empty:
        returncode = 0
        stdout = ""

    monkeypatch.setattr(smoke.subprocess, "run", lambda *a, **k: Empty())
    assert smoke.process_gpu_memory_mb(1234) == (None, None)

    class Bad:
        returncode = 1
        stdout = "1 2"

    monkeypatch.setattr(smoke.subprocess, "run", lambda *a, **k: Bad())
    assert smoke.process_gpu_memory_mb(1234) == (None, None)
