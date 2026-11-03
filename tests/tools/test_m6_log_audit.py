from m6_log_audit import EXTRA_PATTERNS, scan_log_text


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
    assert result["counts"]["Failed to load texture"] == 2
    assert result["counts"]["VerifyError"] == 1
    assert result["total"] == 6
    assert result["ok"] is False


def test_scan_log_text_clean_log_is_ok():
    result = scan_log_text("INFO hello\n")
    assert result["total"] == 0
    assert result["ok"] is True


def test_scan_log_text_reports_absolute_line_numbers():
    result = scan_log_text("a\nFailed to load texture: x\n")
    assert result["matches"][0]["line"] == 2
    assert result["matches"][0]["pattern"] == "Failed to load texture"


def test_extra_patterns_cover_chinese_input_and_fonts():
    joined = " ".join(EXTRA_PATTERNS)
    assert "ChineseInputFix" in joined
    assert "font" in joined.lower()
