import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools"
_spec = importlib.util.spec_from_file_location(
    "m4_session_report", TOOLS / "m4_session_report.py")
report_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report_mod)

FRAME = ("HYPERNOVA_FRAME frames=600 over200=2 maxMs=250 p99Ms=16 "
         "lastMs=12 longGaps=1")
SUMMARY = ("lazy probe: summary queue=1 wouldSkip=0 lookups=5 demand=1 "
           "index=10 types={} queuedSkip=0 demandQueued=0 hits=1 misses=0 "
           "degraded=0 skipped=0 proxies=1 materialized=1 deferred=0 pending=0 "
           "drained=1 reregistered=0 failed=0 disabled=0 main=main loading=none "
           "lateRegistered=0 lateLoaded=0 dimMismatch=0 dds=1 ddsHit=1 "
           "ddsFallback=0 ddsDisabled=0 ddsDimMismatch=0 eviction=1 evicted=0 "
           "rematerialized=0 evictPasses=0 liveBytes=100 startupBytes=10 "
           "foreignBytes=20 evictableBytes=70 budgetBytes=1024 "
           "emptyEvictPasses=0 evictPassMsTotal=0 evictPassMsMax=0 "
           "placeholder=1 oldIdDeleted=0 evictSkipped=0 deferredDeletes=0 "
           "selftest=0 failedParked=0 sceneUnload=0 scenePasses=0 "
           "sceneEvictions=0 sceneEvictMsTotal=0 sceneEvictMsMax=0 scenePending=0")


def test_frame_probe_uses_last_line():
    text = FRAME + "\n" + FRAME.replace("over200=2", "over200=9") + "\n"
    parsed = report_mod.find_frame_probe(text)
    assert parsed["present"] is True
    assert parsed["over200"] == 9
    assert parsed["line"] == 2
    assert parsed["missing_keys"] == []


def test_frame_probe_absent():
    parsed = report_mod.find_frame_probe("no probe here\n")
    assert parsed["present"] is False
    assert "frames" in parsed["missing_keys"]


def test_lazy_summary_only_after_last_anchor():
    text = ("hypernova agent premain\n" + SUMMARY + "\n"
            "hypernova agent premain\n"
            + SUMMARY.replace("disabled=0", "disabled=1") + "\n")
    parsed = report_mod.find_lazy_summary(text)
    assert parsed["present"] is True
    assert parsed["summary"]["disabled"] == 1
    assert parsed["anchor_count"] == 2


def test_lazy_summary_missing_anchor_fails_closed():
    parsed = report_mod.find_lazy_summary(SUMMARY + "\n")
    assert parsed["present"] is False
    assert "anchor" in parsed["reason"]


def test_build_report_combines_sections():
    starsector = ("Fast Rendering: v0.9.7rc2\n" + FRAME + "\n"
                  "Failed to load texture x\n")
    report = report_mod.build_report(
        "hypernova agent premain\n" + SUMMARY + "\n", starsector)
    assert report["frame_probe"]["present"] is True
    assert report["lazy"]["present"] is True
    assert report["texture_errors_total"] == 1
    assert report["health"]["texture_errors_zero"] is False
    assert report["health"]["lazy_failed_zero"] is True


def test_texture_errors_before_last_session_anchor_are_ignored():
    starsector = ("Failed to load texture old\n"
                  "Fast Rendering: v0.9.7rc2\n" + FRAME + "\n")
    report = report_mod.build_report(
        "hypernova agent premain\n" + SUMMARY + "\n", starsector)
    assert report["texture_errors_total"] == 0


def _write_session(tmp_path, starsector):
    agent = tmp_path / "agent.log"
    agent.write_text("hypernova agent premain\n" + SUMMARY + "\n", encoding="utf-8")
    log = tmp_path / "starsector.log"
    log.write_text(starsector, encoding="utf-8")
    return agent, log


def test_strict_requires_frame_probe(tmp_path):
    agent, log = _write_session(tmp_path, "Fast Rendering: v0.9.7rc2\nno frame\n")
    out = tmp_path / "report.json"
    rc = report_mod.main(["--agent-log", str(agent), "--starsector-log", str(log),
                          "--out", str(out), "--strict"])
    assert rc == 1
    assert json.loads(out.read_text(encoding="utf-8"))["frame_probe"]["present"] is False


def test_require_frame_pass(tmp_path):
    agent, log = _write_session(tmp_path, "Fast Rendering: v0.9.7rc2\n" + FRAME + "\n")
    out = tmp_path / "report.json"
    assert report_mod.main(["--agent-log", str(agent), "--starsector-log", str(log),
                            "--out", str(out), "--require-frame"]) == 0


def test_gpu_csv_without_samples_is_rc2(tmp_path):
    agent, log = _write_session(tmp_path, "Fast Rendering: v0.9.7rc2\n" + FRAME + "\n")
    gpu = tmp_path / "gpu.csv"
    gpu.write_text("timestamp,dedicated_mb,shared_mb\n", encoding="utf-8")
    assert report_mod.main(["--agent-log", str(agent), "--starsector-log", str(log),
                            "--gpu-csv", str(gpu)]) == 2


def test_script_runs_under_isolated_mode():
    proc = subprocess.run(
        [sys.executable, "-I", str(TOOLS / "m4_session_report.py"), "--help"],
        capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert "m4_session_report" in proc.stdout or "usage" in proc.stdout.lower()
