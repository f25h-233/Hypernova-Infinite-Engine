# M2.5 通用纹理懒加载 — Task 1 只读可行性 spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用只读探针证明 FR 0.9.7rc2 的启动纹理队列可以被观测、运行时 manifest 能把非 L1 路径标记为可跳过，并产出 M2.5 跳过/代理实现的 GO/NO-GO 硬门禁证据。

**Architecture:** 两个 pre-FR `ClassFileTransformer`：① 向**实际执行**的 `com.fs.graphics.TextureLoader` 加入与 FR donor 同名的 `lambda$queueImage$0` 方法——FR 的 `MethodCopier` 按 `name+descriptor` 判重，看到我们的方法后不再复制 donor 版本，于是队列 worker 执行我们的探针；② 把 `com.fs.graphics.oOoO` 的静态查表方法重命名为 `hypernova$getOriginal`，再加一个同名 wrapper 记录 demand，返回值不变。探针读取由运行时 manifest 生成的紧凑 `lazy-skip-v1.txt`，**不跳过任何加载**；Task 1 只交付形状表、计数、菜单时间与 GO/NO-GO；跳过/代理/按需补加载在 GO 之后以 addendum 形式写 Task 2+。

**Tech Stack:** Java 17（major 61）、ASM 9.1（agent 已内置）、Python 3.14 stdlib（`python -I`）、pytest 9、JUnit 5、`tools/smoke_run.py`、Git Bash（Windows 11）。

**Spec:** `技术笔记-纹理按需加载.md` §5.2（Form B）、§5.3（`ensureLoaded` 契约）、§5.6（状态机）、§7 M2.5、REQ-R2-01..04、INV-10；开工包 `hn-m25-kickoff`；裁决 `hn-m25-decisions`。

---

## Global Constraints

- **宿主锁**：FR **0.9.7rc2**（`fr.jar` md5 `30db0f340f993fb8e8360f5762088b69`）；0.9.7 仅作同线兼容，0.9.5 不支持本模块。游戏 **0.98a-RC8**。版本不匹配 → 只禁用本模块，不阻止启动。
- **agent 顺序**：Hypernova agent 必须在 FR **之前**（M-1b 的 `TextureData` SHA 补丁要求）；本计划依赖这一顺序。若 transformer 看到类里已有 `lambda$queueImage$0`（说明 agent 在 FR 之后），**不覆盖、不猜测**，记日志并放弃。
- **探针不改行为**：`probe=false`（默认）时零新增日志、零 transformer 注册；`probe=true` 时每个纹理仍然走 `loadTextureAsync`。任何无法证明等价的路径 → 停下报告，NO-GO。
- **不改游戏配置**：不动 `enabled_mods.json`、`Miko_*.txt`、`fr.vmparams`、游戏设置；安装只走 `tools/install_agent.py`。**绝不用 `taskkill //F //IM node.exe`**。
- **环境矩阵**：260mods 是 agent-only（256 mods，不含 `hypernova_infinite_engine`），只做启动期菜单冒烟；Base 启用运行期 mod，做运行期正确性。**不要**在 260mods 改 `enabled_mods.json`。
- **日志纪律**：跑门禁前把旧 `starsector.log` / `saves/hypernova/scripts-agent.log` 归档到 `build/m25/logs/`；分析只取**最后一个 `hypernova agent premain` 之后**的会话；FR 锚点用精确 `v0.9.7rc2`。
- **Python**：只用 stdlib，必须能在 `python -I` 下运行；测试从 `tests/tools` 运行（`conftest.py` 已把 `tools/` 加入 `sys.path`）。
- **Java 编译**：`--release 17`、`-encoding UTF-8`、class major 61；agent 不新增依赖（ASM 9.1 已在 `build/agent/lib/asm-9.1.jar` 内置；agent 源码**不得 import 游戏/FR 类**，一律反射/ASM 字符串）。
- **Escape hatch**：若计划里的断言数字/测试顺序与实现不符，按实际修正并在报告里说明，无需请示。**若需求自相矛盾或无法同时满足 → 停下报告，不许挑一半照做。**
- **回滚**：删除启动文件里的 agent 行（`python -I tools/install_agent.py --action uninstall ...`）即回到 M2 基线；探针不写游戏状态。

## Review Focus

1. **Donor 陷阱（最高优先）**：`com/genir/renderer/overrides/loading/textures/TextureLoader` 是 `mergeClass` donor，donor 类本身**从不加载**；必须打实际执行的 `com/fs/graphics/TextureLoader`。证据：探针日志出现 `lambda wired` 且 `queue>0`，而不是只看 class 文件里有没有方法。
2. **agent 顺序**：我们的 transformer 必须看到 pre-FR 原类；若看到已有 donor lambda（说明 FR 先跑），只能安全放弃并让门禁失败。测试：`LazyTransformTest.existingLambdaIsLeftUntouched`。
3. **`oOoO` 形状**：按 descriptor `(Ljava/lang/String;)Lcom/fs/graphics/Object;` + `ACC_STATIC` 查找，必须恰好 1 个候选；0 或 >1 → 不改、记日志。不能只按混淆名硬编码。
4. **探针中立性**：probe 轮的菜单时间必须与 control 同 boot 交错对照在噪声内（±1.5 s）；超出 → 先查环境/漂移，不能把探针开销当成收益或损失。
5. **会话/日志污染**：旧 agent 日志有历史 `premain`；分析取最后一个；旧的 `textures: patched`/`FR missing` 不能当本轮证据。
6. **skip 集口径**：L1 永不进 skip 集（含跨层 L1 优先）；`w<=0/h<=0` 不跳过；`graphics/ui/bottomright*`（FR Blacklist，POT 路径）不跳过；同路径只保留一条（L2 先于 L3）。

---

## Pre-flight（controller 在派发前写入 ledger）

- **Mode:** `pipeline`（默认；任务线性、风险高、计划缺陷需审查层兜底；不使用 wave/worktree）。
- **BASE:** `6d35934`（`git rev-parse HEAD`；M2 已推送，origin/main 同步）。
- **Workspace:** `.superpowers/sdd/2026-11-01-m25-lazy-textures/`（`sdd-workspace` 生成；ledger `progress.md` 首行记 `Mode: pipeline`）。
- **环境事实（2026-11-01 核对）**：
  - 安装的 `fr.jar` 与 `.cache/fr097/fast-rendering-0.9.7rc2/fr.jar` md5 相同；`fr.version.txt` = `v0.9.7rc2`。
  - 260mods runtime manifest：L1 **6,624** / L2 **18,525** / L3 **55,444**；9,110,285 B；260mods 的 mod 目录存在但 `hypernova_infinite_engine` **不在 enabled_mods**（agent-only）。
  - Base runtime manifest：L1 185 / L2 509 / L3 2,612（unique 3,306）；Base 的 mod 已启用。
  - 由 runtime manifest 生成的 skip 文件预期：**260mods skip=73,446**（candidates 73,969；excluded_l1=31、invalid=5、blacklist=9、dup=478）；**Base skip=3,112**（candidates 3,121；blacklist=9）。
  - FR 0.9.7rc2 的 donor 方法名（javap）：`queueImage(String,String)`、`queueImageOptional`、私有 `queueImage(String,String,boolean)`、`lambda$queueImage$0(String,String,boolean)`、`loadTextureAsync(String,String)`、`loadTextureData(String,String)`、`commitAndCacheTexture(String,String,TextureData)`；`ResourceLoaderState.renderProgress` 与 `TextureLoader.knownImages` 均未进混淆映射（按原名合并）。
  - `com.fs.graphics.TextureLoader` 的实际类由 FR 先 rename 7 参 `o00000`→`loadTexture_vanilla`，再 merge donor；donor 类不加载。
  - `com.fs.graphics.oOoO` 的查表方法为 `public static Ò00000(String)Object`；`com.fs.util.C`（FileLoader）有 donor 字段 `mainThread`（`initResourceLoading` 里设为当前线程）。
  - `TextureBuilder.readAndAnalyzeImage(image,false)`：**非 Blacklist 路径 `width=imageWidth, height=imageHeight`（不补 POT）**；Blacklist 才向上取 POT。
