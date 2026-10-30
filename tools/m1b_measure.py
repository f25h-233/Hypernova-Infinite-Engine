#!/usr/bin/env python3
"""M-1b 门禁：统计主菜单前的 cache/*_normal.png 加载行，并验证 agent 补丁已生效。

门禁（出口标准）：本次游戏会话主菜单前法线行数相对 baseline 下降 >= 80% 且绝对
行数 <= max_normal，且本次 agent 会话出现 `textures: patched ...`、无
`textures: TextureData sha mismatch`。用法见文件末尾 argparse。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SESSION_ANCHOR = "Fast Rendering: v0.9.5"
MENU_ANCHOR = "Playing music with id [miscallenous_main_menu.ogg]"
AGENT_ANCHOR = "hypernova agent premain"
TS = re.compile(r"^(\d+) ")
NORMAL = re.compile(
    r"^\d+ \[[^\]]+\] INFO  com\.fs\.graphics\.TextureLoader  - "
    r"Loading image \[cache/[^\]]*_normal\.png\]"
)


def _last_session(lines: list[str]) -> list[str]:
    """Return only the last game session, or [] when there is no anchor.

    Failing closed prevents a stale session from satisfying the gate.
    """
    starts = [i for i, line in enumerate(lines) if SESSION_ANCHOR in line]
    return lines[starts[-1]:] if starts else []


def _last_agent_session(lines: list[str]) -> list[str]:
    starts = [i for i, line in enumerate(lines) if AGENT_ANCHOR in line]
    # 没有 premain = 没有本次 agent 启动；失败关闭，避免读到上一次的 patched 行。
    return lines[starts[-1]:] if starts else []


def measure(log_path: str | Path, agent_log: str | Path | None = None,
            baseline: int = 30378, threshold: float = 0.2,
            max_normal: int = 50) -> dict:
    lines = Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()
    lines = _last_session(lines)
    menu_t: int | None = None
    before = 0
    after = 0
    window: list[int] = []
    for line in lines:
        m = TS.match(line)
        if not m:
            continue
        t = int(m.group(1))
        if menu_t is None and MENU_ANCHOR in line:
            menu_t = t
        if NORMAL.match(line):
            if menu_t is None:
                before += 1
                window.append(t)
            else:
                after += 1

    patched = False
    patch_line = None
    mismatch_line = None
    if agent_log and Path(agent_log).is_file():
        agent_lines = Path(agent_log).read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
        for line in _last_agent_session(agent_lines):
            if "textures: patched" in line:
                patched = True
                patch_line = line
            elif "textures: TextureData sha mismatch" in line and mismatch_line is None:
                mismatch_line = line

    drop = 1.0 - (before / baseline) if baseline > 0 else 0.0
    cap = min(max(50, int(baseline * threshold)), max_normal)
    gate_ok = (
        menu_t is not None
        and patched
        and mismatch_line is None
        and before <= cap
    )
    return {
        "menu_s": round(menu_t / 1000.0, 1) if menu_t is not None else None,
        "normal_before_menu": before,
        "normal_after_menu": after,
        "normal_window_s": (
            round((window[-1] - window[0]) / 1000.0, 1) if len(window) > 1 else 0.0
        ),
        "baseline": baseline,
        "max_normal": max_normal,
        "drop": round(drop, 4),
        "patched": patched,
        "patch_line": patch_line,
        "mismatch_line": mismatch_line,
        "gate_ok": gate_ok,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--agent-log", default=None)
    ap.add_argument("--baseline", type=int, default=30378)
    ap.add_argument("--threshold", type=float, default=0.2)
    ap.add_argument("--max-normal", type=int, default=50)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    result = measure(args.log, args.agent_log, args.baseline, args.threshold,
                     args.max_normal)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8", newline="\n")
    return 0 if result["gate_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
