"""M6：日志健康审计（五类纹理错误 + 中文/字体/输入异常）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from m28_scene_gate import TEXTURE_ERRORS, count_texture_errors  # noqa: E402

EXTRA_PATTERNS = (
    "ChineseInputFix",
    "Exception in thread \"AWT-EventQueue",
    "UnsatisfiedLinkError",
    "java.awt.HeadlessException",
    "Font config error",
    "font file not found",
    "Glyph not found",
    "missing glyph",
    "Input method",
    "IME",
)

MAX_MATCHES = 50


def scan_log_text(text: str) -> dict:
    counts = count_texture_errors(text)
    counts.update({pattern: text.count(pattern) for pattern in EXTRA_PATTERNS})
    matches = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for pattern in counts:
            if pattern in line:
                matches.append({"pattern": pattern, "line": lineno,
                                "text": line.strip()[:300]})
                break
        if len(matches) >= MAX_MATCHES:
            break
    total = sum(counts.values())
    return {"counts": counts, "total": total, "matches": matches,
            "ok": total == 0}


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
        "ok": game_result["ok"] and agent_result["ok"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--text", action="store_true")
    args = parser.parse_args(argv)
    root = args.game_root.resolve()
    report = scan_logs(root / "starsector-core/starsector.log",
                       root / "saves/hypernova/scripts-agent.log")
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    if args.text or not args.out:
        print(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
