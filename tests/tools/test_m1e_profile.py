import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("m1e_profile", REPO / "tools" / "m1e_profile.py")
profile = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(profile)

SOURCE = (
    "-Xmx10g\r\n"
    "-javaagent:../mods/hypernova_infinite_engine/jars/hypernova.agent.jar\r\n"
    "-javaagent:fr.agent.jar\r\n"
    "-classpath fr.jar;janino.jar;starfarer.api.jar\r\n"
    "com.fs.starfarer.StarfarerLauncher"
)


def test_convert_removes_fr_from_agent_and_classpath():
    out, stats = profile.convert(SOURCE)
    assert "fr.agent.jar" not in out
    assert "-classpath janino.jar;starfarer.api.jar" in out
    assert "hypernova.agent.jar" in out
    assert stats == {
        "removed_fr_agent_lines": 1,
        "removed_fr_classpath_tokens": 1,
        "classpath_lines": 1,
    }


def test_convert_preserves_crlf():
    out, _ = profile.convert(SOURCE)
    assert "\r\n" in out
    assert "\n" not in out.replace("\r\n", "")


def test_convert_is_idempotent():
    once, _ = profile.convert(SOURCE)
    twice, stats = profile.convert(once)
    assert twice == once
    assert stats["removed_fr_agent_lines"] == 0
    assert stats["removed_fr_classpath_tokens"] == 0


def test_convert_keeps_lookalike_tokens():
    text = SOURCE.replace("janino.jar", "notfr.jar;fr.jar.bak")
    out, stats = profile.convert(text)
    assert "notfr.jar" in out
    assert "fr.jar.bak" in out
    assert stats["removed_fr_classpath_tokens"] == 1


def test_convert_refuses_missing_hypernova_agent():
    text = SOURCE.replace(
        "-javaagent:../mods/hypernova_infinite_engine/jars/hypernova.agent.jar\r\n", "")
    with pytest.raises(profile.ProfileError, match="Hypernova agent"):
        profile.convert(text)


def test_convert_refuses_split_classpath():
    text = SOURCE.replace(
        "-classpath fr.jar;janino.jar;starfarer.api.jar",
        "-classpath\r\nfr.jar;janino.jar")
    with pytest.raises(profile.ProfileError, match="same line"):
        profile.convert(text)


def test_convert_refuses_duplicate_classpath():
    text = SOURCE.replace(
        "-classpath fr.jar;janino.jar;starfarer.api.jar",
        "-classpath fr.jar;janino.jar\n-classpath other.jar")
    with pytest.raises(profile.ProfileError, match="multiple -classpath"):
        profile.convert(text)


def test_cli_does_not_modify_source(tmp_path):
    src = tmp_path / "Miko_Lite.txt"
    src.write_bytes(SOURCE.encode("utf-8"))
    out = tmp_path / "Miko_Lite_nofr.txt"

    assert profile.main(["--src", str(src), "--out", str(out)]) == 0
    assert src.read_bytes() == SOURCE.encode("utf-8")
    assert out.exists()
    assert "fr.agent.jar" not in out.read_text(encoding="utf-8")


def test_cli_refuses_overwrite_without_force(tmp_path):
    src = tmp_path / "Miko_Lite.txt"
    src.write_bytes(SOURCE.encode("utf-8"))
    out = tmp_path / "Miko_Lite_nofr.txt"
    out.write_text("old", encoding="utf-8")

    assert profile.main(["--src", str(src), "--out", str(out)]) == 2
    assert out.read_text(encoding="utf-8") == "old"
