import json
import os
import time
from pathlib import Path

import pytest

import m6_session
from m6_session import end, main, start

HEALTHY_AGENT = (
    "hypernova agent premain\n"
    "lazy probe: summary queue=1 failed=0 disabled=0 dimMismatch=0 "
    "failedParked=0 main=bound liveBytes=10 evictableBytes=5\n"
    "HYPERNOVA_FRAME frames=600 over200=0 maxMs=10 p99Ms=5 lastMs=5 longGaps=0\n"
)
HEALTHY_GAME = "Fast Rendering: v0.9.7rc2\n"


def _seed_logs(game: Path, agent_text: str = "", game_text: str = "") -> None:
    (game / "starsector-core").mkdir(parents=True, exist_ok=True)
    (game / "saves" / "hypernova").mkdir(parents=True, exist_ok=True)
    (game / "starsector-core" / "starsector.log").write_text(
        game_text, encoding="utf-8"
    )
    (game / "saves" / "hypernova" / "scripts-agent.log").write_text(
        agent_text, encoding="utf-8"
    )


def _write_session_logs(game: Path, agent_text: str, game_text: str) -> None:
    (game / "starsector-core" / "starsector.log").write_text(
        game_text, encoding="utf-8"
    )
    (game / "saves" / "hypernova" / "scripts-agent.log").write_text(
        agent_text, encoding="utf-8"
    )


def test_start_moves_logs_to_evidence(tmp_path):
    game = tmp_path / "game"
    _seed_logs(game, agent_text="agent old\n", game_text="old\n")
    meta = start(game, tmp_path / "evidence", "campaign-1")
    assert meta["label"] == "campaign-1"
    assert (tmp_path / "evidence/campaign-1/logs/pre-starsector.log").read_text(
        encoding="utf-8"
    ) == "old\n"
    assert (tmp_path / "evidence/campaign-1/logs/pre-scripts-agent.log").read_text(
        encoding="utf-8"
    ) == "agent old\n"
    assert not (game / "starsector-core/starsector.log").exists()
    assert not (game / "saves/hypernova/scripts-agent.log").exists()
    assert (tmp_path / "evidence/campaign-1/session-meta.json").is_file()


def test_end_merges_frame_lazy_and_log_audit(tmp_path):
    game = tmp_path / "game"
    _seed_logs(game, agent_text="previous session\n", game_text="old\n")
    start(game, tmp_path / "evidence", "campaign-1")
    _write_session_logs(game, HEALTHY_AGENT, HEALTHY_GAME)
    report = end(game, tmp_path / "evidence", "campaign-1")
    assert report["label"] == "campaign-1"
    assert report["frame_probe"]["present"] is True
    assert report["lazy"]["present"] is True
    assert report["log_audit"]["total"] == 0
    assert report["new_logs_ok"] is True
    assert report["ok"] is True


def test_end_without_logs_is_not_ok(tmp_path):
    game = tmp_path / "game"
    (game / "starsector-core").mkdir(parents=True)
    (game / "saves" / "hypernova").mkdir(parents=True)
    start(game, tmp_path / "evidence", "empty")
    report = end(game, tmp_path / "evidence", "empty")
    assert report["ok"] is False
    assert report["new_logs_ok"] is False
    assert "no new logs since start" in report["problems"]


def test_end_without_start_raises(tmp_path):
    game = tmp_path / "game"
    _seed_logs(game, agent_text=HEALTHY_AGENT, game_text=HEALTHY_GAME)
    with pytest.raises(FileNotFoundError):
        end(game, tmp_path / "evidence", "ghost")
    assert not (tmp_path / "evidence/ghost/session.json").exists()


def test_end_rejects_logs_not_written_since_start(tmp_path):
    game = tmp_path / "game"
    _seed_logs(game, agent_text="old agent\n", game_text="old\n")
    start(game, tmp_path / "evidence", "stale")
    _write_session_logs(game, HEALTHY_AGENT, HEALTHY_GAME)
    stale = time.time() - 3600
    for rel in ("starsector-core/starsector.log",
                "saves/hypernova/scripts-agent.log"):
        os.utime(game / rel, (stale, stale))
    report = end(game, tmp_path / "evidence", "stale")
    assert report["ok"] is False
    assert report["new_logs_ok"] is False
    assert "no new logs since start" in report["problems"]