- **Rulings（controller 裁决，执行时入 ledger）：**
  1. **R-M25-1（规格冲突）**：REQ-R2-03 旧文写“agent 只在 FR 之后注册 transformer”，与 M-1b 的实装顺序（Hypernova 必须在 FR **之前**）冲突。本里程碑以实装为准：agent 在 FR 前；lazy hook 通过“预置同名 donor 方法 → MethodCopier 跳过 donor”实现，**不改 FR 的 `_vanilla` 布局**。Task 5 必须把这一条回写 spec/ADR。
  2. **R-M25-2（指标口径）**：`Loading image` 只统计 PNG 解码（DDS 命中静默），**不是**纹理队列数。M2.5 的结构指标 = agent `queue` 计数与 `wouldSkip`；`Loading image` 只作次级证据。Task 5 更新 REQ-R2-01 的验收口径。
  3. **R-M25-3（skip 集）**：skip = `(L2 ∪ L3) − L1`，且 `w>0 && h>0`，且排除 `graphics/ui/bottomright*`；运行时再排除 `TEXTURE_ALPHA_ADDER`（材质需要 alpha 变换，按需路径不会复现）。L1 永不跳过。
  4. **R-M25-4（默认开关）**：M2.5 生产开关 `textures.lazy.enabled` **默认 false**；验证通过后再考虑默认开。Task 1 的探针只由 `-Dhypernova.textures.lazy.probe=true` 开启，不读生产开关。
  5. **R-M25-5（任务边界）**：Task 1 是**只读探针 + GO/NO-GO**；Task 2+（跳过/代理/按需补加载/A-B/文档）在 GO 后写 `docs/superpowers/plans/2026-11-01-m25-lazy-textures-addendum.md`，addendum 优先于本计划。这不是计划缺口，是开工包要求的硬门禁。
- **Task 依赖**：Task 1 →（GO）→ addendum Task 2..5；Task 1 无前置。
- **Touches（Task 1）**：
  - 新增：`src/agent/java/hypernova/agent/textures/LazyTextureConfig.java`、`LazySkipIndex.java`、`LazyTextures.java`、`LazyTextureTransformer.java`
  - 修改：`src/agent/java/hypernova/agent/HypernovaAgent.java`
  - 新增工具：`tools/gen_lazy_skip.py`、`tools/m25_probe.py`
  - 新增测试：`tests/agent/java/hypernova/LazyTextureConfigTest.java`、`LazySkipIndexTest.java`、`LazyTransformTest.java`、`tests/tools/test_gen_lazy_skip.py`、`tests/tools/test_m25_probe.py`
  - 新增文档：`docs/m25-spike.md`
  - 游戏安装（不入库）：两侧 `data/config/hypernova/lazy-skip-v1.txt` + agent jar/启动文件

---

### Task 1: 只读可行性探针 + GO/NO-GO 证据

**Files:**
- Create: `src/agent/java/hypernova/agent/textures/LazyTextureConfig.java`
- Create: `src/agent/java/hypernova/agent/textures/LazySkipIndex.java`
- Create: `src/agent/java/hypernova/agent/textures/LazyTextures.java`
- Create: `src/agent/java/hypernova/agent/textures/LazyTextureTransformer.java`
- Modify: `src/agent/java/hypernova/agent/HypernovaAgent.java`（premain 里加 lazy 探针注册块）
- Create: `tools/gen_lazy_skip.py`
- Create: `tools/m25_probe.py`
- Test: `tests/agent/java/hypernova/LazyTextureConfigTest.java`
- Test: `tests/agent/java/hypernova/LazySkipIndexTest.java`
- Test: `tests/agent/java/hypernova/LazyTransformTest.java`
- Test: `tests/tools/test_gen_lazy_skip.py`
- Test: `tests/tools/test_m25_probe.py`
- Create: `docs/m25-spike.md`

**Interfaces:**
- Consumes: `hypernova.agent.AgentLog`（已有）；ASM 9.1（已有）；`tools/smoke_run.py --jvm-arg`（已有）。
- Produces:
  - `record LazyTextureConfig(boolean probe, Path skipFile)`；`static LazyTextureConfig load()`；`public static LazyTextureConfig load(String probeProp, String skipProp, Path configFile)`（测试注入用）
  - `final class LazySkipIndex`；`static LazySkipIndex load(Path) throws Exception`、`boolean contains(String)`、`Dim get(String)`、`int size()`、`int invalid()`、`long loadMillis()`；`record Dim(int w, int h)`
  - `final class LazyTextures`；`static void start(LazyTextureConfig)`、`static void queue(Object,String,String) throws Throwable`、`static void markRenderProgress()`、`static void removeKnown(Object,String)`、`static void probeLookup(String)`、`static Object lookup(String)`、`static void summary()`
  - `final class LazyTextureTransformer implements ClassFileTransformer`（目标 `com/fs/graphics/TextureLoader`、`com/fs/graphics/oOoO`）
  - `tools/gen_lazy_skip.py` CLI：`--manifest --out [--json-out --max-paths]` → stdout JSON stats；输出 `path\tw\th` 行
  - `tools/m25_probe.py` CLI：`--agent-log [--smoke-json --json-out]` → stdout JSON；wiring 不全时 exit 1

- [ ] **Step 1: 写生成器与探针解析器的失败测试**

Create `tests/tools/test_gen_lazy_skip.py`：

```python
import json

from gen_lazy_skip import build_skip, main


def test_build_skip_excludes_l1_invalid_blacklist_and_duplicates():
    manifest = {
        "schema": "hypernova-runtime-1",
        "layers": {
            "L1": [{"path": "graphics/l1.png", "w": 1, "h": 1}],
            "L2": [
                {"path": "graphics/l2.png", "w": 2, "h": 3},
                {"path": "graphics/l1.png", "w": 1, "h": 1},
                {"path": "graphics/l2.png", "w": 2, "h": 3},
            ],
            "L3": [
                {"path": "graphics/l3.png", "w": 4, "h": 5},
                {"path": "graphics/bad.png", "w": 0, "h": 5},
                {"path": "graphics/missing.png"},
                {"path": "graphics/ui/bottomright1.png", "w": 8, "h": 8},
            ],
        },
    }
    rows, stats = build_skip(manifest)
    assert rows == [("graphics/l2.png", 2, 3), ("graphics/l3.png", 4, 5)]
    assert stats["skip"] == 2
    assert stats["excluded_l1"] == 1
    assert stats["excluded_invalid"] == 2
    assert stats["excluded_blacklist"] == 1
    assert stats["excluded_duplicate"] == 1


def test_cli_writes_sorted_lines_and_json(tmp_path):
    manifest = tmp_path / "manifest-v1.json"
    manifest.write_text(json.dumps({
        "layers": {
            "L1": [{"path": "graphics/a.png", "w": 1, "h": 1}],
            "L2": [{"path": "graphics/z.png", "w": 9, "h": 8}],
            "L3": [{"path": "graphics/b.png", "w": 3, "h": 4}],
        }
    }), encoding="utf-8")
    out = tmp_path / "lazy-skip-v1.txt"
    json_out = tmp_path / "stats.json"
    assert main(["--manifest", str(manifest), "--out", str(out),
                 "--json-out", str(json_out)]) == 0
    assert out.read_text(encoding="utf-8") == "graphics/b.png\t3\t4\ngraphics/z.png\t9\t8\n"
    assert not (tmp_path / "lazy-skip-v1.txt.tmp").exists()
    stats = json.loads(json_out.read_text(encoding="utf-8"))["stats"]
    assert stats["skip"] == 2


def test_cli_missing_manifest_exits_2(tmp_path):
    assert main(["--manifest", str(tmp_path / "nope.json"),
                 "--out", str(tmp_path / "out.txt")]) == 2
```

Create `tests/tools/test_m25_probe.py`：

```python
from m25_probe import parse_agent_log


def test_last_session_wins_and_counts_are_parsed():
    text = """2026-11-01T00:00:00Z INFO hypernova agent premain; config=old
2026-11-01T00:00:01Z INFO lazy probe: summary queue=1 wouldSkip=0 lookups=0 demand=0 index=1 types={}
2026-11-01T00:01:00Z INFO hypernova agent premain; config=new
2026-11-01T00:01:01Z INFO lazy probe: index loaded paths=2 invalid=0 in 3 ms; file=x
2026-11-01T00:01:02Z INFO lazy probe: queue lambda hook added to com/fs/graphics/TextureLoader
2026-11-01T00:01:02Z INFO lazy probe: repository lookup hook added to com/fs/graphics/oOoO
2026-11-01T00:01:10Z INFO lazy probe: lambda wired (first queue: type=, path=graphics/a.png)
2026-11-01T00:01:20Z INFO lazy probe: summary queue=10 wouldSkip=7 lookups=4 demand=2 index=2 types={=10}
"""
    result = parse_agent_log(text)
    assert result["summary"] == {"queue": 10, "would_skip": 7, "lookups": 4, "demand": 2, "index": "2"}
    assert result["index_paths"] == 2
    assert result["queue_hook"] is True
    assert result["lookup_hook"] is True
    assert result["wired"] is True
    assert abs(result["skip_fraction"] - 0.7) < 1e-9


def test_no_premain_is_empty_and_not_ok():
    result = parse_agent_log("nothing here\n")
    assert result["wired"] is False
    assert result["summary"] is None
    assert result["skip_fraction"] == 0.0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -I -m pytest tests/tools/test_gen_lazy_skip.py tests/tools/test_m25_probe.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'gen_lazy_skip'` / `'m25_probe'`）。

