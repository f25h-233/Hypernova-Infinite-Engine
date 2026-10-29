import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import install_agent as ia

FR = "-javaagent:fr.agent.jar\n"


def test_patch_inserts_after_fr_and_is_idempotent():
    lines = ["-Xmx10g\n", FR, "-classpath\n"]
    out = ia.patch_lines(lines)
    assert out[2] == ia.AGENT_LINE + "\n"
    assert out[0] == "-Xmx10g\n" and out[1] == FR and out[3] == "-classpath\n"
    assert ia.patch_lines(out) == out


def test_patch_without_fr_fails():
    with pytest.raises(SystemExit):
        ia.patch_lines(["-Xmx10g\n", "-classpath\n"])


def test_unpatch_removes_only_agent():
    lines = ["-Xmx10g\n", FR, ia.AGENT_LINE + "\n", "-classpath\n"]
    assert ia.unpatch_lines(lines) == ["-Xmx10g\n", FR, "-classpath\n"]


def test_toggle_is_reversible():
    lines = ["-Xmx10g\n", FR, "-classpath\n"]
    assert ia.unpatch_lines(ia.patch_lines(lines)) == lines


# ---- P1 防御：主类之后的内容会被 JVM 当作程序参数，agent 会静默不加载 ----


def test_agent_line_never_after_main_class():
    # 真实 fr.vmparams 的末行（主类）没有行尾换行。
    lines = ["-Xmx10g\n", FR, "-classpath\n", ia.MAIN_CLASS]
    out = ia.patch_lines(lines)
    assert out[-1] == ia.MAIN_CLASS
    assert out.index(ia.AGENT_LINE + "\n") < out.index(ia.MAIN_CLASS)


def test_patch_refuses_agent_after_main_class():
    # FR 行错放在主类之后时，插在 FR 后的 agent 行也会落在主类之后 -> 必须拒绝。
    lines = [ia.MAIN_CLASS + "\n", FR]
    with pytest.raises(SystemExit) as excinfo:
        ia.patch_lines(lines)
    assert ia.AGENT_LINE in str(excinfo.value)


# ---- F-1：launch 文件已打过补丁时，install 仍须刷新游戏目录里的 agent jar ----

INSTALLER = Path(__file__).resolve().parents[2] / "tools" / "install_agent.py"


def _run_cli(*args: str) -> int:
    # 走真实 CLI 入口：main() 不接受 argv 参数，且这样连 argparse 接线一起覆盖。
    return subprocess.run([sys.executable, "-I", str(INSTALLER), *args],
                          capture_output=True, text=True).returncode


def _fake_game(tmp_path):
    game = tmp_path / "game"
    (game / "starsector-core").mkdir(parents=True)
    launch = game / "starsector-core" / "fr.vmparams"
    launch.write_text("-Xmx10g\n" + FR + "-classpath\n" + ia.MAIN_CLASS, encoding="utf-8")
    return game, launch


def test_reinstall_updates_agent_jar(tmp_path):
    game, launch = _fake_game(tmp_path)
    installed = game / "mods/hypernova_infinite_engine/jars/hypernova.agent.jar"

    jar_v1 = tmp_path / "jar_v1.jar"
    jar_v1.write_bytes(b"V1")
    assert _run_cli("--game", str(game), "--env", "base", "--jar", str(jar_v1)) == 0
    assert installed.read_bytes() == b"V1"
    after_first = launch.read_bytes()

    # 第二次 install：launch 文件已是打过补丁的状态（行无变化），jar 仍必须更新。
    jar_v2 = tmp_path / "jar_v2.jar"
    jar_v2.write_bytes(b"V2")
    assert _run_cli("--game", str(game), "--env", "base", "--jar", str(jar_v2)) == 0
    assert installed.read_bytes() == b"V2"
    # 幂等仍然成立：launch 文件内容一字未变。
    assert launch.read_bytes() == after_first


def test_backupRefreshesOnEachInstall(tmp_path):
    game, launch = _fake_game(tmp_path)
    backup = launch.with_name(launch.name + ".bak-hypernova")
    jar = tmp_path / "agent.jar"
    jar.write_bytes(b"JAR")

    original = launch.read_text(encoding="utf-8")
    assert _run_cli("--game", str(game), "--env", "base", "--jar", str(jar)) == 0
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == original, "backup must hold pre-install bytes"

    # 用户手工再改一次启动文件；下一次 install 的备份必须反映这次的改动。
    edited = launch.read_text(encoding="utf-8").replace(
        "-Xmx10g\n", "-Xmx10g\n-Duser.edit=1\n")
    launch.write_text(edited, encoding="utf-8", newline="\n")

    assert _run_cli("--game", str(game), "--env", "base", "--jar", str(jar)) == 0
    assert backup.read_text(encoding="utf-8") == edited, "backup must refresh on every install"
    # 目标文件仍然只有一行 agent 行（幂等，没有叠加）。
    assert launch.read_text(encoding="utf-8").count(ia.AGENT_LINE) == 1


def test_backupCreatedEvenWhenAlreadyPatched(tmp_path):
    game, _ = _fake_game(tmp_path)
    # 预先放一个已含 agent 行、且没有任何备份的启动文件。
    launch = game / "starsector-core" / "fr.vmparams"
    pre = "-Xmx10g\n" + FR + ia.AGENT_LINE + "\n-classpath\n" + ia.MAIN_CLASS
    launch.write_text(pre, encoding="utf-8", newline="\n")
    backup = launch.with_name(launch.name + ".bak-hypernova")
    assert not backup.exists()

    jar = tmp_path / "agent.jar"
    jar.write_bytes(b"JAR")
    assert _run_cli("--game", str(game), "--env", "base", "--jar", str(jar)) == 0
    assert backup.exists(), "already-patched installs must still leave a backup"
    assert backup.read_text(encoding="utf-8") == pre


def test_dry_run_does_not_copy_agent_jar(tmp_path):
    game, launch = _fake_game(tmp_path)
    original = launch.read_text(encoding="utf-8")

    jar = tmp_path / "agent.jar"
    jar.write_bytes(b"JAR")
    assert _run_cli("--game", str(game), "--env", "base",
                    "--jar", str(jar), "--dry-run") == 0
    installed = game / "mods/hypernova_infinite_engine/jars/hypernova.agent.jar"
    assert not installed.exists()
    assert launch.read_text(encoding="utf-8") == original
