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
    agent.write_text(
        "2026-01-01T00:00:00Z INFO hypernova agent premain; config=x\n"
        "2026-01-01T00:00:00Z INFO textures: patched org/dark/shaders/util/TextureData\n",
        encoding="utf-8",
    )
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
    out = tmp_path / "out.json"
    r = subprocess.run([sys.executable, str(ROOT / "tools/m1b_measure.py"),
                        "--log", str(log), "--baseline", "100",
                        "--json-out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 1
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["gate_ok"] is False


def test_gate_fails_when_too_many_normals_before_menu(tmp_path):
    log = tmp_path / "starsector.log"
    agent = tmp_path / "agent.log"
    write_log(log, 60, 0)
    agent.write_text(
        "2026-01-01T00:00:00Z INFO hypernova agent premain; config=x\n"
        "textures: patched org/dark/shaders/util/TextureData\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    r = subprocess.run([sys.executable, str(ROOT / "tools/m1b_measure.py"),
                        "--log", str(log), "--agent-log", str(agent),
                        "--baseline", "100", "--json-out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 1
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["gate_ok"] is False


def test_agent_log_is_scoped_to_last_session(tmp_path):
    log = tmp_path / "starsector.log"
    agent = tmp_path / "agent.log"
    write_log(log, 0, 0)
    agent.write_text(
        "2026-01-01T00:00:00Z INFO hypernova agent premain; config=x\n"
        "2026-01-01T00:00:01Z INFO textures: patched org/dark/shaders/util/TextureData\n"
        "2026-01-02T00:00:00Z INFO hypernova agent premain; config=y\n"
        "2026-01-02T00:00:01Z INFO textures normal-cache disabled by config\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    r = subprocess.run([sys.executable, str(ROOT / "tools/m1b_measure.py"),
                        "--log", str(log), "--agent-log", str(agent),
                        "--baseline", "100", "--json-out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 1
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["patched"] is False
    assert d["gate_ok"] is False


def test_uses_only_the_last_game_session(tmp_path):
    log = tmp_path / "starsector.log"
    agent = tmp_path / "agent.log"
    lines = ["1000 [main] INFO  com.genir.renderer.agent.Agent  - Fast Rendering: v0.9.5"]
    for i in range(5):
        lines.append(f"{1010 + i} [Thread-3] INFO  com.fs.graphics.TextureLoader  - "
                     f"Loading image [cache/old{i}_normal.png]")
    lines.append("2000 [main] INFO  com.genir.renderer.agent.Agent  - Fast Rendering: v0.9.5")
    lines.append("2010 [Thread-3] INFO  com.fs.graphics.TextureLoader  - "
                 "Loading image [cache/new0_normal.png]")
    lines.append("3000 [Thread-21] INFO  sound.H  - "
                 "Playing music with id [miscallenous_main_menu.ogg]")
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    agent.write_text(
        "2026-01-01T00:00:00Z INFO hypernova agent premain; config=x\n"
        "2026-01-01T00:00:01Z INFO textures: patched org/dark/shaders/util/TextureData\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    r = subprocess.run([sys.executable, str(ROOT / "tools/m1b_measure.py"),
                        "--log", str(log), "--agent-log", str(agent),
                        "--baseline", "100", "--json-out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["normal_before_menu"] == 1


def test_max_normal_cap_rejects_partial_patch(tmp_path):
    log = tmp_path / "starsector.log"
    agent = tmp_path / "agent.log"
    write_log(log, 100, 0)
    agent.write_text(
        "2026-01-01T00:00:00Z INFO hypernova agent premain; config=x\n"
        "textures: patched org/dark/shaders/util/TextureData\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    r = subprocess.run([sys.executable, str(ROOT / "tools/m1b_measure.py"),
                        "--log", str(log), "--agent-log", str(agent),
                        "--baseline", "10000", "--max-normal", "50",
                        "--json-out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 1
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["normal_before_menu"] == 100
    assert d["gate_ok"] is False


def test_uses_timestamp_rollover_when_anchor_missing(tmp_path):
    log = tmp_path / "starsector.log"
    lines = []
    for i in range(5):
        lines.append(f"{5010 + i} [Thread-3] INFO  com.fs.graphics.TextureLoader  - "
                     f"Loading image [cache/first{i}_normal.png]")
    lines.append("6000 [Thread-21] INFO  sound.H  - "
                 "Playing music with id [miscallenous_main_menu.ogg]")
    lines.append("1000 [Thread-3] INFO  com.fs.graphics.TextureLoader  - "
                 "Loading image [cache/second0_normal.png]")
    lines.append("2000 [Thread-21] INFO  sound.H  - "
                 "Playing music with id [miscallenous_main_menu.ogg]")
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = tmp_path / "out.json"
    r = subprocess.run([sys.executable, str(ROOT / "tools/m1b_measure.py"),
                        "--log", str(log), "--baseline", "100",
                        "--json-out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 1
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["normal_before_menu"] == 1
    assert d["menu_s"] is not None
    assert d["gate_ok"] is False


def test_no_session_anchor_fails_closed(tmp_path):
    # 既无 FR 锚点，也无毫秒时间戳：没有会话信息，必须失败关闭。
    log = tmp_path / "starsector.log"
    log.write_text(
        "INFO  sound.H  - Playing music with id [miscallenous_main_menu.ogg]\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    r = subprocess.run([sys.executable, str(ROOT / "tools/m1b_measure.py"),
                        "--log", str(log), "--baseline", "100",
                        "--json-out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 1
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["gate_ok"] is False
    assert d["menu_s"] is None
