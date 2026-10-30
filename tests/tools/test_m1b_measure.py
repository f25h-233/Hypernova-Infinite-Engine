import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def write_log(path, normals_before, normals_after):
    lines = []
    t = 1000
    lines.append(f"{t} [main] INFO  com.genir.renderer.agent.Agent  - Fast Rendering: v0.9.5")
    for i in range(normals_before):
        t += 10
        lines.append(f"{t} [Thread-3] INFO  com.fs.graphics.TextureLoader  - Loading image [cache/x{i}_normal.png]")
    t += 1000
    lines.append(f"{t} [Thread-21] INFO  sound.H  - Playing music with id [miscallenous_main_menu.ogg]")
    for i in range(normals_after):
        t += 10
        lines.append(f"{t} [Thread-3] INFO  com.fs.graphics.TextureLoader  - Loading image [cache/y{i}_normal.png]")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_counts_only_before_menu_and_requires_patch(tmp_path):
    log = tmp_path / "starsector.log"
    agent = tmp_path / "agent.log"
    write_log(log, 10, 2)
    agent.write_text("2026-01-01T00:00:00Z INFO textures: patched org/dark/shaders/util/TextureData\n",
                     encoding="utf-8")
    out = tmp_path / "out.json"
    r = subprocess.run([sys.executable, str(ROOT / "tools/m1b_measure.py"),
                        "--log", str(log), "--agent-log", str(agent),
                        "--baseline", "100", "--json-out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["normal_before_menu"] == 10
    assert d["normal_after_menu"] == 2
    assert d["patched"] is True
    assert d["gate_ok"] is True


def test_gate_fails_without_patch(tmp_path):
    log = tmp_path / "starsector.log"
    write_log(log, 0, 0)
    r = subprocess.run([sys.executable, str(ROOT / "tools/m1b_measure.py"),
                        "--log", str(log), "--baseline", "100"],
                       capture_output=True, text=True)
    assert r.returncode == 1


def test_gate_fails_when_too_many_normals_before_menu(tmp_path):
    log = tmp_path / "starsector.log"
    agent = tmp_path / "agent.log"
    write_log(log, 60, 0)
    agent.write_text("textures: patched org/dark/shaders/util/TextureData\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "tools/m1b_measure.py"),
                        "--log", str(log), "--agent-log", str(agent),
                        "--baseline", "100"],
                       capture_output=True, text=True)
    assert r.returncode == 1