- [ ] **Step 3: 实现 `tools/gen_lazy_skip.py`**

```python
#!/usr/bin/env python3
"""Generate the M2.5 lazy skip file from the runtime manifest.

Format: UTF-8, LF, one record per line: <path>\\t<w>\\t<h>.
Only L2/L3 paths are eligible. L1 always wins; entries without usable
dimensions and FR's blacklist paths are excluded. The file is written
atomically (sibling .tmp + os.replace).
"""
import argparse
import json
import os
import sys
from pathlib import Path

BLACKLIST_PREFIX = "graphics/ui/bottomright"


def build_skip(manifest: dict) -> tuple[list[tuple[str, int, int]], dict]:
    layers = manifest.get("layers") or {}
    if not isinstance(layers, dict):
        layers = {}
    l1 = {e.get("path") for e in layers.get("L1") or [] if isinstance(e, dict)}
    stats = {
        "l1": len(l1),
        "candidates": 0,
        "skip": 0,
        "excluded_l1": 0,
        "excluded_invalid": 0,
        "excluded_blacklist": 0,
        "excluded_duplicate": 0,
    }
    seen: set[str] = set()
    out: list[tuple[str, int, int]] = []
    for layer in ("L2", "L3"):
        for entry in layers.get(layer) or []:
            if not isinstance(entry, dict):
                continue
            stats["candidates"] += 1
            path = entry.get("path")
            if not isinstance(path, str) or not path:
                stats["excluded_invalid"] += 1
                continue
            if path in l1:
                stats["excluded_l1"] += 1
                continue
            if path.startswith(BLACKLIST_PREFIX):
                stats["excluded_blacklist"] += 1
                continue
            w, h = entry.get("w"), entry.get("h")
            if not isinstance(w, int) or not isinstance(h, int) or w <= 0 or h <= 0:
                stats["excluded_invalid"] += 1
                continue
            if path in seen:
                stats["excluded_duplicate"] += 1
                continue
            seen.add(path)
            out.append((path, w, h))
    out.sort()
    stats["skip"] = len(out)
    return out, stats


def write_atomic(path: Path, rows: list[tuple[str, int, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for p, w, h in rows:
            f.write(f"{p}\t{w}\t{h}\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--json-out", default="")
    ap.add_argument("--max-paths", type=int, default=200_000)
    args = ap.parse_args(argv)
    try:
        data = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FATAL: cannot read manifest {args.manifest}: {exc}", file=sys.stderr)
        return 2
    rows, stats = build_skip(data)
    if len(rows) > args.max_paths:
        print(f"FATAL: skip set {len(rows)} > --max-paths {args.max_paths}", file=sys.stderr)
        return 2
    write_atomic(Path(args.out), rows)
    stats["out"] = str(args.out)
    stats["bytes"] = Path(args.out).stat().st_size
    print(json.dumps(stats, ensure_ascii=False, sort_keys=True))
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"stats": stats}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 实现 `tools/m25_probe.py`**

```python
#!/usr/bin/env python3
"""Summarize one M2.5 probe session from the agent log + smoke JSON."""
import argparse
import json
import re
import sys
from pathlib import Path

INDEX_RE = re.compile(
    r"lazy probe: index loaded paths=(\d+) invalid=(\d+) in (\d+) ms")
SUMMARY_RE = re.compile(
    r"lazy probe: summary queue=(\d+) wouldSkip=(\d+) lookups=(\d+) demand=(\d+) index=(\S+)")


def parse_agent_log(text: str) -> dict:
    lines = text.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if "hypernova agent premain" in line:
            start = i
    session = lines[start:]
    out = {
        "session_lines": len(session),
        "index_paths": 0,
        "index_invalid": 0,
        "index_ms": 0,
        "queue_hook": False,
        "lookup_hook": False,
        "wired": False,
        "summary": None,
        "would_skip_samples": 0,
        "demand_samples": 0,
    }
    for line in session:
        m = INDEX_RE.search(line)
        if m:
            out["index_paths"] = int(m.group(1))
            out["index_invalid"] = int(m.group(2))
            out["index_ms"] = int(m.group(3))
        if "queue lambda hook added" in line:
            out["queue_hook"] = True
        if "repository lookup hook added" in line:
            out["lookup_hook"] = True
        if "lambda wired" in line:
            out["wired"] = True
        if "lazy probe: would-skip " in line:
            out["would_skip_samples"] += 1
        if "lazy probe: demand " in line:
            out["demand_samples"] += 1
        m = SUMMARY_RE.search(line)
        if m:
            out["summary"] = {
                "queue": int(m.group(1)),
                "would_skip": int(m.group(2)),
                "lookups": int(m.group(3)),
                "demand": int(m.group(4)),
                "index": m.group(5),
            }
    s = out["summary"]
    out["skip_fraction"] = (s["would_skip"] / s["queue"]) if s and s["queue"] else 0.0
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-log", required=True)
    ap.add_argument("--smoke-json", default="")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args(argv)
    text = Path(args.agent_log).read_text(encoding="utf-8", errors="replace")
    result = parse_agent_log(text)
    if args.smoke_json:
        try:
            rows = json.loads(Path(args.smoke_json).read_text(encoding="utf-8"))
            result["menu_s"] = rows[0].get("menu_s") if rows else None
        except Exception as exc:
            result["smoke_error"] = str(exc)
    result["ok"] = bool(
        result["queue_hook"] and result["lookup_hook"] and result["wired"]
        and result["summary"] and result["summary"]["queue"] > 0
        and result.get("menu_s") is not None)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -I -m pytest tests/tools/test_gen_lazy_skip.py tests/tools/test_m25_probe.py -q`
Expected: `5 passed`。

- [ ] **Step 6: 写 Java 失败测试**

Create `tests/agent/java/hypernova/LazySkipIndexTest.java`：

```java
package hypernova;

import hypernova.agent.textures.LazySkipIndex;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class LazySkipIndexTest {
    @Test
    void parsesPathsAndDims(@TempDir Path dir) throws Exception {
        Path f = dir.resolve("skip.txt");
        Files.writeString(f, "# comment\n"
                + "graphics/a.png\t10\t20\n"
                + "\n"
                + "graphics/b c.png\t3\t4\n");
        LazySkipIndex idx = LazySkipIndex.load(f);
        assertEquals(2, idx.size());
        assertEquals(0, idx.invalid());
        assertTrue(idx.contains("graphics/a.png"));
        assertEquals(new LazySkipIndex.Dim(10, 20), idx.get("graphics/a.png"));
        assertEquals(new LazySkipIndex.Dim(3, 4), idx.get("graphics/b c.png"));
    }

    @Test
    void rejectsBadDimsAndMalformedLines(@TempDir Path dir) throws Exception {
        Path f = dir.resolve("skip.txt");
        Files.writeString(f, "bad line\n"
                + "graphics/a.png\t0\t20\n"
                + "graphics/b.png\tx\t20\n"
                + "graphics/c.png\t5\t\n");
        LazySkipIndex idx = LazySkipIndex.load(f);
        assertEquals(0, idx.size());
        assertEquals(4, idx.invalid());
    }

    @Test
    void missingFileThrows(@TempDir Path dir) {
        assertThrows(Exception.class, () -> LazySkipIndex.load(dir.resolve("nope.txt")));
    }
}
```

Create `tests/agent/java/hypernova/LazyTextureConfigTest.java`：

```java
package hypernova;

