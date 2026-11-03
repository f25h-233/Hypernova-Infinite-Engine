"""M6：日志健康审计（五类纹理错误 + 真实异常；中文/字体/IME 观察项）。

扫描整份轮转日志；`matches[].line` 是整份日志的绝对行号（跨所有会话），
不是最后一次会话内的行号。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from m28_scene_gate import TEXTURE_ERRORS  # noqa: E402

EXTRA_ERROR_PATTERNS: tuple[str, ...] = (
    'Exception in thread "AWT-EventQueue',
    "UnsatisfiedLinkError",
    "java.awt.HeadlessException",
    "Fontconfig error",
    "Font config error",
    "Glyph not found",
    "missing glyph",
)

OBSERVATION_PATTERNS: tuple[str, ...] = (
    "ChineseInputFix",
    "IME",
)

ERROR_PATTERNS: tuple[str, ...] = TEXTURE_ERRORS + EXTRA_ERROR_PATTERNS
EXTRA_PATTERNS: tuple[str, ...] = EXTRA_ERROR_PATTERNS + OBSERVATION_PATTERNS

# 独立词 IME：不匹配 TIME/LIFETIME/PRIMEDIVI 等键名里的子串。
IME_RE = re.compile(r"(?<![A-Za-z])IME(?![A-Za-z])")

MAX_MATCHES = 50


def _match_line(line: str) -> tuple[str, str] | None:
    folded = line.casefold()
    for pattern in ERROR_PATTERNS:
        if pattern.casefold() in folded:
            return "error", pattern
    if "ChineseInputFix" in line:
        return "observation", "ChineseInputFix"
    if IME_RE.search(line):
        return "observation", "IME"
    return None


def scan_log_text(text: str) -> dict:
    """Scan one log text.

    `matches[].line` is an absolute line number in the whole rotated log
    (all sessions), not a line number inside the last session.

    Error counts are case-insensitive; `m28_scene_gate.count_texture_errors`
    is case-sensitive, so it cannot satisfy the M6 addendum and is not used.
    """
    folded = text.casefold()
    errors = {pattern: folded.count(pattern.casefold())
              for pattern in ERROR_PATTERNS}
    observations = {
        "ChineseInputFix": text.count("ChineseInputFix"),
        "IME": len(IME_RE.findall(text)),
    }
    matches = []
    truncated = False
    for lineno, line in enumerate(text.splitlines(), 1):
        hit = _match_line(line)
        if hit is None:
            continue
        if len(matches) >= MAX_MATCHES:
            truncated = True
            break
        kind, pattern = hit
        matches.append({"kind": kind, "pattern": pattern, "line": lineno,
                        "text": line.strip()[:300]})
    total = sum(errors.values())
    observations_total = sum(observations.values())
    return {
        "errors": errors,
        "observations": observations,
        "total": total,
        "observations_total": observations_total,
        "matches": matches,
        "truncated": truncated,
        "ok": total == 0,
    }


def _read(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def scan_logs(starsector_log: str | Path, agent_log: str | Path) -> dict:
    game = Path(starsector_log)
    agent = Path(agent_log)
    game_result = scan_log_text(_read(game))
    agent_result = scan_log_text(_read(agent))
    return {
        "starsector_log": {"path": str(game), "present": game.is_file(),
                           **game_result},
        "agent_log": {"path": str(agent), "present": agent.is_file(),
                      **agent_result},
        "total": game_result["total"] + agent_result["total"],
        "observations": {
            "ChineseInputFix": (
                game_result["observations"]["ChineseInputFix"]
                + agent_result["observations"]["ChineseInputFix"]
            ),
            "IME": (game_result["observations"]["IME"]
                    + agent_result["observations"]["IME"]),
        },
        "observations_total": (
            game_result["observations_total"] + agent_result["observations_total"]
        ),
        "complete": game.is_file() and agent.is_file(),
        "ok": game_result["ok"] and agent_result["ok"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--text", action="store_true")
    args = parser.parse_args(argv)
    root = args.game_root.resolve()
    try:
        report = scan_logs(root / "starsector-core/starsector.log",
                           root / "saves/hypernova/scripts-agent.log")
    except OSError as exc:
        print(f"FATAL: cannot read logs under {root}: {exc}", file=sys.stderr)
        return 2
    missing = []
    if not report["starsector_log"]["present"]:
        missing.append("starsector.log")
    if not report["agent_log"]["present"]:
        missing.append("scripts-agent.log")
    if missing:
        report["ok"] = False
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    try:
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text + "\n", encoding="utf-8")
        if args.text or not args.out:
            print(text)
    except OSError as exc:
        print(f"FATAL: cannot write report: {exc}", file=sys.stderr)
        return 2
    if len(missing) == 2:
        print(f"FATAL: no logs under {root}", file=sys.stderr)
        return 2
    if missing:
        print(f"FATAL: missing log(s): {', '.join(missing)}", file=sys.stderr)
        return 1
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
