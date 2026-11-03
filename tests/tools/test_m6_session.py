from pathlib import Path

from m6_session import end, start


def _seed_logs(game: Path, agent_text: str = "", game_text: str = "") -> None:
    (game / "starsector-core").mkdir(parents=True, exist_ok=True)
    (game / "saves" / "hypernova").mkdir(parents=True, exist_ok=True)
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
    _seed_logs(
        game,
        agent_text=(
            "hypernova agent premain\n"
            "lazy probe: summary queue=1 failed=0 disabled=0 dimMismatch=0 "
            "failedParked=0 main=bound liveBytes=10 evictableBytes=5\n"
            "HYPERNOVA_FRAME frames=600 over200=0 maxMs=10 p99Ms=5 lastMs=5 longGaps=0\n"
        ),
        game_text="Fast Rendering: v0.9.7rc2\n",
    )
    report = end(game, tmp_path / "evidence", "campaign-1")
    assert report["label"] == "campaign-1"
    assert report["frame_probe"]["present"] is True
    assert report["lazy"]["present"] is True
    assert report["log_audit"]["total"] == 0
    assert report["ok"] is True


def test_end_without_logs_is_not_ok(tmp_path):
    game = tmp_path / "game"
    (game / "starsector-core").mkdir(parents=True)
    (game / "saves" / "hypernova").mkdir(parents=True)
    report = end(game, tmp_path / "evidence", "empty")
    assert report["ok"] is False
