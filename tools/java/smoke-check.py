#!/usr/bin/env python3
"""M1 冒烟检查：读 starsector.log 与 telemetry，输出 PASS/FAIL。

用法:
    python -I tools/java/smoke-check.py --game Starsector-098-Base

判定口径（全部来自实测，不是假设）：
  - 真身 mod 列表是 <game>/mods/enabled_mods.json（ModManager.getFilename()），
    不是 starsector-core/data/config/enabled_mods.json（从不被读）。
  - telemetry 由 writeTextFileToCommon 落盘为 <saves>/common/hypernova/telemetry.jsonl.data。
  - 「本组件单帧耗时」看心跳里的 nanosLastTick（调度器自计时），不是 telemetry 的 nanos
    （后者含引擎侧加载/缓存查找的真实耗时，hit 路径可达数十毫秒）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BANNER = "正在运行 Starsector"
BUDGET_NANOS = 2_000_000  # REQ-R1-03: 2 ms
HEARTBEAT = re.compile(r"HYPERNOVA_TICK (\d+) backlog=(\d+) stats=SchedulerStats\[queued=(\d+), "
                       r"loaded=(\d+), failed=(\d+), ticks=(\d+), nanosLastTick=(\d+), backlog=(\d+)\]")


def sessions(lines: list[str]) -> list[int]:
    return [i for i, line in enumerate(lines) if BANNER in line]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    args = ap.parse_args()
    game = Path(args.game)
    core = game / "starsector-core"
    log = core / "starsector.log"
    telemetry = game / "saves" / "common" / "hypernova" / "telemetry.jsonl.data"

    checks: list[tuple[str, bool, str]] = []

    # ---- 0) 前置：组件是否真的被启用、产物是否齐 ----
    enabled_file = game / "mods" / "enabled_mods.json"
    enabled: list[str] = []
    if enabled_file.is_file():
        try:
            enabled = json.loads(enabled_file.read_text(encoding="utf-8")).get("enabledMods", [])
        except json.JSONDecodeError:
            enabled = []
    checks.append(("hypernova enabled in mods/enabled_mods.json",
                   "hypernova_infinite_engine" in enabled,
                   f"enabled_count={len(enabled)}"))
    mod_dir = game / "mods" / "hypernova_infinite_engine"
    checks.append(("installed manifest present",
                   (mod_dir / "data/config/hypernova/manifest-v1.json").is_file(),
                   str(mod_dir / "data/config/hypernova/manifest-v1.json")))
    checks.append(("installed jar present",
                   (mod_dir / "jars/hypernova.jar").is_file(),
                   str(mod_dir / "jars/hypernova.jar")))

    # ---- 1) 日志：最后一个 session ----
    text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    lines = text.splitlines()
    starts = sessions(lines)
    session = lines[starts[-1]:] if starts else lines
    joined = "\n".join(session)

    checks.append(("plugin active", "Hypernova active:" in joined,
                   _first(session, "Hypernova active:") or "no 'Hypernova active' line"))
    checks.append(("no disable reason", "Hypernova disabled:" not in joined,
                   _first(session, "Hypernova disabled:") or "no disable line"))
    checks.append(("no init failure", "Hypernova disabled: init failure" not in joined, ""))
    checks.append(("campaign wiring attached", "attachCampaign: done" in joined,
                   _first(session, "attachCampaign: done") or "attachCampaign never completed"))
    checks.append(("trigger poller raised no error", "TriggerPoller.tick failed" not in joined,
                   _first(session, "TriggerPoller.tick failed") or "no poller error"))

    # ---- 2) 心跳：调度器自计时 ----
    beats = [HEARTBEAT.search(l) for l in session]
    beats = [b for b in beats if b]
    if beats:
        last = beats[-1]
        queued, loaded, failed, ticks, nanos = (int(last.group(3)), int(last.group(4)),
                                                int(last.group(5)), int(last.group(6)),
                                                int(last.group(7)))
        checks.append(("pipeline ticking", ticks > 0, f"ticks={ticks}"))
        checks.append(("scheduler enqueued paths", queued > 0, f"queued={queued}"))
        checks.append(("no scheduler failures", failed == 0, f"failed={failed}"))
        checks.append(("frame budget <= 2 ms (scheduler self-timed)",
                       nanos <= BUDGET_NANOS,
                       f"nanosLastTick={nanos} ({nanos / 1e6:.3f} ms, limit {BUDGET_NANOS / 1e6:.0f} ms)"))
    else:
        checks.append(("pipeline ticking", False, "no HYPERNOVA_TICK heartbeat in last session"))

    # ---- 3) telemetry ----
    if telemetry.is_file():
        rows: list[dict] = []
        bad = 0
        for line in telemetry.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
        checks.append(("telemetry lines are valid JSON", bad == 0, f"bad={bad}"))
        kinds: dict[str, int] = {}
        for r in rows:
            kinds[r.get("kind", "?")] = kinds.get(r.get("kind", "?"), 0) + 1
        checks.append(("telemetry has events", len(rows) > 0, f"n={len(rows)} kinds={kinds}"))
        checks.append(("no non-main-thread rejection", kinds.get("rejected", 0) == 0,
                       f"rejected={kinds.get('rejected', 0)}"))
    else:
        checks.append(("telemetry file exists", False, str(telemetry)))

    # ---- 输出 ----
    width = max(len(name) for name, _, _ in checks)
    ok = True
    for name, passed, detail in checks:
        ok = ok and passed
        print(f"{'PASS' if passed else 'FAIL'}  {name:<{width}}  {detail}")
    print()
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def _first(lines: list[str], needle: str) -> str | None:
    for line in lines:
        if needle in line:
            return line.strip()[:160]
    return None


if __name__ == "__main__":
    sys.exit(main())
