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


def run_measure(tmp_path, log_text):
    log = tmp_path / "starsector.log"
    log.write_text(log_text, encoding="utf-8")
    out = tmp_path / "out.json"
    r = subprocess.run([sys.executable, str(ROOT / "tools/m1b_measure.py"),
                        "--log", str(log), "--baseline", "100",
                        "--json-out", str(out)],
                       capture_output=True, text=True)
    return r, json.loads(out.read_text(encoding="utf-8"))


def normal_line(t, name):
    return (f"{t} [Thread-3] INFO  com.fs.graphics.TextureLoader  - "
            f"Loading image [cache/{name}_normal.png]")


def menu_line(t):
    return (f"{t} [Thread-21] INFO  sound.H  - "
            f"Playing music with id [miscallenous_main_menu.ogg]")


def test_small_timestamp_dip_does_not_split(tmp_path):
    # 多线程日志会有 1–2 ms 的倒序；它不能把会话切成两半、丢掉法线计数。
    log_text = "\n".join([
        "1000 [main] INFO  com.genir.renderer.agent.Agent  - "
        "Fast Rendering: v0.9.5",
        normal_line(1010, "a"),
        normal_line(1020, "b"),
        normal_line(1019, "c"),   # 1 ms 倒序
        menu_line(1030),
        normal_line(1040, "d"),
    ]) + "\n"
    _, d = run_measure(tmp_path, log_text)
    assert d["normal_before_menu"] == 3, d
    assert d["normal_after_menu"] == 1, d
    assert d["session_source"] == "anchor"
    assert d["menu_s"] == 1.0


def test_later_rollover_beats_stale_anchor(tmp_path):
    # 旧会话有 FR 锚点；新会话没有锚点、时间戳重置。必须测量新会话。
    log_text = "\n".join([
        "1000 [main] INFO  com.genir.renderer.agent.Agent  - "
        "Fast Rendering: v0.9.5",
        normal_line(1010, "old0"),
        normal_line(2000, "old1"),
        menu_line(3000),
        normal_line(100, "new0"),
        normal_line(110, "new1"),
        menu_line(500),
    ]) + "\n"
    _, d = run_measure(tmp_path, log_text)
    assert d["normal_before_menu"] == 2, d
    assert d["menu_s"] == 0.5
    assert d["session_source"] == "rollover"


def test_session_source_values(tmp_path):
    # anchor：有 FR 锚点
    anchor_log = "\n".join([
        "1000 [main] INFO  com.genir.renderer.agent.Agent  - "
        "Fast Rendering: v0.9.5",
        normal_line(1010, "a"),
        menu_line(1100),
    ]) + "\n"
    _, d = run_measure(tmp_path, anchor_log)
    assert d["session_source"] == "anchor", d

    # rollover：无锚点，时间戳从 5000 回到 1000（>1 s）
    rollover_log = "\n".join([
        normal_line(5000, "old"),
        menu_line(6000),
        normal_line(1000, "new"),
        menu_line(2000),
    ]) + "\n"
    _, d = run_measure(tmp_path, rollover_log)
    assert d["session_source"] == "rollover", d

    # whole：无锚点、无 >1 s 回退，整份文件就是一个会话
    whole_log = "\n".join([
        normal_line(1000, "a"),
        menu_line(1100),
    ]) + "\n"
    _, d = run_measure(tmp_path, whole_log)
    assert d["session_source"] == "whole", d
    assert d["normal_before_menu"] == 1, d


def write_nofr_log(path, normals_before, normals_after, failures=0, old_fr_session=True):
    lines = []
    if old_fr_session:
        lines.append("100000 [main] INFO  com.genir.renderer.agent.Agent  - Fast Rendering: v0.9.5")
        lines.append("100010 [Thread-3] INFO  com.fs.graphics.TextureLoader  - "
                     "Loading image [cache/old_normal.png]")
    t = 0
    for i in range(failures):
        t += 1
        lines.append(f"{t} [Thread-3] ERROR com.fs.graphics.TextureLoader  - "
                     f"Failed to load texture [broken{i}]")
    for i in range(normals_before):
        t += 10
        lines.append(f"{t} [Thread-3] INFO  com.fs.graphics.TextureLoader  - "
                     f"Loading image [cache/x{i}_normal.png]")
    t += 1000
    lines.append(f"{t} [Thread-21] INFO  sound.H  - "
                 "Playing music with id [miscallenous_main_menu.ogg]")
    for i in range(normals_after):
        t += 10
        lines.append(f"{t} [Thread-3] INFO  com.fs.graphics.TextureLoader  - "
                     f"Loading image [cache/y{i}_normal.png]")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


NOFR_AGENT = (
    "2026-01-01T00:00:00Z INFO hypernova agent premain; config=x\n"
    "2026-01-01T00:00:01Z INFO FR missing; scripts cache disabled\n"
    "2026-01-01T00:00:02Z INFO textures: patched org/dark/shaders/util/TextureData\n"
)


def _run_measure(log, agent, out, *extra):
    return subprocess.run(
        [sys.executable, str(ROOT / "tools/m1b_measure.py"),
         "--log", str(log), "--agent-log", str(agent),
         "--baseline", "100", "--json-out", str(out), *extra],
        capture_output=True, text=True)


def test_nofr_session_selected_by_rollover_and_gate_passes(tmp_path):
    log = tmp_path / "starsector.log"
    agent = tmp_path / "agent.log"
    out = tmp_path / "out.json"
    write_nofr_log(log, 0, 2)
    agent.write_text(NOFR_AGENT, encoding="utf-8")

    r = _run_measure(log, agent, out, "--expect-no-fr")
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["session_source"] == "rollover"
    assert d["fr_present"] is False
    assert d["fr_missing_disabled"] is True
    assert d["failed_texture_lines"] == 0
    assert d["gate_ok"] is True