import hypernova.agent.textures.LazyTextureConfig;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class LazyTextureConfigTest {
    @Test
    void probeOffByDefault() {
        LazyTextureConfig c = LazyTextureConfig.load(null, null, null);
        assertFalse(c.probe());
        assertNull(c.skipFile());
    }

    @Test
    void probeAndSkipFileFromProperties() {
        LazyTextureConfig c = LazyTextureConfig.load("true", "C:/x/skip.txt", null);
        assertTrue(c.probe());
        assertEquals(Path.of("C:/x/skip.txt"), c.skipFile());
    }

    @Test
    void skipFileDerivedFromModRoot(@TempDir Path dir) throws Exception {
        Path mod = dir.resolve("mods/hypernova_infinite_engine");
        Path cfg = mod.resolve("data/config/hypernova/hypernova.json");
        Files.createDirectories(cfg.getParent());
        Files.writeString(cfg, "{}");
        LazyTextureConfig c = LazyTextureConfig.load(null, null, cfg);
        assertFalse(c.probe());
        assertEquals(mod.resolve("data/config/hypernova/lazy-skip-v1.txt"), c.skipFile());
    }
}
```

Create `tests/agent/java/hypernova/LazyTransformTest.java`：

```java
package hypernova;

import hypernova.agent.textures.LazyTextureTransformer;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

import java.util.function.Consumer;

import static org.junit.jupiter.api.Assertions.*;

class LazyTransformTest {
    private static final String LOADER = "com/fs/graphics/TextureLoader";
    private static final String REPO = "com/fs/graphics/oOoO";
    private static final String LAMBDA = "lambda$queueImage$0";
    private static final String LAMBDA_DESC = "(Ljava/lang/String;Ljava/lang/String;Z)V";
    private static final String LOOKUP_DESC = "(Ljava/lang/String;)Lcom/fs/graphics/Object;";

    @Test
    void addsQueueLambdaWhenAbsent() {
        byte[] in = classBytes(LOADER, cv -> {
            MethodVisitor mv = cv.visitMethod(Opcodes.ACC_PUBLIC, "loadTextureAsync",
                    "(Ljava/lang/String;Ljava/lang/String;)V", null, null);
            mv.visitCode();
            mv.visitInsn(Opcodes.RETURN);
            mv.visitMaxs(0, 0);
            mv.visitEnd();
        });
        byte[] out = new LazyTextureTransformer().transform(null, LOADER, null, null, in);
        assertNotNull(out);
        ClassNode node = read(out);
        MethodNode lambda = method(node, LAMBDA, LAMBDA_DESC);
        assertNotNull(lambda);
        assertTrue(hasCall(lambda, "hypernova/agent/textures/LazyTextures", "queue"));
    }

    @Test
    void existingLambdaIsLeftUntouched() {
        byte[] in = classBytes(LOADER, cv -> {
            MethodVisitor mv = cv.visitMethod(Opcodes.ACC_PRIVATE | Opcodes.ACC_SYNTHETIC,
                    LAMBDA, LAMBDA_DESC, null, null);
            mv.visitCode();
            mv.visitInsn(Opcodes.RETURN);
            mv.visitMaxs(0, 0);
            mv.visitEnd();
        });
        assertNull(new LazyTextureTransformer().transform(null, LOADER, null, null, in));
    }

    @Test
    void wrapsRepositoryLookup() {
        byte[] in = classBytes(REPO, cv -> {
            MethodVisitor mv = cv.visitMethod(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
                    "lookup", LOOKUP_DESC, null, null);
            mv.visitCode();
            mv.visitInsn(Opcodes.ACONST_NULL);
            mv.visitInsn(Opcodes.ARETURN);
            mv.visitMaxs(0, 0);
            mv.visitEnd();
        });
        byte[] out = new LazyTextureTransformer().transform(null, REPO, null, null, in);
        assertNotNull(out);
        ClassNode node = read(out);
        assertNotNull(method(node, "hypernova$getOriginal", LOOKUP_DESC));
        MethodNode wrapper = method(node, "lookup", LOOKUP_DESC);
        assertNotNull(wrapper);
        assertTrue(hasCall(wrapper, "hypernova/agent/textures/LazyTextures", "probeLookup"));
        assertTrue(hasCall(wrapper, "hypernova/agent/textures/LazyTextures", "lookup"));
    }

    @Test
    void repositoryWithoutUniqueShapeIsUntouched() {
        byte[] in = classBytes(REPO, cv -> {
            for (int i = 0; i < 2; i++) {
                MethodVisitor mv = cv.visitMethod(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
                        "lookup" + i, LOOKUP_DESC, null, null);
                mv.visitCode();
                mv.visitInsn(Opcodes.ACONST_NULL);
                mv.visitInsn(Opcodes.ARETURN);
                mv.visitMaxs(0, 0);
                mv.visitEnd();
            }
        });
        assertNull(new LazyTextureTransformer().transform(null, REPO, null, null, in));
    }

    @Test
    void malformedBytesReturnNull() {
        assertNull(new LazyTextureTransformer().transform(null, LOADER, null, null, new byte[]{1, 2, 3}));
    }

    private static byte[] classBytes(String name, Consumer<ClassVisitor> body) {
        ClassWriter cw = new ClassWriter(0);
        cw.visit(Opcodes.V17, Opcodes.ACC_PUBLIC, name, null, "java/lang/Object", null);
        body.accept(cw);
        cw.visitEnd();
        return cw.toByteArray();
    }

    private static ClassNode read(byte[] bytes) {
        ClassNode node = new ClassNode();
        new ClassReader(bytes).accept(node, 0);
        return node;
    }

    private static MethodNode method(ClassNode node, String name, String desc) {
        for (MethodNode m : node.methods) {
            if (name.equals(m.name) && desc.equals(m.desc)) return m;
        }
        return null;
    }

    private static boolean hasCall(MethodNode method, String owner, String name) {
        return method.instructions.stream()
                .filter(i -> i instanceof MethodInsnNode)
                .map(i -> (MethodInsnNode) i)
                .anyMatch(i -> owner.equals(i.owner) && name.equals(i.name));
    }
}
```

- [ ] **Step 7: 跑 Java 测试确认失败**

Run: `bash tools/java/run-agent-tests.sh Lazy`
Expected: 编译失败（`LazySkipIndex` / `LazyTextureConfig` / `LazyTextureTransformer` 不存在）。

- [ ] **Step 8: 实现 `LazyTextureConfig.java`**

```java
package hypernova.agent.textures;

import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Task 1 probe configuration. Production skip mode is added by the M2.5
 * addendum (textures.lazy.enabled, default false); the probe is debug-only.
 */
public record LazyTextureConfig(boolean probe, Path skipFile) {

    public static LazyTextureConfig load() {
        return load(System.getProperty("hypernova.textures.lazy.probe"),
                System.getProperty("hypernova.textures.lazy.skipFile"),
                locateConfig());
    }

    public static LazyTextureConfig load(String probeProp, String skipProp, Path configFile) {
        boolean probe = probeProp != null && Boolean.parseBoolean(probeProp);
        Path skip = skipProp == null || skipProp.isBlank() ? null : Path.of(skipProp);
        if (skip == null) {
            Path modRoot = modRoot(configFile);
            if (modRoot != null) {
                skip = modRoot.resolve("data/config/hypernova/lazy-skip-v1.txt");
            }
        }
        return new LazyTextureConfig(probe, skip);
    }

    private static Path locateConfig() {
        try {
            var src = LazyTextureConfig.class.getProtectionDomain().getCodeSource();
            if (src != null && src.getLocation() != null) {
                Path jar = Path.of(src.getLocation().toURI());
                Path modRoot = jar.getParent() == null ? null : jar.getParent().getParent();
                if (modRoot != null) {
                    Path f = modRoot.resolve("data/config/hypernova/hypernova.json");
                    if (Files.isRegularFile(f)) return f;
                }
            }
        } catch (Throwable ignored) {
            // fall through to game-root lookup
        }
        Path cwd = Path.of(System.getProperty("user.dir", ".")).toAbsolutePath().normalize();
        Path gameRoot = cwd.getFileName() != null
                && cwd.getFileName().toString().equals("starsector-core")
                ? cwd.getParent() : cwd;
        Path f = gameRoot.resolve("mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json");
        return Files.isRegularFile(f) ? f : null;
    }

    private static Path modRoot(Path configFile) {
        if (configFile != null) {
            Path p = configFile.getParent(); // hypernova
            for (int i = 0; i < 3 && p != null; i++) p = p.getParent(); // config, data, mod root
            if (p != null) return p;
        }
        Path cwd = Path.of(System.getProperty("user.dir", ".")).toAbsolutePath().normalize();
        Path gameRoot = cwd.getFileName() != null
                && cwd.getFileName().toString().equals("starsector-core")
                ? cwd.getParent() : cwd;
        Path mod = gameRoot.resolve("mods/hypernova_infinite_engine");
        return Files.isDirectory(mod) ? mod : null;
    }
}
```

- [ ] **Step 9: 实现 `LazySkipIndex.java`**

```java
package hypernova.agent.textures;

