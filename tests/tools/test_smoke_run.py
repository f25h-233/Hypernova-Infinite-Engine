import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
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
