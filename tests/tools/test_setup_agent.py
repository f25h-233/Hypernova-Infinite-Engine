"""Tests for the player-facing agent installer.

The rule that matters and is easy to get backwards:

* route B (plain FR, Miko argfile): Hypernova **before** ``fr.agent.jar``
* route A (MixinFR, single-line vmparams): Hypernova **after** the bridge

A previous revision had route A inverted. Inverting it does not crash — the
game starts and the agent loads — so only a test (or a log check) catches it.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "player-tools"))

import setup_agent as sa  # noqa: E402


BS = "\\"
MIXIN = f"-javaagent:..{BS}mods{BS}MixinFR{BS}jars{BS}MixinLib-bridge.jar"
AGENT = "-javaagent:../mods/hypernova_infinite_engine/jars/hypernova.agent.jar"
MAIN = "com.fs.starfarer.StarfarerLauncher"


def vmparams(*, with_agent=False, agent_first=False):
    tokens = ["java.exe", "-Xmx4096m", "-Djava.library.path=native" + BS + "windows", "-classpath", "a.jar;b.jar"]
    if with_agent and agent_first:
        tokens.append(AGENT)
    tokens.append(MIXIN)
    if with_agent and not agent_first:
        tokens.append(AGENT)
    tokens.append(MAIN)
    return " ".join(tokens)


def miko(*, with_agent=False, agent_after=False):
    lines = ["-Xmx4096m", "-Xss4m"]
    if with_agent and not agent_after:
        lines.append(AGENT)
    lines.append("-javaagent:fr.agent.jar")
    lines.append("-classpath fr.jar;starfield.jar")
    if with_agent and agent_after:
        lines.append(AGENT)
    lines.append(MAIN)
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ routing

@pytest.mark.parametrize("text,route", [
    (vmparams(), sa.ROUTE_A),
    (miko(), sa.ROUTE_B),
    (vmparams().replace(MIXIN, "-javaagent:fr.jar"), sa.ROUTE_B),
])
def test_detect_route(text, route):
    assert sa.detect_route(text) == route


def test_detect_route_rejects_nothing_installed():
    with pytest.raises(sa.SetupError, match="no Fast Rendering agent line"):
        sa.detect_route("java.exe -Xmx4096m " + MAIN)


# ------------------------------------------------------ route A (MixinFR)

def test_route_a_inserts_after_the_bridge():
    """The bridge must stay first; this is the direction that regressed once."""
    out = sa.patch_single_line(vmparams(), sa.ROUTE_A)
    assert out.index(MIXIN) < out.index(AGENT)
    assert sa.verify(out, sa.ROUTE_A) == []


def test_route_a_stays_on_one_line():
    out = sa.patch_single_line(vmparams(), sa.ROUTE_A)
    assert "\n" not in out
    assert out.rstrip().endswith(MAIN)


def test_route_a_check_flags_agent_before_bridge():
    text = vmparams(with_agent=True, agent_first=True)
    problems = sa.verify(text, sa.ROUTE_A)
    assert any("BEFORE the MixinFR bridge" in p for p in problems)


def test_route_a_reinstall_is_idempotent():
    once = sa.patch_single_line(vmparams(), sa.ROUTE_A)
    twice = sa.patch_single_line(once, sa.ROUTE_A)
    assert once == twice
    assert once.count("hypernova.agent.jar") == 1


def test_route_a_refuses_when_main_class_is_not_last():
    broken = vmparams().replace(MAIN, MAIN + " -Dextra=1")
    with pytest.raises(sa.SetupError, match="not the last thing"):
        sa.patch_single_line(broken, sa.ROUTE_A)


# ------------------------------------------------------ route B (Miko)

def test_route_b_inserts_before_fr():
    out = sa.patch_multi_line(miko(), sa.ROUTE_B)
    assert out.index(AGENT) < out.index("-javaagent:fr.agent.jar")
    assert sa.verify(out, sa.ROUTE_B) == []


def test_route_b_check_flags_agent_after_fr():
    problems = sa.verify(miko(with_agent=True, agent_after=True), sa.ROUTE_B)
    assert any("AFTER Fast Rendering" in p for p in problems)


def test_route_b_moves_a_legacy_line_that_sits_after_fr():
    out = sa.patch_multi_line(miko(with_agent=True, agent_after=True), sa.ROUTE_B)
    assert out.count("hypernova.agent.jar") == 1
    assert out.index(AGENT) < out.index("-javaagent:fr.agent.jar")
    assert sa.verify(out, sa.ROUTE_B) == []


def test_route_b_keeps_main_class_last():
    out = sa.patch_multi_line(miko(), sa.ROUTE_B)
    assert out.strip().splitlines()[-1].strip() == MAIN


def test_route_b_refuses_when_content_follows_main_class():
    broken = miko().rstrip("\n") + "\n-Devil=1\n"
    with pytest.raises(sa.SetupError, match="must stay the last line"):
        sa.patch_multi_line(broken, sa.ROUTE_B)


# ------------------------------------------------------------------ common

def test_verify_reports_missing_agent():
    assert sa.verify(miko(), sa.ROUTE_B) == ["Hypernova agent line is missing"]


def test_verify_flags_duplicate_agent_lines():
    dup = miko(with_agent=True).replace("-Xss4m", "-Xss4m\n" + AGENT)
    problems = sa.verify(dup, sa.ROUTE_B)
    assert any("more than once" in p for p in problems)


def test_verify_does_not_touch_memory_settings():
    """Memory belongs to the launcher configurator; the installer must not edit it."""
    text = vmparams(with_agent=True)
    assert "-Xmx4096m" in sa.patch_single_line(text, sa.ROUTE_A)
    assert "-Xmx4096m" in sa.patch_multi_line(miko(), sa.ROUTE_B)