import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;

/** Immutable path -> (w,h) index generated from the runtime manifest. */
public final class LazySkipIndex {
    public record Dim(int w, int h) {
    }

    private final Map<String, Dim> byPath;
    private final int invalid;
    private final long loadMillis;

    private LazySkipIndex(Map<String, Dim> byPath, int invalid, long loadMillis) {
        this.byPath = byPath;
        this.invalid = invalid;
        this.loadMillis = loadMillis;
    }

    public static LazySkipIndex load(Path file) throws Exception {
        long t0 = System.nanoTime();
        Map<String, Dim> map = new HashMap<>(1 << 17);
        int invalid = 0;
        try (BufferedReader reader = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isEmpty() || line.charAt(0) == '#') continue;
                int t1 = line.indexOf('\t');
                int t2 = t1 < 0 ? -1 : line.indexOf('\t', t1 + 1);
                if (t1 <= 0 || t2 <= t1) {
                    invalid++;
                    continue;
                }
                try {
                    int w = Integer.parseInt(line.substring(t1 + 1, t2));
                    int h = Integer.parseInt(line.substring(t2 + 1));
                    if (w <= 0 || h <= 0) {
                        invalid++;
                        continue;
                    }
                    map.put(line.substring(0, t1), new Dim(w, h));
                } catch (NumberFormatException e) {
                    invalid++;
                }
            }
        }
        long ms = (System.nanoTime() - t0) / 1_000_000L;
        return new LazySkipIndex(map, invalid, ms);
    }

    public boolean contains(String path) {
        return path != null && byPath.containsKey(path);
    }

    public Dim get(String path) {
        return byPath.get(path);
    }

    public int size() {
        return byPath.size();
    }

    public int invalid() {
        return invalid;
    }

    public long loadMillis() {
        return loadMillis;
    }
}
```

- [ ] **Step 10: 实现 `LazyTextures.java`（探针版）**

```java
package hypernova.agent.textures;

import hypernova.agent.AgentLog;

import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Task 1 probe state. Every queued texture still goes through the donor's
 * loadTextureAsync; counters only observe. The production skip/proxy path is
 * the M2.5 addendum.
 */
public final class LazyTextures {
    private static final AtomicLong QUEUE_TOTAL = new AtomicLong();
    private static final AtomicLong QUEUE_WOULD_SKIP = new AtomicLong();
    private static final AtomicLong LOOKUP_TOTAL = new AtomicLong();
    private static final AtomicLong DEMAND_DISTINCT = new AtomicLong();
    private static final Map<String, AtomicLong> TYPES = new ConcurrentHashMap<>();
    private static final Map<String, Long> DEMAND_FIRST = new ConcurrentHashMap<>();
    private static final AtomicBoolean WIRED = new AtomicBoolean();
    private static final AtomicBoolean SUMMARY_STARTED = new AtomicBoolean();

    private static volatile LazySkipIndex index;
    private static volatile Path skipFile;

    private static volatile boolean loadResolved;
    private static volatile Method loadAsyncMethod;
    private static volatile boolean renderResolved;
    private static volatile Field renderProgressField;
    private static volatile boolean knownResolved;
    private static volatile Field knownImagesField;

    private LazyTextures() {
    }

    public static void start(LazyTextureConfig config) {
        if (!config.probe()) return;
        skipFile = config.skipFile();
        Thread loader = new Thread(LazyTextures::loadIndex, "Hypernova-Lazy-Index");
        loader.setDaemon(true);
        loader.start();
        if (SUMMARY_STARTED.compareAndSet(false, true)) {
            Thread summary = new Thread(LazyTextures::summaryLoop, "Hypernova-Lazy-Summary");
            summary.setDaemon(true);
            summary.start();
            Runtime.getRuntime().addShutdownHook(
                    new Thread(LazyTextures::summary, "Hypernova-Lazy-Summary-Shutdown"));
        }
        AgentLog.info("lazy probe: started; skipFile=" + skipFile);
    }

    private static void loadIndex() {
        try {
            Path f = skipFile;
            if (f == null) {
                AgentLog.info("lazy probe: no skip file resolved; probe counts stay 0");
                return;
            }
            if (!Files.isRegularFile(f)) {
                AgentLog.info("lazy probe: skip file missing: " + f);
                return;
            }
            LazySkipIndex idx = LazySkipIndex.load(f);
            index = idx;
            AgentLog.info("lazy probe: index loaded paths=" + idx.size()
                    + " invalid=" + idx.invalid() + " in " + idx.loadMillis()
                    + " ms; file=" + f);
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: index load failed; probe counts stay 0", t);
        }
    }

    /**
     * Called from the injected queue lambda on a texture worker, before the
     * original load. Must preserve the donor's exception semantics: any
     * Throwable from loadTextureAsync propagates to the generated catch.
     */
    public static void queue(Object loader, String type, String path) throws Throwable {
        try {
            QUEUE_TOTAL.incrementAndGet();
            TYPES.computeIfAbsent(type == null ? "" : type, k -> new AtomicLong()).incrementAndGet();
            if (WIRED.compareAndSet(false, true)) {
                AgentLog.info("lazy probe: lambda wired (first queue: type=" + type
                        + ", path=" + path + ")");
            }
            LazySkipIndex idx = index;
            if (idx != null && idx.contains(path)) {
                long n = QUEUE_WOULD_SKIP.incrementAndGet();
                if (n <= 20) AgentLog.info("lazy probe: would-skip " + path);
            }
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: counter failed; continuing", t);
        }
        loadAsync(loader, type, path);
    }

    private static void loadAsync(Object loader, String type, String path) throws Throwable {
        Method m = loadAsyncMethod;
        if (m == null && !loadResolved) {
            synchronized (LazyTextures.class) {
                m = loadAsyncMethod;
                if (m == null && !loadResolved) {
                    try {
                        m = loader.getClass().getDeclaredMethod(
                                "loadTextureAsync", String.class, String.class);
                        m.setAccessible(true);
                        loadAsyncMethod = m;
                        AgentLog.info("lazy probe: loadTextureAsync resolved on "
                                + loader.getClass().getName());
                    } catch (Throwable t) {
                        AgentLog.fail("lazy probe: loadTextureAsync missing; queued texture skipped", t);
                    } finally {
                        loadResolved = true;
                    }
                }
            }
        }
        if (m == null) return; // fail-open: never crash the game for a probe
        try {
            m.invoke(loader, type, path);
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            throw cause == null ? e : cause;
        }
    }

    public static void markRenderProgress() {
        Field f = renderProgressField;
        if (f == null && !renderResolved) {
            synchronized (LazyTextures.class) {
                f = renderProgressField;
                if (f == null && !renderResolved) {
                    try {
                        Class<?> c = Class.forName("com.fs.starfarer.loading.ResourceLoaderState",
                                false, LazyTextures.class.getClassLoader());
                        f = c.getDeclaredField("renderProgress");
                        f.setAccessible(true);
                        renderProgressField = f;
                    } catch (Throwable t) {
                        AgentLog.fail("lazy probe: renderProgress missing; progress hint disabled", t);
                    } finally {
                        renderResolved = true;
                    }
                }
            }
        }
        if (f == null) return;
        try {
            f.setBoolean(null, true);
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: renderProgress set failed", t);
        }
    }

    public static void removeKnown(Object loader, String path) {
        Field f = knownImagesField;
        if (f == null && !knownResolved) {
            synchronized (LazyTextures.class) {
                f = knownImagesField;
                if (f == null && !knownResolved) {
                    try {
                        f = loader.getClass().getDeclaredField("knownImages");
                        f.setAccessible(true);
                        knownImagesField = f;
                    } catch (Throwable t) {
                        AgentLog.fail("lazy probe: knownImages missing; optional cleanup disabled", t);
                    } finally {
                        knownResolved = true;
                    }
                }
            }
        }
        if (f == null) return;
        try {
            Object value = f.get(loader);
            if (value instanceof Set<?> set) set.remove(path);
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: knownImages remove failed", t);
        }
    }

    /** Demand accounting for paths that a real skip implementation would proxy. */
    public static void probeLookup(String path) {
        try {
            LOOKUP_TOTAL.incrementAndGet();
            LazySkipIndex idx = index;
            if (idx == null || !idx.contains(path)) return;
            if (DEMAND_FIRST.putIfAbsent(path, System.nanoTime()) == null) {
                long n = DEMAND_DISTINCT.incrementAndGet();
                if (n <= 20) AgentLog.info("lazy probe: demand " + path);
            }
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: lookup counter failed; continuing", t);
        }
    }

