import json

from m6_log_audit import (
    EXTRA_PATTERNS,
    MAX_MATCHES,
    main,
    scan_log_text,
    scan_logs,
)


def test_scan_log_text_counts_texture_and_extra_errors():
    text = (
        "INFO start\n"
        "Failed to load texture: a.png\n"
        "java.lang.VerifyError: bad\n"
        "ClassFormatError\n"
        "AsyncException\n"
        "isStateCorrupted\n"
        "Failed to load texture: b.png\n"
    )
    result = scan_log_text(text)
    assert result["errors"]["Failed to load texture"] == 2
    assert result["errors"]["VerifyError"] == 1
    assert result["total"] == 6
    assert result["ok"] is False


def test_scan_log_text_clean_log_is_ok():
    result = scan_log_text("INFO hello\n")
    assert result["total"] == 0
    assert result["observations_total"] == 0
    assert result["ok"] is True


def test_scan_log_text_reports_absolute_line_numbers():
    result = scan_log_text("a\nFailed to load texture: x\n")
    assert result["matches"][0]["line"] == 2
    assert result["matches"][0]["pattern"] == "Failed to load texture"
    assert result["matches"][0]["kind"] == "error"


def test_extra_patterns_cover_chinese_input_and_fonts():
    joined = " ".join(EXTRA_PATTERNS)
    assert "ChineseInputFix" in joined
    assert "font" in joined.lower()


def test_noise_is_observation_only():
    # TIME/LIFETIME/PRIMEDIVI 只含 IME 子串，不是独立词，不能产生 errors。
    text = (
        "TIME=1 LIFETIME=2 PRIMEDIVI\n"
        "发现 Mod：{ChineseInputFix} [D:\\mods\\ChineseInputFix]\n"
        "IME\n"
    )
    result = scan_log_text(text)
    assert result["total"] == 0
    assert result["ok"] is True
    assert result["errors"]["Failed to load texture"] == 0
    assert result["observations"]["IME"] == 1
    assert result["observations"]["ChineseInputFix"] == 2


def test_chinese_input_fix_discovery_line_does_not_fail():
    result = scan_log_text("INFO ModManager - 发现 Mod：{ChineseInputFix}\n")
    assert result["total"] == 0
    assert result["ok"] is True
    assert result["observations"]["ChineseInputFix"] == 1


def test_error_patterns_are_case_insensitive_and_cover_fontconfig():
    result = scan_log_text(
        "failed to load texture: x.png\n"
        "Fontconfig error: Cannot load default config file\n"
        "GLYPH NOT FOUND\n"
        "java.awt.headlessexception\n"
    )
    assert result["errors"]["Failed to load texture"] == 1
    assert result["errors"]["Fontconfig error"] == 1
    assert result["errors"]["Glyph not found"] == 1
    assert result["errors"]["java.awt.HeadlessException"] == 1
    assert result["total"] == 4
    assert result["ok"] is False


def test_matches_are_capped_and_flagged_truncated():
    text = "Failed to load texture: x.png\n" * (MAX_MATCHES + 10)
    result = scan_log_text(text)
    assert result["errors"]["Failed to load texture"] == MAX_MATCHES + 10
    assert result["total"] == MAX_MATCHES + 10
    assert len(result["matches"]) == MAX_MATCHES
    assert result["truncated"] is True
    assert result["ok"] is False


def test_font_file_not_found_is_error_case_insensitive():
    result = scan_log_text(
        "java.io.IOException: font file not found: a.ttf\n"
        "FONT FILE NOT FOUND: b.ttf\n"
    )
    assert result["errors"]["font file not found"] == 2
    assert result["total"] == 2
    assert result["ok"] is False


def test_scan_logs_aggregates_errors_and_observations(tmp_path):
    game = tmp_path / "starsector.log"
    agent = tmp_path / "scripts-agent.log"
    game.write_text("Failed to load texture: a\n{ChineseInputFix}\n", encoding="utf-8")
    agent.write_text("VerifyError\nIME\n", encoding="utf-8")
    report = scan_logs(game, agent)
    assert report["total"] == 2
    assert report["observations_total"] == 2
    assert report["observations"]["ChineseInputFix"] == 1
    assert report["observations"]["IME"] == 1
    assert report["complete"] is True
    assert report["ok"] is False


def _seed_logs(root, game_text="", agent_text=""):
    (root / "starsector-core").mkdir(parents=True, exist_ok=True)
    (root / "saves" / "hypernova").mkdir(parents=True, exist_ok=True)
    (root / "starsector-core" / "starsector.log").write_text(
        game_text, encoding="utf-8"
    )
    (root / "saves" / "hypernova" / "scripts-agent.log").write_text(
        agent_text, encoding="utf-8"
    )


def test_main_healthy_logs_rc_zero(tmp_path):
    root = tmp_path / "game"
    _seed_logs(root, "Fast Rendering: v0.9.7rc2\n", "INFO ok\n")
    out = tmp_path / "out.json"
    assert main(["--game-root", str(root), "--out", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["complete"] is True


def test_main_observations_only_rc_zero(tmp_path):
    root = tmp_path / "game"
    _seed_logs(root, "发现 Mod：{ChineseInputFix}\n", "IME\n")
    out = tmp_path / "out.json"
    assert main(["--game-root", str(root), "--out", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["total"] == 0
    assert report["observations_total"] == 2


def test_main_errors_rc_one(tmp_path):
    root = tmp_path / "game"
    _seed_logs(root, "Failed to load texture: x\n", "")
    out = tmp_path / "out.json"
    assert main(["--game-root", str(root), "--out", str(out)]) == 1


def test_main_missing_all_logs_is_fail_closed(tmp_path, capsys):
    out = tmp_path / "out.json"
    rc = main(["--game-root", str(tmp_path / "no-game"), "--out", str(out)])
    captured = capsys.readouterr()
    assert rc == 2
    assert "FATAL: no logs under" in captured.err
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["complete"] is False


def test_main_partial_logs_rc_one_when_starsector_missing(tmp_path, capsys):
    root = tmp_path / "game"
    (root / "saves" / "hypernova").mkdir(parents=True)
    (root / "saves" / "hypernova" / "scripts-agent.log").write_text(
        "INFO ok\n", encoding="utf-8"
    )
    out = tmp_path / "out.json"
    rc = main(["--game-root", str(root), "--out", str(out)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "starsector.log" in captured.err
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["complete"] is False
    assert report["agent_log"]["present"] is True
    assert report["starsector_log"]["present"] is False