def test_expect_no_fr_fails_when_fr_anchor_present(tmp_path):
    log = tmp_path / "starsector.log"
    agent = tmp_path / "agent.log"
    out = tmp_path / "out.json"
    write_log(log, 0, 0)
    agent.write_text(NOFR_AGENT, encoding="utf-8")

    r = _run_measure(log, agent, out, "--expect-no-fr")
    assert r.returncode == 1
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["fr_present"] is True
    assert d["gate_ok"] is False


def test_expect_no_fr_requires_agent_fr_missing_line(tmp_path):
    log = tmp_path / "starsector.log"
    agent = tmp_path / "agent.log"
    out = tmp_path / "out.json"
    write_nofr_log(log, 0, 0)
    agent.write_text(
        "2026-01-01T00:00:00Z INFO hypernova agent premain; config=x\n"
        "2026-01-01T00:00:02Z INFO textures: patched org/dark/shaders/util/TextureData\n",
        encoding="utf-8")

    r = _run_measure(log, agent, out, "--expect-no-fr")
    assert r.returncode == 1
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["fr_missing_disabled"] is False
    assert d["gate_ok"] is False


def test_expect_no_fr_fails_on_failed_texture(tmp_path):
    log = tmp_path / "starsector.log"
    agent = tmp_path / "agent.log"
    out = tmp_path / "out.json"
    write_nofr_log(log, 0, 0, failures=1)
    agent.write_text(NOFR_AGENT, encoding="utf-8")

    r = _run_measure(log, agent, out, "--expect-no-fr")
    assert r.returncode == 1
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["failed_texture_lines"] == 1
    assert d["gate_ok"] is False


def write_cleaned_nofr_log(path, cleaned_before, cleaned_after, loading_before=0):
    lines = []
    t = 0
    for i in range(cleaned_before):
        t += 10
        lines.append(f"{t} [main] INFO  com.fs.graphics.TextureLoader  - "
                     f"Cleaned buffer for texture cache/c{i}_normal.png (using reflection)")
    for i in range(loading_before):
        t += 1
        lines.append(normal_line(t, f"l{i}"))
    t += 1000
    lines.append(menu_line(t))
    for i in range(cleaned_after):
        t += 10
        lines.append(f"{t} [main] INFO  com.fs.graphics.TextureLoader  - "
                     f"Cleaned buffer for texture cache/d{i}_normal.png (using reflection)")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_cleaned_metric_counts_cleaned_lines(tmp_path):
    log = tmp_path / "starsector.log"
    agent = tmp_path / "agent.log"
    out = tmp_path / "out.json"
    write_cleaned_nofr_log(log, 40, 2, loading_before=5)
    agent.write_text(NOFR_AGENT, encoding="utf-8")

    r = _run_measure(log, agent, out, "--normal-metric", "cleaned")
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["normal_metric"] == "cleaned"
    assert d["normal_before_menu"] == 40
    assert d["normal_after_menu"] == 2
    assert d["loading_normal_before_menu"] == 5
    assert d["loading_normal_after_menu"] == 0
    assert d["gate_ok"] is True


def test_expect_no_fr_defaults_to_cleaned_metric(tmp_path):
    log = tmp_path / "starsector.log"
    agent = tmp_path / "agent.log"
    out = tmp_path / "out.json"
    write_cleaned_nofr_log(log, 10, 0)
    agent.write_text(NOFR_AGENT, encoding="utf-8")

    r = _run_measure(log, agent, out, "--expect-no-fr")
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["normal_metric"] == "cleaned"
    assert d["normal_before_menu"] == 10
    assert d["loading_normal_before_menu"] == 0


def test_default_metric_is_loading(tmp_path):
    log = tmp_path / "starsector.log"
    agent = tmp_path / "agent.log"
    out = tmp_path / "out.json"
    write_cleaned_nofr_log(log, 30, 0, loading_before=4)
    agent.write_text(NOFR_AGENT, encoding="utf-8")

    r = _run_measure(log, agent, out)
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["normal_metric"] == "loading"
    assert d["normal_before_menu"] == 4
    assert d["normal_after_menu"] == 0


def test_normal_metric_rejects_unknown_value(tmp_path):
    log = tmp_path / "starsector.log"
    agent = tmp_path / "no-agent.log"
    out = tmp_path / "out.json"
    write_log(log, 0, 0)

    r = _run_measure(log, agent, out, "--normal-metric", "bogus")
    assert r.returncode == 2


def test_cleaned_metric_counts_whitespace_filenames(tmp_path):
    # I-1: cache-normal filenames may contain spaces. The cache/ scope must
    # still exclude source-texture graphics/..._normal.png cleans.
    log = tmp_path / "starsector.log"
    agent = tmp_path / "agent.log"
    out = tmp_path / "out.json"
    lines = []
    t = 0
    for name in ("cache/M_energy level___SHIP_normal.png",
                 "cache/flame sp___TURRET0_normal.png",
                 "graphics/shaders/normal/ships/shuttle_normal.png"):
        t += 10
        lines.append(f"{t} [main] INFO  com.fs.graphics.TextureLoader  - "
                     f"Cleaned buffer for texture {name} (using reflection)")
    t += 1000
    lines.append(menu_line(t))
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    agent.write_text(NOFR_AGENT, encoding="utf-8")

    r = _run_measure(log, agent, out, "--normal-metric", "cleaned")
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["normal_before_menu"] == 2
    assert d["gate_ok"] is True
