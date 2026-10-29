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
