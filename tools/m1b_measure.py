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

# Prefix match: FR 0.9.5 logs "v0.9.5", FR 0.9.7rc2 logs "v0.9.7rc2".
# A version-pinned anchor silently stops finding sessions after an FR upgrade.
SESSION_ANCHOR = "Fast Rendering: v0.9."
MENU_ANCHOR = "Playing music with id [miscallenous_main_menu.ogg]"
AGENT_ANCHOR = "hypernova agent premain"
TS = re.compile(r"^(\d+) ")
NORMAL = re.compile(
    r"^\d+ \[[^\]]+\] INFO  com\.fs\.graphics\.TextureLoader  - "
    r"Loading image \[cache/[^\]]*_normal\.png\]"
)
# 真 no-FR 会话里 vanilla TextureLoader 不写 "Loading image"；同等信号是
# "Cleaned buffer for texture cache/..._normal.png"，计数口径由 --normal-metric 选择。
CLEANED_NORMAL = re.compile(
    r"^\d+ \[[^\]]+\] INFO  com\.fs\.graphics\.TextureLoader  - "
    r"Cleaned buffer for texture (cache/.*?_normal\.png)"
)
# 真实日志里有大量 1–2 ms 的时间戳倒序（多线程写日志），不能当会话边界。
# 只有倒退超过 1 s 才说明日志跨了两次启动。
ROLLOVER_GAP_MS = 1000
FAILED_TEXTURE = "Failed to load texture"
FR_MISSING = "FR missing; scripts cache disabled"


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
            max_normal: int = 50, expect_no_fr: bool = False,
            normal_metric: str | None = None) -> dict:
    lines = Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()
    lines, session_source = _select_session(lines)
    fr_present = any(SESSION_ANCHOR in line for line in lines)
    failed_texture_lines = sum(1 for line in lines if FAILED_TEXTURE in line)

    # --expect-no-fr implies the cleaned metric: vanilla TextureLoader emits
    # "Cleaned buffer for texture cache/..._normal.png" instead of "Loading image".
    metric = normal_metric or ("cleaned" if expect_no_fr else "loading")
    if metric not in ("loading", "cleaned"):
        raise ValueError(f"unknown normal_metric: {metric!r}")

    menu_t: int | None = None
    loading_before = 0
    loading_after = 0
    cleaned_before = 0
    cleaned_after = 0
    loading_window: list[int] = []
    cleaned_window: list[int] = []
    for line in lines:
        m = TS.match(line)
        if not m:
            continue
        t = int(m.group(1))
        if menu_t is None and MENU_ANCHOR in line:
            menu_t = t
        if NORMAL.match(line):
            if menu_t is None:
                loading_before += 1
                loading_window.append(t)
            else:
                loading_after += 1
        if CLEANED_NORMAL.match(line):
            if menu_t is None:
                cleaned_before += 1
                cleaned_window.append(t)
            else:
                cleaned_after += 1

    if metric == "cleaned":
        before, after, window = cleaned_before, cleaned_after, cleaned_window
    else:
        before, after, window = loading_before, loading_after, loading_window

    patched = False
    patch_line = None
    mismatch_line = None
    fr_missing_disabled = False
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
            if FR_MISSING in line:
                fr_missing_disabled = True

    drop = 1.0 - (before / baseline) if baseline > 0 else 0.0
    cap = min(max(50, int(baseline * threshold)), max_normal)
    gate_ok = (
        menu_t is not None
        and patched
        and mismatch_line is None
        and before <= cap
        and (not expect_no_fr or (not fr_present and fr_missing_disabled
                                  and failed_texture_lines == 0))
    )
    return {
        "menu_s": round(menu_t / 1000.0, 1) if menu_t is not None else None,
        "session_source": session_source,
        "normal_metric": metric,
        "normal_before_menu": before,
        "normal_after_menu": after,
        "loading_normal_before_menu": loading_before,
        "loading_normal_after_menu": loading_after,
        "normal_window_s": (
            round((window[-1] - window[0]) / 1000.0, 1) if len(window) > 1 else 0.0
        ),
        "baseline": baseline,
        "max_normal": max_normal,
        "drop": round(drop, 4),
        "patched": patched,
        "patch_line": patch_line,
        "mismatch_line": mismatch_line,
        "fr_present": fr_present,
        "fr_missing_disabled": fr_missing_disabled,
        "failed_texture_lines": failed_texture_lines,
        "expect_no_fr": expect_no_fr,
        "gate_ok": gate_ok,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--agent-log", default=None)
    ap.add_argument("--baseline", type=int, default=30378)
    ap.add_argument("--threshold", type=float, default=0.2)
    ap.add_argument("--max-normal", type=int, default=50)
    ap.add_argument("--expect-no-fr", action="store_true",
                    help="require a true no-FR session: no FR anchor, agent logs "
                         "'FR missing', and no failed texture loads")
    ap.add_argument("--normal-metric", choices=("loading", "cleaned"), default=None,
                    help="normal-count signal; default loading, cleaned when "
                         "--expect-no-fr is set")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    result = measure(args.log, args.agent_log, args.baseline, args.threshold,
                     args.max_normal, args.expect_no_fr, args.normal_metric)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8", newline="\n")
    return 0 if result["gate_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
