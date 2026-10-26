#!/usr/bin/env python3
"""M1 冒烟检查：读 starsector.log、telemetry 与构建产物，输出 PASS/FAIL。

用法:
    python -I tools/java/smoke-check.py --game Starsector-098-Base

判定口径（全部来自实测，不是假设）：
  - 真身 mod 列表是 <game>/mods/enabled_mods.json（ModManager.getFilename()），
    不是 starsector-core/data/config/enabled_mods.json（从不被读）。
  - telemetry 由 writeTextFileToCommon 落盘为 <saves>/common/hypernova/telemetry.jsonl.data。
  - 「本组件单帧耗时」看心跳里的 nanosLastTick（调度器自计时）；REQ-R1-03 的 P99
    另取 telemetry 里所有 kind="loaded" 的 nanos 计算（两者口径不同，分别断言）。
  - 心跳格式以 HEAD 为准：`HYPERNOVA_TICK <n> SchedulerStats[...]`。旧构建的
    `backlog=<n> stats=SchedulerStats[...]` 一律判 FAIL（C2 provenance）。
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

BANNER = "正在运行 Starsector"
BUDGET_NANOS = 2_000_000  # REQ-R1-03: 2 ms

# HEAD 格式：HypernovaCombatPlugin 打印 "HYPERNOVA_TICK " + tick + " " + scheduler.stats()
HEARTBEAT = re.compile(
    r"HYPERNOVA_TICK (\d+) SchedulerStats\[queued=(\d+), loaded=(\d+), failed=(\d+), "
    r"ticks=(\d+), nanosLastTick=(\d+), backlog=(\d+)\]"
)
# 88a752d 之前的旧格式（本轮冒烟证据曾被它污染，必须显式识别并判红）
OLD_HEARTBEAT = re.compile(r"HYPERNOVA_TICK \d+ backlog=\d+ stats=")
SELFCHECK = re.compile(r"selfcheck: RESULT (\d+)/(\d+) (PASS|FAIL)")


def sessions(lines: list[str]) -> list[int]:
    return [i for i, line in enumerate(lines) if BANNER in line]


def parse_heartbeats(lines: list[str]) -> list[dict[str, int]]:
    """按 HEAD 正则解析心跳；返回字段字典列表（tick/queued/loaded/failed/ticks/nanos/backlog）。"""
    out: list[dict[str, int]] = []
    for line in lines:
        m = HEARTBEAT.search(line)
        if not m:
            continue
        (tick, queued, loaded, failed, ticks, nanos, backlog) = (int(g) for g in m.groups())
        out.append({"tick": tick, "queued": queued, "loaded": loaded, "failed": failed,
                    "ticks": ticks, "nanos": nanos, "backlog": backlog})
    return out


def old_format_heartbeats(lines: list[str]) -> list[str]:
    return [l.strip() for l in lines if OLD_HEARTBEAT.search(l)]


def percentile(values: list[int], p: float) -> int | None:
    """nearest-rank 百分位（不插值）：升序第 ceil(p/100 * n) 个样本。"""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100.0 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def load_telemetry(path: Path) -> tuple[list[dict], int]:
    rows: list[dict] = []
    bad = 0
    if not path.is_file():
        return rows, bad
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            bad += 1
    return rows, bad


def load_config(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def jar_provenance(installed: Path, build: Path) -> tuple[bool, str]:
    """安装的 jar 必须与 build/java/hypernova.jar 的**类内容**一致。

    直接比字节会误判：`jar` 每次打包写入不同的 META-INF 时间戳，同一份 class
    两次打包的 sha 必然不同（本机实测：大小相同 50153B、sha 不同）。因此比对
    「排除了 META-INF 与目录项之后，每个条目的 名称+crc32+大小」的哈希。
    """
    if not installed.is_file():
        return False, f"installed jar missing: {installed}"
    if not build.is_file():
        return False, f"build output missing: {build} (先跑 tools/java/build-mod.sh)"
    a, na = _jar_content_hash(installed)
    b, nb = _jar_content_hash(build)
    if a != b:
        return False, f"installed={na} entries sha={a[:12]} build={nb} entries sha={b[:12]}"
    return True, f"{na} entries sha={a[:12]}"


def _jar_content_hash(path: Path) -> tuple[str, int]:
    import hashlib
    import zipfile

    rows = []
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir() or info.filename.startswith("META-INF/"):
                continue
            rows.append(f"{info.filename}|{info.CRC}|{info.file_size}")
    rows.sort()
    joined = chr(10).join(rows).encode("utf-8")
    return hashlib.sha256(joined).hexdigest(), len(rows)


def _sha(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", required=True)
    ap.add_argument("--skip-provenance", action="store_true",
                    help="仅诊断用：不比较 installed jar 与 build 输出")
    args = ap.parse_args(argv)
    game = Path(args.game)
    core = game / "starsector-core"
    log = core / "starsector.log"
    telemetry = game / "saves" / "common" / "hypernova" / "telemetry.jsonl.data"
    mod_dir = game / "mods" / "hypernova_infinite_engine"
    repo = Path(__file__).resolve().parents[2]
    build_jar = repo / "build" / "java" / "hypernova.jar"
    config = load_config(mod_dir / "data/config/hypernova/hypernova.json")

    checks: list[tuple[str, str, str]] = []  # (name, PASS/FAIL/SKIP, detail)

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append((name, "PASS" if passed else "FAIL", detail))

    def skip(name: str, detail: str = "") -> None:
        checks.append((name, "SKIP", detail))

    # ---- 0) 前置：组件是否真的被启用、产物是否齐 ----
    enabled_file = game / "mods" / "enabled_mods.json"
    enabled: list[str] = []
    if enabled_file.is_file():
        try:
            enabled = json.loads(enabled_file.read_text(encoding="utf-8")).get("enabledMods", [])
        except json.JSONDecodeError:
            enabled = []
    check("hypernova enabled in mods/enabled_mods.json",
          "hypernova_infinite_engine" in enabled, f"enabled_count={len(enabled)}")
    installed_manifest = mod_dir / "data/config/hypernova/manifest-v1.json"
    check("installed manifest present", installed_manifest.is_file(), str(installed_manifest))
    check("installed jar present", (mod_dir / "jars/hypernova.jar").is_file(),
          str(mod_dir / "jars/hypernova.jar"))

    # ---- 0b) provenance：安装的 jar 必须是本次构建产物 ----
    if args.skip_provenance:
        skip("installed jar matches build output",
             "skipped via --skip-provenance (diagnostic only)")
    else:
        ok, detail = jar_provenance(mod_dir / "jars/hypernova.jar", build_jar)
        check("installed jar matches build output", ok, detail)

    # ---- 1) 日志：最后一个 session ----
    text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    lines = text.splitlines()
    starts = sessions(lines)
    session = lines[starts[-1]:] if starts else lines
    joined = "\n".join(session)

    check("plugin active", "Hypernova active:" in joined,
          _first(session, "Hypernova active:") or "no 'Hypernova active' line")
    check("no disable reason", "Hypernova disabled:" not in joined,
          _first(session, "Hypernova disabled:") or "no disable line")
    check("no init failure", "Hypernova disabled: init failure" not in joined, "")
    check("campaign wiring attached", "attachCampaign: done" in joined,
          _first(session, "attachCampaign: done") or "attachCampaign never completed")
    check("trigger poller raised no error", "TriggerPoller.tick failed" not in joined,
          _first(session, "TriggerPoller.tick failed") or "no poller error")

    # ---- 1b) selfcheck（配置显式开启时必须出现 RESULT N/N PASS）----
    probe_paths = int(config.get("startup_probe_paths", 0) or 0)
    if probe_paths > 0:
        m = SELFCHECK.search(joined)
        passed = bool(m) and m.group(1) == m.group(2) and m.group(3) == "PASS"
        check("selfcheck RESULT PASS (startup_probe_paths>0)", passed,
              m.group(0) if m else "no 'selfcheck: RESULT N/N PASS' line")
    else:
        skip("selfcheck RESULT PASS (startup_probe_paths>0)",
             "startup_probe_paths=0 (diagnostic probe disabled; run with >0 to verify)")

    # ---- 2) 心跳：调度器自计时 ----
    old = old_format_heartbeats(session)
    check("heartbeat format is HEAD (no legacy backlog=/stats=)", not old,
          "legacy heartbeat found — log 来自旧构建" if old else "no legacy heartbeat")
    beats = parse_heartbeats(session)
    if beats:
        last = beats[-1]
        check("pipeline ticking", last["ticks"] > 0, f"ticks={last['ticks']}")
        check("scheduler enqueued paths", last["queued"] > 0, f"queued={last['queued']}")
        check("no scheduler failures", last["failed"] == 0, f"failed={last['failed']}")
        nanos = last["nanos"]
        check("last tick nanosLastTick <= 2 ms", nanos <= BUDGET_NANOS,
              f"nanosLastTick={nanos} ({nanos / 1e6:.3f} ms, limit {BUDGET_NANOS / 1e6:.0f} ms)")
    else:
        check("pipeline ticking", False, "no HYPERNOVA_TICK heartbeat in last session")

    # ---- 3) telemetry ----
    rows, bad = load_telemetry(telemetry)
    if telemetry.is_file():
        check("telemetry lines are valid JSON", bad == 0, f"bad={bad}")
        kinds: dict[str, int] = {}
        for r in rows:
            kinds[r.get("kind", "?")] = kinds.get(r.get("kind", "?"), 0) + 1
        check("telemetry has events", len(rows) > 0, f"n={len(rows)} kinds={kinds}")
        check("no non-main-thread rejection", kinds.get("rejected", 0) == 0,
              f"rejected={kinds.get('rejected', 0)}")
        check("telemetry has thread field",
              all("thread" in r for r in rows) if rows else False,
              "missing thread field (REQ-R1-06)" if rows and any("thread" not in r for r in rows)
              else "all rows carry thread")

        # REQ-R1-03：所有 loaded 事件的 P99（不是最后一跳）
        loaded_nanos = [int(r["nanos"]) for r in rows
                        if r.get("kind") == "loaded" and isinstance(r.get("nanos"), (int, float))]
        p50 = percentile(loaded_nanos, 50)
        p99 = percentile(loaded_nanos, 99)
        if p99 is None:
            check("loaded p99 <= 2 ms", False, "no kind=loaded samples in telemetry")
        else:
            check("loaded p99 <= 2 ms", p99 <= BUDGET_NANOS,
                  f"n={len(loaded_nanos)} p50={p50}ns p99={p99}ns ({p99 / 1e6:.3f} ms)")
    else:
        check("telemetry file exists", False, str(telemetry))

    # ---- 输出 ----
    width = max(len(name) for name, _, _ in checks)
    ok = True
    for name, state, detail in checks:
        if state == "FAIL":
            ok = False
        print(f"{state:<4}  {name:<{width}}  {detail}")
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