    /** Task 1: no proxy. The addendum replaces this with the proxy/materialize path. */
    public static Object lookup(String path) {
        return null;
    }

    private static void summaryLoop() {
        while (true) {
            try {
                Thread.sleep(10_000);
            } catch (InterruptedException e) {
                return;
            }
            summary();
        }
    }

    public static void summary() {
        try {
            LazySkipIndex idx = index;
            AgentLog.info("lazy probe: summary queue=" + QUEUE_TOTAL.get()
                    + " wouldSkip=" + QUEUE_WOULD_SKIP.get()
                    + " lookups=" + LOOKUP_TOTAL.get()
                    + " demand=" + DEMAND_DISTINCT.get()
                    + " index=" + (idx == null ? "none" : idx.size())
                    + " types=" + types());
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: summary failed", t);
        }
    }

    private static String types() {
        StringBuilder sb = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, AtomicLong> e : TYPES.entrySet()) {
            if (!first) sb.append(',');
            first = false;
            sb.append(e.getKey()).append('=').append(e.getValue().get());
        }
        return sb.append('}').toString();
    }
}
```

- [ ] **Step 11: 实现 `LazyTextureTransformer.java`**

```java
package hypernova.agent.textures;

import hypernova.agent.AgentLog;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Label;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

/**
 * Task 1 probe transformer.
 *
 * <p>Hook 1: com/fs/graphics/TextureLoader is the executed class. FR renames
 * its 7-arg o00000 to loadTexture_vanilla and merges the donor
 * com/genir/renderer/overrides/loading/textures/TextureLoader. MethodCopier
 * skips donor methods whose name+descriptor already exists, so adding the
 * donor's lambda here makes the queue workers execute our probe.
 *
 * <p>Hook 2: com/fs/graphics/oOoO.get is the only global texture lookup. It is
 * renamed to hypernova$getOriginal and wrapped; the wrapper records demand and
 * returns exactly the same value.
 */
public final class LazyTextureTransformer implements ClassFileTransformer {
    public static final String TEXTURE_LOADER = "com/fs/graphics/TextureLoader";
    public static final String REPOSITORY = "com/fs/graphics/oOoO";
    private static final String HOOK = "hypernova/agent/textures/LazyTextures";
    private static final String LAMBDA = "lambda$queueImage$0";
    private static final String LAMBDA_DESC = "(Ljava/lang/String;Ljava/lang/String;Z)V";
    private static final String LOOKUP_DESC = "(Ljava/lang/String;)Lcom/fs/graphics/Object;";
    private static final String RENAMED_LOOKUP = "hypernova$getOriginal";

    @Override
    public byte[] transform(ClassLoader loader, String className, Class<?> redefined,
                            ProtectionDomain protectionDomain, byte[] bytes) {
        if (className == null || redefined != null || bytes == null) return null;
        try {
            if (TEXTURE_LOADER.equals(className)) return patchQueueLambda(bytes);
            if (REPOSITORY.equals(className)) return patchRepository(bytes);
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: transform failed for " + className + "; left untouched", t);
        }
        return null;
    }

    private static byte[] patchQueueLambda(byte[] bytes) {
        ClassReader reader = new ClassReader(bytes);
        ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
        boolean[] present = {false};
        ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
            @Override
            public MethodVisitor visitMethod(int access, String name, String desc,
                                             String signature, String[] exceptions) {
                if (LAMBDA.equals(name) && LAMBDA_DESC.equals(desc)) present[0] = true;
                return super.visitMethod(access, name, desc, signature, exceptions);
            }

            @Override
            public void visitEnd() {
                if (!present[0]) {
                    addQueueLambda(super.visitMethod(
                            Opcodes.ACC_PRIVATE | Opcodes.ACC_SYNTHETIC,
                            LAMBDA, LAMBDA_DESC, null, null));
                }
                super.visitEnd();
            }
        };
        reader.accept(visitor, 0);
        if (present[0]) {
            AgentLog.info("lazy probe: " + LAMBDA + " already present in " + TEXTURE_LOADER
                    + "; transform skipped (agent ordered after FR?)");
            return null;
        }
        AgentLog.info("lazy probe: queue lambda hook added to " + TEXTURE_LOADER);
        return writer.toByteArray();
    }

    private static void addQueueLambda(MethodVisitor mv) {
        Label start = new Label();
        Label end = new Label();
        Label handler = new Label();
        Label rethrow = new Label();
        Label done = new Label();
        mv.visitCode();
        mv.visitTryCatchBlock(start, end, handler, "java/lang/Throwable");
        mv.visitLabel(start);
        mv.visitVarInsn(Opcodes.ALOAD, 0);
        mv.visitVarInsn(Opcodes.ALOAD, 1);
        mv.visitVarInsn(Opcodes.ALOAD, 2);
        mv.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK, "queue",
                "(Ljava/lang/Object;Ljava/lang/String;Ljava/lang/String;)V", false);
        mv.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK, "markRenderProgress", "()V", false);
        mv.visitLabel(end);
        mv.visitJumpInsn(Opcodes.GOTO, done);
        mv.visitLabel(handler);
        mv.visitFrame(Opcodes.F_SAME1, 0, null, 1, new Object[]{"java/lang/Throwable"});
        mv.visitVarInsn(Opcodes.ILOAD, 3);
        mv.visitJumpInsn(Opcodes.IFEQ, rethrow);
        mv.visitInsn(Opcodes.POP);
        mv.visitVarInsn(Opcodes.ALOAD, 0);
        mv.visitVarInsn(Opcodes.ALOAD, 2);
        mv.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK, "removeKnown",
                "(Ljava/lang/Object;Ljava/lang/String;)V", false);
        mv.visitJumpInsn(Opcodes.GOTO, done);
        mv.visitLabel(rethrow);
        mv.visitFrame(Opcodes.F_SAME1, 0, null, 1, new Object[]{"java/lang/Throwable"});
        mv.visitInsn(Opcodes.ATHROW);
        mv.visitLabel(done);
        mv.visitFrame(Opcodes.F_SAME, 0, null, 0, null);
        mv.visitInsn(Opcodes.RETURN);
        mv.visitMaxs(0, 0);
        mv.visitEnd();
    }

    private static byte[] patchRepository(byte[] bytes) {
        ClassReader reader = new ClassReader(bytes);
        ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
        String[] found = {null};
        int[] count = {0};
        ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
            @Override
            public MethodVisitor visitMethod(int access, String name, String desc,
                                             String signature, String[] exceptions) {
                if (LOOKUP_DESC.equals(desc) && (access & Opcodes.ACC_STATIC) != 0) {
                    count[0]++;
                    found[0] = name;
                    return super.visitMethod(access, RENAMED_LOOKUP, desc, signature, exceptions);
                }
                return super.visitMethod(access, name, desc, signature, exceptions);
            }

            @Override
            public void visitEnd() {
                if (count[0] == 1) {
                    addRepositoryWrapper(super.visitMethod(
                            Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
                            found[0], LOOKUP_DESC, null, null));
                }
                super.visitEnd();
            }
        };
        reader.accept(visitor, 0);
        if (count[0] != 1) {
            AgentLog.info("lazy probe: " + REPOSITORY + " lookup shape not unique (candidates="
                    + count[0] + "); transform skipped");
            return null;
        }
        AgentLog.info("lazy probe: repository lookup hook added to " + REPOSITORY
                + " (method=" + found[0] + ")");
        return writer.toByteArray();
    }

    private static void addRepositoryWrapper(MethodVisitor mv) {
        Label miss = new Label();
        mv.visitCode();
        mv.visitVarInsn(Opcodes.ALOAD, 0);
        mv.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK, "probeLookup",
                "(Ljava/lang/String;)V", false);
        mv.visitVarInsn(Opcodes.ALOAD, 0);
        mv.visitMethodInsn(Opcodes.INVOKESTATIC, REPOSITORY, RENAMED_LOOKUP,
                LOOKUP_DESC, false);
        mv.visitVarInsn(Opcodes.ASTORE, 1);
        mv.visitVarInsn(Opcodes.ALOAD, 1);
        mv.visitJumpInsn(Opcodes.IFNULL, miss);
        mv.visitVarInsn(Opcodes.ALOAD, 1);
        mv.visitInsn(Opcodes.ARETURN);
        mv.visitLabel(miss);
        mv.visitFrame(Opcodes.F_APPEND, 1, new Object[]{"java/lang/Object"}, 0, null);
        mv.visitVarInsn(Opcodes.ALOAD, 0);
        mv.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK, "lookup",
                "(Ljava/lang/String;)Ljava/lang/Object;", false);
        mv.visitTypeInsn(Opcodes.CHECKCAST, "com/fs/graphics/Object");
        mv.visitInsn(Opcodes.ARETURN);
        mv.visitMaxs(0, 0);
        mv.visitEnd();
    }
}
```

- [ ] **Step 12: 接线 `HypernovaAgent.premain`**

在 `StartupTimelineTransformer` 注册之后、`TexturePatchConfig` 块之前插入（import 三个类）：

```java
            try {
                LazyTextureConfig lazy = LazyTextureConfig.load();
                if (lazy.probe()) {
                    if (!frPresent()) {
                        AgentLog.info("lazy probe: FR missing; probe disabled");
                    } else {
                        instrumentation.addTransformer(new LazyTextureTransformer(), false);
                        LazyTextures.start(lazy);
                        AgentLog.info("lazy probe transformer registered");
                    }
                }
            } catch (Throwable t) {
                AgentLog.fail("lazy probe init failed; continuing", t);
            }
