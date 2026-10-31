import sys
from pathlib import Path

import pytest

# pytest under `python -I` does not put the repo root on sys.path; tools/ is not
# a package and tests/conftest.py only inserts tools/ itself.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.m3_profile import derive


def test_replaces_log4j_token_and_preserves_crlf(tmp_path):
    src = tmp_path / "Miko_Lite.txt"
    src.write_bytes(
        b"-Xms8192m\r\n"
        b"-Dlog4j.configuration=..\\\\mikohime/mikohime.properties\r\n"
        b"-javaagent:../mods/x/hypernova.agent.jar\r\n"
        b"-javaagent:fr.agent.jar\r\n"
    )
    dst = tmp_path / "Miko_Lite_phase.txt"
    derive(src, dst, "mikohime/hn-phase.properties")
    data = dst.read_bytes()
    assert b"hn-phase.properties" in data
    assert b"mikohime.properties" not in data
    assert data.count(b"\r\n") == 4
    assert data.count(b"\n") == 4
    # agent 顺序不变：hypernova 在 FR 之前
    assert data.index(b"hypernova.agent.jar") < data.index(b"fr.agent.jar")


def test_rejects_missing_token(tmp_path):
    src = tmp_path / "bad.txt"
    src.write_bytes(b"-Xmx1g\r\n")
    with pytest.raises(ValueError):
        derive(src, tmp_path / "out.txt", "mikohime/hn-phase.properties")


def test_rejects_multiple_tokens(tmp_path):
    src = tmp_path / "bad2.txt"
    src.write_bytes(b"mikohime/mikohime.properties\r\nmikohime/mikohime.properties\r\n")
    with pytest.raises(ValueError):
        derive(src, tmp_path / "out.txt", "mikohime/hn-phase.properties")