def test_end_flags_unhealthy_lazy_counts(tmp_path):
    game = tmp_path / "game"
    _seed_logs(game, agent_text="previous session\n", game_text="old\n")
    start(game, tmp_path / "evidence", "lazy-bad")
    _write_session_logs(
        game,
        HEALTHY_AGENT.replace("failed=0", "failed=1"),
        HEALTHY_GAME,
    )
    report = end(game, tmp_path / "evidence", "lazy-bad")
    assert report["ok"] is False
    assert any(problem.startswith("lazy health") for problem in report["problems"])


@pytest.mark.parametrize(
    "label", ["", ".", "..", "../escape", "/abs", "a/b", "a\\b", "C:\\x"]
)
def test_start_rejects_unsafe_labels(tmp_path, label):
    game = tmp_path / "game"
    _seed_logs(game, agent_text="agent\n", game_text="game\n")
    with pytest.raises(ValueError):
        start(game, tmp_path / "evidence", label)


def test_end_rejects_unsafe_label(tmp_path):
    game = tmp_path / "game"
    with pytest.raises(ValueError):
        end(game, tmp_path / "evidence", "../escape")


def test_start_failure_rolls_back_and_allows_retry(tmp_path, monkeypatch):
    game = tmp_path / "game"
    evidence = tmp_path / "evidence"
    _seed_logs(game, agent_text="agent old\n", game_text="old\n")
    real_move = m6_session.shutil.move
    calls = {"count": 0}

    def flaky_move(src, dst):
        calls["count"] += 1
        if calls["count"] == 2:
            raise PermissionError("log is still locked")
        return real_move(src, dst)

    monkeypatch.setattr(m6_session.shutil, "move", flaky_move)
    with pytest.raises(PermissionError):
        start(game, evidence, "retry")

    # 原日志回滚到位，本次创建的 pre-* 与空目录被清理，可直接重试。
    assert (game / "starsector-core/starsector.log").read_text(
        encoding="utf-8"
    ) == "old\n"
    assert (game / "saves/hypernova/scripts-agent.log").read_text(
        encoding="utf-8"
    ) == "agent old\n"
    assert not (evidence / "retry" / "logs").exists()
    assert not (evidence / "retry" / "session-meta.json").exists()

    monkeypatch.setattr(m6_session.shutil, "move", real_move)
    meta = start(game, evidence, "retry")
    assert meta["label"] == "retry"
    assert (evidence / "retry" / "session-meta.json").is_file()


def test_start_snapshot_records_start_time(tmp_path):
    game = tmp_path / "game"
    _seed_logs(game, agent_text="agent\n", game_text="game\n")
    meta = start(game, tmp_path / "evidence", "meta")
    data = json.loads(
        (tmp_path / "evidence/meta/session-meta.json").read_text(encoding="utf-8")
    )
    assert isinstance(data["started_at_epoch"], float)
    assert data["started_at_epoch"] == meta["started_at_epoch"]


def test_cli_end_without_start_reports_one_stderr_line(tmp_path, capsys):
    game = tmp_path / "game"
    (game / "starsector-core").mkdir(parents=True)
    rc = main([
        "end",
        "--game-root", str(game),
        "--evidence-root", str(tmp_path / "evidence"),
        "--label", "ghost",
    ])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.err.strip().count("\n") == 0
    assert "FATAL:" in captured.err


def test_cli_end_not_ok_reports_one_stderr_line(tmp_path, capsys):
    game = tmp_path / "game"
    (game / "starsector-core").mkdir(parents=True)
    (game / "saves" / "hypernova").mkdir(parents=True)
    start(game, tmp_path / "evidence", "empty")
    rc = main([
        "end",
        "--game-root", str(game),
        "--evidence-root", str(tmp_path / "evidence"),
        "--label", "empty",
    ])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.err.strip().count("\n") == 0
    assert "not ok" in captured.err


def test_cli_start_warns_when_no_logs_found(tmp_path, capsys):
    game = tmp_path / "game"
    (game / "starsector-core").mkdir(parents=True)
    (game / "saves" / "hypernova").mkdir(parents=True)
    rc = main([
        "start",
        "--game-root", str(game),
        "--evidence-root", str(tmp_path / "evidence"),
        "--label", "no-logs",
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert "WARNING:" in captured.err
