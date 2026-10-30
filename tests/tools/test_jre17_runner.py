from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _assert_runtime_override(script: Path) -> None:
    text = script.read_text(encoding="utf-8")
    assert 'JAVA_RUNTIME="${JAVA_RUNTIME:-java}"' in text, script
    assert '"$JAVA_RUNTIME" -jar' in text, script
    for line in text.splitlines():
        if line.strip().startswith("java -jar"):
            raise AssertionError(f"bare java -jar remains in {script}: {line}")


def test_agent_runner_uses_runtime_override():
    _assert_runtime_override(REPO / "tools" / "java" / "run-agent-tests.sh")


def test_mod_runner_uses_runtime_override():
    _assert_runtime_override(REPO / "tools" / "java" / "run-tests.sh")
