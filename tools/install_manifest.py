#!/usr/bin/env python3
"""为一个真实游戏安装生成、校验并落盘运行时 manifest。

用法:
    python -I tools/install_manifest.py --game-root Starsector-098-260mods
    python -I tools/install_manifest.py --game-root <game> --out <file>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

# `python -I` 不会把脚本目录加入 sys.path；工具内部自行补上。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen_lazy_skip import build_skip, build_skip_v2, write_skip, write_skip_v2  # noqa: E402
from manifest_builder import build_manifest, load_tier_overrides  # noqa: E402
from probe_cache import CACHE_NAME as PROBE_CACHE_NAME  # noqa: E402
from trim_manifest import trim  # noqa: E402
from validate_manifest import Finding, validate  # noqa: E402

DEFAULT_REL = Path(
    "mods/hypernova_infinite_engine/data/config/hypernova/manifest-v1.json"
)


class _Swimmer:
    """生成期间在终端最后一行游来游去的鱼。

    只在 stdout 是终端时启用：进度输出经常被 `| tail`、构建脚本或测试捕获，
    那里塞 \r 会污染日志。全部用 ASCII 字符，避免玩家控制台代码页不是 UTF-8
    时编码炸掉。
    """

    FISH_RIGHT = "><(((o>"
    FISH_LEFT = "<o)))><"
    WATER = "~"
    TICK = 0.12

    def __init__(self, width: int = 54, stream=None, enabled: bool | None = None):
        self.stream = stream if stream is not None else sys.stdout
        self.enabled = self.stream.isatty() if enabled is None else enabled
        if self.enabled:
            # 窗口太窄时鱼会折行，把水面缩到窗口宽度以内。
            try:
                columns = shutil.get_terminal_size().columns
                width = max(12, min(width, columns - 1))
            except OSError:
                pass
        self.width = width
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pos = 0
        self._dir = 1
        self._drawn = False
        self._span = max(1, width - len(self.FISH_RIGHT))

    def start(self) -> None:
        if not self.enabled:
            return
        self._thread = threading.Thread(target=self._run, name="hn-fish", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self.enabled:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        with self._lock:
            self._erase()

    def message(self, text: str) -> None:
        """打印一行真正的输出；先把鱼擦掉，免得两行糊在一起。"""
        with self._lock:
            self._erase()
            self.stream.write(text + "\n")
            self.stream.flush()

    def _erase(self) -> None:
        if not self._drawn:
            return
        self.stream.write("\r" + " " * (self.width + 2) + "\r")
        self.stream.flush()
        self._drawn = False

    def _frame(self) -> str:
        fish = self.FISH_RIGHT if self._dir > 0 else self.FISH_LEFT
        return self.WATER * self._pos + fish + self.WATER * (self._span - self._pos)

    def _run(self) -> None:
        while not self._stop.wait(self.TICK):
            with self._lock:
                self.stream.write("\r" + self._frame())
                self.stream.flush()
                self._drawn = True
            self._pos += self._dir
            if self._pos >= self._span:
                self._pos = self._span
                self._dir = -1
            elif self._pos <= 0:
                self._pos = 0
                self._dir = 1


@dataclass(frozen=True)
class InstallResult:
    full: dict
    runtime: dict
    out: Path
    findings: list[Finding]
    skip_file: Path | None = None
    skip_count: int = 0
    skip_v2_file: Path | None = None
    skip_v2_count: int = 0
    warnings: list[str] = field(default_factory=list)
    probe_cache: Path | None = None


def install(
    game_root: Path,
    out: Path | None = None,
    *,
    tiers: dict[str, str] | None = None,
    scope: str = "mod_non_shader",
    include_core: bool = True,
    include_l2: bool = True,
    max_l1: int = 8000,
    progress=None,
    probe_cache: Path | None = None,
    probe_workers: int = 8,
) -> InstallResult:
    def note(msg: str) -> None:
        if progress is not None:
            progress(msg)

    root = Path(game_root).resolve()
    target = Path(out) if out is not None else root / DEFAULT_REL
    cache_path = (
        Path(probe_cache) if probe_cache is not None
        else target.parent / PROBE_CACHE_NAME
    )
    built = build_manifest(
        root,
        scope=scope,
        include_core=include_core,
        include_l2=include_l2,
        tier_overrides=tiers or {},
        progress=progress,
        probe_cache=cache_path,
        probe_workers=probe_workers,
    )
    note("校验清单")
    findings = validate(built.manifest, root, max_l1=max_l1)
    critical = any(f.severity == "Critical" for f in findings)
    runtime: dict = {}
    skip_file: Path | None = None
    skip_count = 0
    skip_v2_file: Path | None = None
    skip_v2_count = 0
    if not critical:
        note("裁剪清单并写盘")
        runtime = trim(built.manifest)
        target.parent.mkdir(parents=True, exist_ok=True)
        skip_target = target.parent / "lazy-skip-v1.txt"
        skip_rows, _skip_stats = build_skip(runtime)
        skip_v2_rows, _skip_v2_stats = build_skip_v2(built.manifest)
        skip_v2_target = target.parent / "lazy-skip-v2.txt"
        tmp = target.with_name(target.name + ".tmp")
        skip_tmp = skip_target.with_name(skip_target.name + ".tmp")
        skip_v2_tmp = skip_v2_target.with_name(skip_v2_target.name + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(runtime, fh, ensure_ascii=False, separators=(",", ":"))
                fh.flush()
            generation = hashlib.sha256(tmp.read_bytes()).hexdigest()
            header = f"# generation={generation}"
            write_skip(skip_tmp, skip_rows, header=header)
            write_skip_v2(skip_v2_tmp, skip_v2_rows, header=header)
            os.replace(tmp, target)
            try:
                os.replace(skip_tmp, skip_target)
                os.replace(skip_v2_tmp, skip_v2_target)
            except BaseException:
                # manifest 已换新：删除两份旧 skip，绝不留跨代 pair。
                skip_target.unlink(missing_ok=True)
                skip_v2_target.unlink(missing_ok=True)
                raise
        except BaseException:
            tmp.unlink(missing_ok=True)
            skip_tmp.unlink(missing_ok=True)
            skip_v2_tmp.unlink(missing_ok=True)
            raise
        skip_file = skip_target
        skip_count = len(skip_rows)
        skip_v2_file = skip_v2_target
        skip_v2_count = len(skip_v2_rows)
    return InstallResult(
        built.manifest,
        runtime,
        target,
        findings,
        skip_file=skip_file,
        skip_count=skip_count,
        skip_v2_file=skip_v2_file,
        skip_v2_count=skip_v2_count,
        warnings=list(built.warnings),
        probe_cache=cache_path,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--tiers", type=Path,
                        help='JSON: {"mods": {"<modId>": "L1|L2|L3"}}')
    parser.add_argument("--scope", default="mod_non_shader",
                        choices=["mod_non_shader", "all_mod_metadata"])
    parser.add_argument("--no-core", action="store_true")
    parser.add_argument("--no-l2", action="store_true")
    parser.add_argument("--max-l1", type=int, default=8000)
    args = parser.parse_args(argv)
    tiers = load_tier_overrides(args.tiers) if args.tiers else {}
    started = time.monotonic()
    state = {"msg": "准备"}
    fish = _Swimmer()

    def progress(msg: str) -> None:
        # 所有输出都走 fish.message：它持锁并先擦掉鱼，免得两行糊在一起。
        state["msg"] = msg
        fish.message(f"  [{time.monotonic() - started:5.1f}s] {msg}")

    # 心跳：某一个阶段（比如解析几万张贴图）可能要跑几十秒，期间没有回调，
    # 窗口看起来像卡死。每 10 秒补一行"还在干活"，让人知道不是死了。
    stop_beat = threading.Event()

    def heartbeat() -> None:
        while not stop_beat.wait(10.0):
            fish.message(
                f"  [{time.monotonic() - started:5.1f}s] 仍在处理：{state['msg']}"
            )

    beat = threading.Thread(target=heartbeat, daemon=True)
    fish.start()
    beat.start()

    try:
        result = install(
            args.game_root,
            out=args.out,
            tiers=tiers,
            scope=args.scope,
            include_core=not args.no_core,
            include_l2=not args.no_l2,
            max_l1=args.max_l1,
            progress=progress,
        )
    finally:
        stop_beat.set()
        fish.stop()
    stats = result.full["stats"]
    print(
        "full: L1={l1} L2={l2} L3={l3} baked={baked}/{expected} "
        "unresolved={unresolved}".format(
            l1=stats["l1_count"],
            l2=stats["l2_count"],
            l3=stats["l3_count"],
            baked=stats["coverage"]["baked_resolved"],
            expected=stats["coverage"]["baked_expected"],
            unresolved=stats["unresolved_baked_count"],
        )
    )
    for warning in result.warnings:
        print(f"[注意] {warning}")
    for finding in result.findings:
        print(f"[{finding.severity}] {finding.code}: {finding.message}")
    if any(f.severity == "Critical" for f in result.findings):
        print("FATAL: manifest not written (Critical findings)", file=sys.stderr)
        return 1
    print(f"installed: {result.out}")
    print(f"skip={result.skip_count} skip_file={result.skip_file}")
    print(f"skip_v2={result.skip_v2_count} skip_v2_file={result.skip_v2_file}")
    print(f"耗时: {time.monotonic() - started:.1f} 秒")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
