import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("m1e_rounds", REPO / "tools" / "m1e_rounds.py")
rounds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rounds)

PURGE = REPO / "tools" / "clear_standby.ps1"


def test_build_smoke_command_includes_profile_jvm_args_and_json():
    cmd = rounds.build_smoke_command(
        "miko-lite", Path("build/out.json"), ["-Dhypernova.textures=false"])
    assert cmd[:3] == [sys.executable, "-I", str(REPO / "tools" / "smoke_run.py")]
    assert cmd[cmd.index("--profile") + 1] == "miko-lite"
    assert cmd[cmd.index("--json-out") + 1] == str(Path("build/out.json"))
    # argparse treats "-D..." as an option; use the --opt=value form.
    assert "--jvm-arg=-Dhypernova.textures=false" in cmd


def test_parse_key_ms():
    line = "2026-10-31T00:00:00Z INFO cache key ready (background): abc, took 458 ms"
    assert rounds.parse_key_ms(line) == 458
    assert rounds.parse_key_ms("") is None
    assert rounds.parse_key_ms("no timing here") is None


def test_summarize_medians_and_ok_count():
    rows = [
        {"ok": True, "menu_s": 80.0, "read_bytes_menu": 100,
         "agent": {"key_ready": "took 500 ms"}},
        {"ok": True, "menu_s": 90.0, "read_bytes_menu": 300,
         "agent": {"key_ready": "took 700 ms"}},
        {"ok": False},
    ]
    summary = rounds.summarize(rows)
    assert summary["rounds"] == 3
    assert summary["ok_rounds"] == 2
    assert summary["menu_s"] == {"n": 2, "median": 85.0, "min": 80.0, "max": 90.0}
    assert summary["read_bytes_menu"]["max"] == 300
    assert summary["key_ms"]["median"] == 600.0


def test_summarize_empty():
    summary = rounds.summarize([])
    assert summary["ok_rounds"] == 0
    assert summary["menu_s"] is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_purge_script_reports_not_elevated_in_this_shell():
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PURGE)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    out = (r.stdout or "") + (r.stderr or "")
    # "ELEVATED" is a substring of "NOT_ELEVATED"; skip only on a real
    # elevated run, where the script prints ELEVATED/PURGED and not NOT_ELEVATED.
    if "ELEVATED" in out and "NOT_ELEVATED" not in out:
        pytest.skip("this shell is elevated")
    assert r.returncode == 3
    assert "NOT_ELEVATED" in out


def test_purge_script_contract():
    text = PURGE.read_text(encoding="utf-8")
    assert "NtSetSystemInformation" in text
    assert "SeProfileSingleProcessPrivilege" in text
    assert "MemoryPurgeStandbyList" in text
    assert "NOT_ELEVATED" in text