```

- [ ] **Step 13: 构建并跑 agent / 全量测试**

Run: `bash tools/java/build-agent.sh`
Expected: `OK: .../build/agent/hypernova.agent.jar`；jar 内含 `hypernova/agent/textures/LazyTextures.class`。

Run: `bash tools/java/run-agent-tests.sh Lazy`
Expected: Lazy 测试全绿（`LazySkipIndexTest` 3 + `LazyTextureConfigTest` 3 + `LazyTransformTest` 5 = 11；以实际 found 数为准）。

Run: `bash tools/java/run-tests.sh`
Expected: 103/103（mod 测试不受影响）。

Run: `python -I -m pytest tests/tools -q`
Expected: 既有 2 个 `test_smoke_check.py` stale 夹具失败仍在；新增 5 passed。**不要**把它们当本轮回归。

- [ ] **Step 14: 生成两侧 skip 文件并断言数量**

Run:

```bash
python -I tools/gen_lazy_skip.py \
  --manifest Starsector-098-260mods/mods/hypernova_infinite_engine/data/config/hypernova/manifest-v1.json \
  --out Starsector-098-260mods/mods/hypernova_infinite_engine/data/config/hypernova/lazy-skip-v1.txt
python -I tools/gen_lazy_skip.py \
  --manifest Starsector-098-Base/mods/hypernova_infinite_engine/data/config/hypernova/manifest-v1.json \
  --out Starsector-098-Base/mods/hypernova_infinite_engine/data/config/hypernova/lazy-skip-v1.txt
```

Expected stdout（260mods）：`"skip": 73446`、`"excluded_l1": 31`、`"excluded_invalid": 5`、`"excluded_blacklist": 9`、`"excluded_duplicate": 478`。
Expected stdout（Base）：`"skip": 3112`、`"excluded_blacklist": 9`。
若数字不符：先确认 manifest 未被重新安装/更新；按实际修正并在报告里记录偏差（Escape hatch），不要手改 skip 文件。

- [ ] **Step 15: 装 agent（两侧）**

Run:

```bash
python -I tools/install_agent.py --game Starsector-098-Base --env base --action install
python -I tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite --action install
```

Expected：`installed: .../mods/hypernova_infinite_engine/jars/hypernova.agent.jar`；启动文件已含 agent 行且在 FR 之前（若原本已装，输出 `no vmparams change`）。

- [ ] **Step 16: 归档旧日志**

Run:

```bash
mkdir -p build/m25/logs
mv Starsector-098-Base/starsector-core/starsector.log build/m25/logs/base-starsector.log.$(date +%s) 2>/dev/null || true
mv Starsector-098-Base/saves/hypernova/scripts-agent.log build/m25/logs/base-agent.log.$(date +%s) 2>/dev/null || true
mv Starsector-098-260mods/starsector-core/starsector.log build/m25/logs/260-starsector.log.$(date +%s) 2>/dev/null || true
mv Starsector-098-260mods/saves/hypernova/scripts-agent.log build/m25/logs/260-agent.log.$(date +%s) 2>/dev/null || true
```

注意：agent 日志里还有 scripts cache 的历史；`m25_probe.py` 只看最后一个 `premain`，但归档能让证据更干净。

- [ ] **Step 17: Base 探针冒烟**

Run:

```bash
python -I tools/smoke_run.py --profile base --rounds 1 --wait-menu 300 \
  --jvm-arg=-Dhypernova.textures.lazy.probe=true \
  --json-out build/m25/smoke-base-probe.json
python -I tools/m25_probe.py \
  --agent-log Starsector-098-Base/saves/hypernova/scripts-agent.log \
  --smoke-json build/m25/smoke-base-probe.json \
  --json-out build/m25/probe-base.json
```

Expected：
- smoke：`menu_s` 有值（Base 基线约 11 s；本机波动允许 ±3 s），`ok=true`。
- probe：`queue_hook=true`、`lookup_hook=true`、`wired=true`、`summary.queue>0`、`index_paths≈3112`、exit 0。
- `starsector.log` 无 `VerifyError`/`ClassFormatError`；无新增 `Failed to load texture`（与 control 相同或更少）。

- [ ] **Step 18: 260mods control/probe 交错 2+2**

Run（逐条执行；每条之间不要并行）：

```bash
python -I tools/smoke_run.py --profile miko-lite --rounds 1 --wait-menu 300 \
  --json-out build/m25/ab-260-c1.json
python -I tools/smoke_run.py --profile miko-lite --rounds 1 --wait-menu 300 \
  --jvm-arg=-Dhypernova.textures.lazy.probe=true \
  --json-out build/m25/ab-260-p1.json
python -I tools/smoke_run.py --profile miko-lite --rounds 1 --wait-menu 300 \
  --json-out build/m25/ab-260-c2.json
python -I tools/smoke_run.py --profile miko-lite --rounds 1 --wait-menu 300 \
  --jvm-arg=-Dhypernova.textures.lazy.probe=true \
  --json-out build/m25/ab-260-p2.json
```

Expected：四轮都 `ok=true`；control 中位 ≈ 48–50 s（M3 基线 48.1 s 的量级；跨 boot 漂移允许更大，只做同 boot 交错对照）；probe 与 control 中位差 ≤1.5 s。若 >1.5 s：先查环境漂移/后台进程，再补 1+1；仍超 → 记录并降级为“探针开销待查”，不得宣称收益。

分析 probe 轮。agent 日志跨轮追加，**在 p1 之后、c2 之前**先复制快照；p2 用 live log（最后一个 `premain` 会话）：

```bash
cp Starsector-098-260mods/saves/hypernova/scripts-agent.log \
   build/m25/logs/260-agent-p1.log
```

```bash
python -I tools/m25_probe.py \
  --agent-log build/m25/logs/260-agent-p1.log \
  --smoke-json build/m25/ab-260-p1.json \
  --json-out build/m25/probe-260-p1.json
python -I tools/m25_probe.py \
  --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
  --smoke-json build/m25/ab-260-p2.json \
  --json-out build/m25/probe-260-p2.json
```

注意：两个 probe 会话的计数应同量级；若差异大，先查 `index loaded` 是否为 73,446 且 `summary.index` 非 `none`（索引未加载会静默 0）。

- [ ] **Step 19: 写 `docs/m25-spike.md`**

至少包含：

1. **形状表（0.9.7rc2，E1/E2）**：donor/target、方法/descriptor、runtime 名、为什么 hook 在 `com.fs.graphics.TextureLoader` 而不是 donor；`oOoO` 查表；`FileLoader.mainThread`；`Object` 字段映射；`TextureBuilder` 非 POT 事实（记录 Task 2 的尺寸/UV 依据）。
2. **探针设计**：预置同名 lambda → MethodCopier 跳过 donor；`oOoO` rename+wrapper；为什么行为不变。
3. **实测**：Base/260mods 的 smoke JSON、probe JSON 摘要；`queue`、`wouldSkip`、`skip_fraction`、`lookups`、`demand`、`index_paths`、`menu_s`；control/probe 菜单对照；任何偏差与 Escape hatch 记录。
4. **GO/NO-GO 判定**（按下一节标准）与理由；若 NO-GO，写限制与下一个候选（FileLoader hook / 后台预取 / 接受 M2）。
5. **Task 2–5 草案**（4–7 任务、回滚开关、fail-open、A/B 方案）——只列验收与边界，完整代码在 addendum。

- [ ] **Step 20: 提交**

```bash
git add docs/superpowers/plans/2026-11-01-m25-lazy-textures.md \
        src/agent/java/hypernova/agent/textures/LazyTextureConfig.java \
        src/agent/java/hypernova/agent/textures/LazySkipIndex.java \
        src/agent/java/hypernova/agent/textures/LazyTextures.java \
        src/agent/java/hypernova/agent/textures/LazyTextureTransformer.java \
        src/agent/java/hypernova/agent/HypernovaAgent.java \
        tools/gen_lazy_skip.py tools/m25_probe.py \
        tests/agent/java/hypernova/LazyTextureConfigTest.java \
        tests/agent/java/hypernova/LazySkipIndexTest.java \
        tests/agent/java/hypernova/LazyTransformTest.java \
        tests/tools/test_gen_lazy_skip.py tests/tools/test_m25_probe.py \
        docs/m25-spike.md
