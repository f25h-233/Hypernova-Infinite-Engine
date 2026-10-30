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
# 真实日志里有大量 1–2 ms 的时间戳倒序（多线程写日志），不能当会话边界。
# 只有倒退超过 1 s 才说明日志跨了两次启动。
ROLLOVER_GAP_MS = 1000


def _select_session(lines: list[str]) -> tuple[list[str], str]:
    """Return (last game session's lines, session_source).

    The session starts at the later of:
      * the last `Fast Rendering` anchor, and
      * the last timestamp rollover where the clock goes backwards by more
        than ``ROLLOVER_GAP_MS``.

    A stale FR anchor therefore loses to a newer anchor-less session. Small
    (1–2 ms) backwards jitter is ignored, so it cannot cut a normal-count
    window in half.

    ``session_source`` is ``"anchor"`` or ``"rollover"`` when a boundary was
    used. With no boundary at all the whole file is treated as one session
    (``"whole"``); if it also has no millisecond timestamps, ``menu_s`` stays
    None and the gate fails closed.
    """
    anchors = [i for i, line in enumerate(lines) if SESSION_ANCHOR in line]
    rollovers: list[int] = []
    prev: int | None = None
    for i, line in enumerate(lines):
        m = TS.match(line)
        if not m:
            continue
        t = int(m.group(1))
        if prev is not None and prev - t > ROLLOVER_GAP_MS:
            rollovers.append(i)
        prev = t

    anchor = anchors[-1] if anchors else None
    rollover = rollovers[-1] if rollovers else None

    if anchor is None and rollover is None:
        # 没有切分点：非空且带时间戳的日志按单会话处理；连时间戳都没有时
        # 仍返回整份文件，但 measure() 找不到 menu_t，门禁失败关闭。
        return lines, "whole"
    if rollover is None or (anchor is not None and anchor >= rollover):
        return lines[anchor:], "anchor"
    return lines[rollover:], "rollover"


def _last_agent_session(lines: list[str]) -> list[str]:
    starts = [i for i, line in enumerate(lines) if AGENT_ANCHOR in line]
    # 没有 premain = 没有本次 agent 启动；失败关闭，避免读到上一次的 patched 行。
    return lines[starts[-1]:] if starts else []


def measure(log_path: str | Path, agent_log: str | Path | None = None,
            baseline: int = 30378, threshold: float = 0.2,
            max_normal: int = 50) -> dict:
    lines = Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()
    lines, session_source = _select_session(lines)
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
        "session_source": session_source,
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