git commit -m "feat(m25): add read-only lazy texture probe and GO/NO-GO evidence" \
    -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

注意：两侧游戏目录里的 `lazy-skip-v1.txt`、agent jar、启动文件备份**不入库**；`.gitignore` 已覆盖游戏安装/构建产物；**禁止 `git add -A`**。

---

## Gate：GO/NO-GO（硬门禁，Task 1 出口）

Task 1 完成后，controller 按以下标准裁决并写入 ledger；**GO 才派 Task 2+**。

**G1 接线（必须）：**
- Base 与 260mods 的 probe 会话都有 `queue lambda hook added`、`repository lookup hook added`、`lambda wired`；
- `summary.queue > 0`；`starsector.log` 无 `VerifyError`/`ClassFormatError`；游戏到主菜单。

**G2 结构（必须）：**
- 260mods `skip_fraction ≥ 0.50`（预期 ~0.90）；
- `demand`（distinct skip-set lookups）`≤ 0.20 × index_paths`（260mods ≤ ~14,689）；若超过，说明菜单/加载期确实需要大量非 L1 纹理，按需补加载会把收益吃回去。
- 若 `wouldSkip` 的结构与 manifest 明显不符（例如 queue 只有几千），先查探针是否只看到部分队列；记录实际口径。

**G3 中立性（必须）：**
- 同 boot 交错 control/probe 的菜单中位差 ≤1.5 s（2+2；超了补 1+1 再判）。

**G4 正确性（必须）：**
- probe 轮无新增 `Failed to load texture`、无新异常；Base 菜单正常、260mods 菜单正常。

**裁决：**
- 全满足 → **GO**：写 addendum（Task 2 跳过/代理/按需补加载；Task 3 安装集成；Task 4 A/B+VRAM；Task 5 文档/规格/记忆/终审），进入实现。
- G1 失败 → **NO-GO（钩子不可用）**：不动生产代码；在 `docs/m25-spike.md` 写限制与下一个候选（`FileLoader.Ó00000` + 1×1 占位；或接受 M2 基线）。
- G2 失败 → **NO-GO（收益结构不成立）**：写限制；可选改为“只跳过 never-used 的 L3 子集”，需用户另行裁决。
- G3 失败但 G1/G2/G4 通过 → 先查探针开销；若确认是探针本身（例如 map 查找在每帧 `getSprite` 上过重），优化后再判，不直接 NO-GO。
- 边界情况 → 呈给用户裁决，不自行扩大范围。

---

## Tasks 2–5（GO 后写 addendum；此处只定验收/边界）

> 开工包明确“GO 才派 Task 2+”。以下为 Task 1 报告里必须给出的任务草案；完整代码/测试在 `2026-11-01-m25-lazy-textures-addendum.md`，addendum 优先。

### Task 2（草案）：跳过 + 代理 + 按需补加载（生产代码）
- `textures.lazy.enabled`（默认 false）+ 系统属性覆盖；FR 0.9.7rc2/0.9.7 + 游戏 0.98a-RC8 + 形状门；任何失败 fail-open。
- `queue`：skip 集且 type≠`TEXTURE_ALPHA_ADDER` → 注册 proxy（`com.fs.graphics.Object`，真实 w/h、stringId/path、id=0）；否则 `loadTextureAsync`。
- `lookup`：引擎 miss 且有 proxy → 主线程 materialize（反射 donor 7 参默认路径，拿新 Object，逐字段拷贝进 proxy；写回 `TextureLoader` path cache）；非主线程只返回 proxy。
- `noteEngineHit`：引擎命中且 proxy 未就绪 → 从真实 Object 拷贝字段（免费 materialize）。
- 失败：每 path 最多 1 次重试；失败保留占位并记录，不崩。
- 验收：Base 菜单 + 手动读档 + 战斗场景无缺失；260mods 菜单；计数显示 skip/materialize；回滚开关关闭后行为回到 M2。

### Task 3（草案）：安装集成
- `install_manifest.py` 生成 skip 文件（原子写、校验 Critical 拒写）；`smoke-prepare.sh`/`smoke-restore.sh` 同步；发行包 manifest 源改用 M2（排队任务，可与本任务合并或单列）。
- 验收：新装/重装/回滚后 skip 文件与 manifest 同代；缺失时模块 fail-open。

### Task 4（草案）：A/B + VRAM + 正确性
- 同 boot 交错 3+3：control（lazy=false）vs treatment（lazy=true）；菜单中位、`Loading image`、agent skip/materialize 计数、working set（`Get-Process`/`tasklist`）、GPU 显存（`nvidia-smi` 可用时）。
- 正确性：Base 菜单 + 读档 + 一战；260mods 菜单；无 `Failed to load texture`/缺失截图。
- 验收阈值：菜单中位改善 ≥2.0 s 或 working set/VRAM 改善 ≥5%（二者至少一项；否则记录“收益不成立”并呈用户裁决）；正确性为底线。

### Task 5（草案）：结果、规格、回滚、记忆、终审
- `docs/m25-results.md`；spec M2.5 段、REQ-R2-01/03 口径、ADR-05 补记；`textures.lazy.enabled=false` 回滚说明；memory 钩子；最终 opus 全分支 review。

---

## Self-Review（controller 写完计划后逐项过）

1. **Spec 覆盖**：Task 1 只覆盖 REQ-R2-01/02/03/04 的**可行性证据**，不实现 R2-02 的代理填充/INV-10 的尺寸约束——这些明确落在 Task 2（addendum）。R-M25-5 记录了这个边界，不是漏项。R-M25-1 解决 REQ-R2-03 的“after FR”与实装冲突；R-M25-2 解决 `Loading image` 口径。Task 5 负责回写 spec。
2. **占位符扫描**：无 TBD/悬空 stub；`LazyTextures.lookup` 在 Task 1 明确返回 null（探针），addendum 替换为 proxy；每个测试/命令都有期望。
3. **类型/签名一致**：`LazyTextures.queue(Object,String,String)` ↔ transformer 生成 descriptor `(Ljava/lang/Object;Ljava/lang/String;Ljava/lang/String;)V`；`LazyTextures.lookup(String)Object` ↔ wrapper `(Ljava/lang/String;)Ljava/lang/Object;`；`LazySkipIndex.Dim` ↔ 测试；`LazyTextureConfig.load(String,String,Path)` ↔ 测试。
4. **Review Focus 的测试归属**：donor 陷阱 → `LazyTransformTest` + probe `wired`；agent 顺序 → `existingLambdaIsLeftUntouched`；`oOoO` 形状 → `repositoryWithoutUniqueShapeIsUntouched`；skip 集口径 → `test_build_skip_excludes...`；日志污染 → `test_last_session_wins...`；中立性 → Step 18 的 2+2。
5. **比例**：Task 1 代码集中在 4 个 agent 小类 + 2 个工具；Task 2–5 只给验收/边界，完整代码在 GO 后的 addendum——符合开工包的硬门禁，避免在未验证的钩子上写第二份未测代码。

---

## Exit criteria（M2.5 Task 1 出口）

- Task 1 的 Python 5 测试 + Java Lazy 测试全绿；`run-tests.sh` 103/103；既有 pytest 2 个 stale 失败不扩大。
- `build-agent.sh` 成功；两侧 skip 文件数量与预期一致（260mods 73,446 / Base 3,112）。
- Base 与 260mods 的 probe 冒烟有 `wired`/`queue>0`，无 VerifyError；control/probe 2+2 中立。
- `docs/m25-spike.md` 含形状表、实测、GO/NO-GO 判定与 Task 2–5 草案；提交入库。
- controller 在 ledger 记 Rulings、G1–G4 结果、下一动作（GO → addendum；NO-GO → 限制与候选）。
