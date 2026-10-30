# M-1e 发布前验证 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在发布/内测前补齐三项验证——**no-FR 臂**（收益是否依赖宿主）、**受控 OS 缓存测量**（时间数字是否可信）、**Java 17 审计**（运行时是否偷偷依赖 Java 21）；只加验证工具与报告，**不新开功能**。

**Architecture:** 用可复现的工具把环境差异做成文件而不是手工改启动参数：`m1e_profile.py` 从 `Miko_Lite.txt` 派生真正的 no-FR profile（同时移除 `fr.jar` classpath token 与 `-javaagent:fr.agent.jar`，保留 Hypernova agent）；`smoke_run.py` 增加 no-FR profile、额外 `-D` 参数与进程 I/O 计数器；`m1b_measure.py` 增加 `--expect-no-fr` 正向证据（日志无 FR、agent 记 `FR missing`、无 `Failed to load texture`）；`m1e_rounds.py` 编排多轮并记录 OS 缓存状态；`m1e_java_audit.py` 逐类检查 major 61 + 扫描 Java 21 API；`run-*-tests.sh` 支持用 Base JRE 17 跑全量测试。最后把三门禁的原始值写进 `docs/m1e-results.md` 并回写规格 §7。

**Tech Stack:** Python 3（stdlib：`argparse`/`json`/`ctypes`/`zipfile`/`statistics`/`subprocess`）、Git Bash、PowerShell（提权清 standby list）、Java 17（`--release 17`，class major 61）、Base 自带 JRE 17（Zulu 17.0.10）、JUnit Platform 1.11.4、Miko JDK 28（仅作 260mods 运行时）。

**Spec:** `技术笔记-纹理按需加载.md` §7「M-1e 发布前验证」。计划是论证；规格是权威，冲突时按规格裁决并记入 ledger。

---

## 开工前实测（2026-10-31，controller 亲测，写进 ledger）

### A. 当前环境事实

| 项 | 实测 |
|---|---|
| 仓库 HEAD | `8b2cf2b`（`docs(m1e): define the release-readiness milestone`） |
| 260mods 启动档 | `Miko_Lite.txt`（CRLF），`-javaagent:../mods/hypernova_infinite_engine/jars/hypernova.agent.jar` 在 `-javaagent:fr.agent.jar` **之前**；classpath 首 token 是 `fr.jar` |
| FR 形态 | **没有** `mods/Fast Rendering` 目录；FR 只是 `starsector-core/fr.jar` + `fr.agent.jar`。从 classpath 删掉 `fr.jar` + 删掉 `-javaagent:fr.agent.jar` 就是真正的 no-FR |
| 启用 mod 列表 | 活动文件是 `mods/enabled_mods.json`（**256** 个 id）；`starsector-core/data/config/enabled_mods.json`（66 个）不是活动列表 |
| `com/genir` 引用 | 272 个 mod jar 中只有两个：`VramOptimizer` 的 `ModPlugin` 与我们的 `ScriptCacheTransformer`。VOpt 的 `Version.getVersion()` 调用在 `try/catch Throwable` 内、且由 `VOpt.frEnabled` 守卫；FR 缺席时走 `DDSOverriding.HandleDDS()`（手动 DDS），**预计不崩** |
| 系统 Java | `21.0.10`（`javac 21.0.10`）；Base `jre/bin/java.exe` = **17.0.10**（无 javac）；Miko `jdk-28+13` |
| JUnit | `junit-platform-console-standalone` **1.11.4**，multi-release 含 major 61，可在 JRE 17 运行 |
| 权限 | 当前 shell **非管理员**；本机无 Sysinternals/RAMMap。清 standby list 需要提权（`SeProfileSingleProcessPrivilege`） |
| 游戏进程 | 当前没有 `java.exe`/`javaw.exe` 在跑 |
| 历史数字 | 菜单 76.9–98.2 s（M-1d-2 三轮 83.2/77.6/77.1）；法线基线 **30,378**；B 组 144.7 s、A 组 85.5 s、A 组法线 **0**；key 旧 15 次中位 7,606 ms、新 3 次 458 ms |

### B. M-1e 的三项门禁（规格 §7 原文摘要）

1. **no-FR 臂**：真无 FR（agent 未加载且 `com.genir.renderer.Version` 不在 classpath；只删 `-javaagent` 不算）。验收：正常到主菜单；日志无 `Fast Rendering: v0.9.5`；`scripts` 出现 `FR missing; scripts cache disabled` 且不崩；`textures` 仍 `patched`；`normal_before_menu` 相对 B 组下降 ≥80%；无 `Failed to load texture`。停止：无法在不破坏 260mods 的前提下移除 FR → 改用 Base + 目标 mod 子集并写明差异；不得把“只删 agent 行”当 no-FR。
2. **控制 OS 缓存的收益测量**：清/控 Windows 文件缓存后至少 3 轮热启动；报告中位数与分布；明确冷/热口径；不得用单轮宣称收益。停止：无法控制 OS 缓存 → 报告不确定性，结论降级为“观察”，不得宣称净收益。
3. **Java 21 审计 + JRE17 全量**：逐个 `javap -verbose` 检查 `build/agent/classes/**` 的 major（不仅 `HypernovaAgent`）；搜索 Java 21 特有 API；用 Base 自带 JRE 17 跑全量 agent 测试。验收：所有 agent class major=61；无 21-only API；JRE17 下全绿（symlink assumption 可 abort）。停止：JRE17 失败 → 修代码或阻塞发布；不得用系统 Java 21 全绿代替。

---

## Global Constraints

- **只做验证与工具，不改生产代码**（`src/**` 不改）；若 JRE17 测试失败，先报告 controller 裁决，不自行改生产代码。
- Java 编译仍必须 `--release 17`；新增/修改的 Python 工具只用 stdlib，UTF-8，`python -I` 可运行。
- **绝不修改 `Miko_Lite.txt`**；no-FR 只写派生副本 `Miko_Lite_nofr.txt`。`install_agent.py` 若报告 `install:`（说明它改了启动档）→ 停下检查行尾，不得继续。
- **不得永久破坏 260mods 启动文件**；不得把“只删 `-javaagent` 行”当 no-FR。
- 杀进程只杀 `smoke_run` 自己 spawn 的 PID；**禁止** `taskkill //F //IM node.exe`，也不要用 `taskkill /IM java.exe` 误杀别的 Java 进程。
- 同一时间只跑一个游戏实例；每轮开始前 `tasklist /FI "IMAGENAME eq java.exe"` 确认没有残留。
- M-1e **不升级 FR**（继续 pin 0.9.5）；FR 0.9.7rc2 的兼容改造是后续会话的独立任务。
- 不宣称菜单时间收益；菜单数字只作分布记录（历史 76.9–98.2 s 已覆盖 77.6）。
- 不公开 `docs/audit-2026-10-31-coremod-ecosystem.md`（内部证据，未入库）。
- 每个任务一个独立 commit；消息前缀 `feat(m1e):` / `test(m1e):` / `docs(m1e):`，并附 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。
- 本计划按 **pipeline** 执行（ledger 首部记录 `Mode: pipeline`）。

## Escape Hatch

- 若计划里的断言数字、测试顺序、文件路径或方法描述符与实际实现不符 → **按实际修正并报告**（写进 `task-N-report.md`），无需请示。
- 若需求自相矛盾或无法同时满足 → **停下报告 controller，不许挑一半照做**。写清矛盾原文、为什么不能同时成立、建议裁决。
- Pipeline 下只改本任务 `Touches:` 声明内的文件；需要越界 → 停下报告，等 controller 裁决。
- **no-FR 臂**：若 260mods 在真 no-FR 下无法到主菜单（或 VOpt/其它 mod 崩溃）→ 按规格停止条件改用 **Base + 目标 mod 子集**，并在报告中写明环境差异；不得回退成“只删 agent 行”。
- **OS 缓存**：若无法提权清 standby（本机默认如此）→ 记录 `cache_control=none`，3 轮热启动只作“观察”，不得声称净收益；不要为了“看起来受控”而伪造口径。
- **JRE17**：若测试失败 → 停，附完整日志；是否改代码由 controller 裁决（规格允许“修代码或阻塞发布”，但 M-1e 不默认改生产代码）。

## Review Focus

1. **假 no-FR**：`fr.jar` 仍在 classpath，或只删了 `-javaagent:fr.agent.jar` → `HypernovaAgent.frPresent()` 仍为 true，臂不成立。Task 1 的 `convert` 拒绝残留、`m1b_measure --expect-no-fr` 要求 `fr_present=false` + agent `FR missing`。
2. **no-FR 下 VOpt 崩溃**：`VOpt.ModPlugin` 引用 `com/genir/renderer/Version`。必须在 no-FR 下正常到主菜单并看到 VOpt 手动 DDS 回退；Task 1 Step 7/8 抓 `FR not enabled, handling DDS files manually` 或等价日志。
3. **OS 缓存状态不明却宣称收益**：没有 I/O 证据或 purge 未成功时，结果只能写成“观察”。Task 2 的 `read_bytes_menu` + `cache_control` 字段；`m1e_rounds` 在 purge 失败时把 `cache_control` 置 `none`。
4. **JRE17 runner 偷偷回退系统 Java 21**：脚本里残留裸 `java -jar`，或用 `java` 启动但没设 `JAVA_RUNTIME`。Task 3 的静态守卫 + 运行日志首行 `runtime:`。
5. **审计只查了 `HypernovaAgent`**：现有 `build-agent.sh` 只断言一个类。Task 3 的审计覆盖 `build/agent/classes/**` 全部 class，并在任一 major≠61 时非零退出。
6. **派生 profile 反向污染源文件**：工具写错目标或原地改写 `Miko_Lite.txt`。Task 1 的 `test_cli_does_not_modify_source` + CLI 拒绝 `--src == --out`。

## File Structure

| 路径 | 责任 | 任务 |
|---|---|---|
| `tools/m1e_profile.py` | 从现有启动档派生真 no-FR profile；失败关闭；不碰源文件 | 1 |
| `tests/tools/test_m1e_profile.py` | 派生规则、幂等、CRLF、拒绝残留、源文件不变 | 1 |
| `tools/smoke_run.py` | 新增 `miko-lite-nofr` profile、`--jvm-arg`、进程 I/O 计数、agent 行解析 | 1/2 |
| `tests/tools/test_smoke_run.py` | profile/命令顺序/I/O 探针 | 1 |
| `tools/m1b_measure.py` | `--expect-no-fr`、`fr_present`、`FR missing`、`Failed to load texture` | 1 |
| `tests/tools/test_m1b_measure.py` | no-FR session 选择与门禁 | 1 |
| `tools/clear_standby.ps1` | 提权清 Windows standby list；非提权返回 `NOT_ELEVATED` | 2 |
| `tools/m1e_rounds.py` | 多轮编排、purge、JSON 汇总（menu/read bytes/key） | 2 |
| `tests/tools/test_m1e_rounds.py` | 统计、命令构造、非提权路径 | 2 |
| `tools/m1e_java_audit.py` | class major 61 全量审计 + Java 21 API 扫描 | 3 |
| `tests/tools/test_m1e_java_audit.py` | class 头解析、jar 扫描、API 正则、CLI 门禁 | 3 |
| `tools/java/run-agent-tests.sh` | `JAVA_RUNTIME` 覆盖，默认系统 java | 3 |
| `tools/java/run-tests.sh` | 同上（mod 测试） | 3 |
| `tests/tools/test_jre17_runner.py` | 两个 runner 的静态守卫 | 3 |
| `docs/m1e-results.md` | 三项证据、原始值、中位数/分布、口径、回滚 | 4 |
| `技术笔记-纹理按需加载.md` §7 | M-1e 状态与实测回写 | 4 |

---

### Task 1: 真 no-FR 启动档 + 测量工具

**Files:**
- Create: `tools/m1e_profile.py`
- Create: `tests/tools/test_m1e_profile.py`
- Modify: `tools/smoke_run.py`（PROFILES、`build_command`、`--jvm-arg`、`agent_results`）
- Create: `tests/tools/test_smoke_run.py`
- Modify: `tools/m1b_measure.py`（`--expect-no-fr`、`fr_present`、`FR missing`、`Failed to load texture`）
- Modify: `tests/tools/test_m1b_measure.py`

**Interfaces:**
- Consumes: `smoke_run.PROFILES`、`smoke_run.one_round`、`smoke_run.agent_results`；`m1b_measure.measure`。
- Produces:
  - `tools/m1e_profile.py`：`ProfileError(Exception)`；`convert(text: str) -> tuple[str, dict]`；`main(argv: list[str] | None = None) -> int`。
  - `smoke_run.build_command(java: str, vmparams_arg: str, direct: list[str], jvm_args: list[str]) -> list[str]`。
  - `smoke_run.PROFILES["miko-lite-nofr"]`（`game=Starsector-098-260mods`、`java=jdk-28+13/bin/java.exe`、`vmparams=../Miko_Lite_nofr.txt`、`cwd=starsector-core`）。
  - `smoke_run.agent_results` 新增键：`fr_missing`、`textures_patched`、`textures_mismatch`、`key_ready`、`key_breakdown`。
  - `m1b_measure.measure(..., expect_no_fr: bool = False)`；输出新增 `fr_present`、`fr_missing_disabled`、`failed_texture_lines`、`expect_no_fr`。

**Dependencies:** 无。
**Touches:** `tools/m1e_profile.py`、`tests/tools/test_m1e_profile.py`、`tools/smoke_run.py`、`tests/tools/test_smoke_run.py`、`tools/m1b_measure.py`、`tests/tools/test_m1b_measure.py`。

- [ ] **Step 1: 写 `tools/m1e_profile.py` 的失败测试**

创建 `tests/tools/test_m1e_profile.py`：

```python
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("m1e_profile", REPO / "tools" / "m1e_profile.py")
profile = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(profile)

SOURCE = (
    "-Xmx10g\r\n"
    "-javaagent:../mods/hypernova_infinite_engine/jars/hypernova.agent.jar\r\n"
    "-javaagent:fr.agent.jar\r\n"
    "-classpath fr.jar;janino.jar;starfarer.api.jar\r\n"
    "com.fs.starfarer.StarfarerLauncher"
)


def test_convert_removes_fr_from_agent_and_classpath():
    out, stats = profile.convert(SOURCE)
    assert "fr.agent.jar" not in out
    assert "-classpath janino.jar;starfarer.api.jar" in out
    assert "hypernova.agent.jar" in out
    assert stats == {
        "removed_fr_agent_lines": 1,
        "removed_fr_classpath_tokens": 1,
        "classpath_lines": 1,
    }


def test_convert_preserves_crlf():
    out, _ = profile.convert(SOURCE)
    assert "\r\n" in out
    assert "\n" not in out.replace("\r\n", "")


def test_convert_is_idempotent():
    once, _ = profile.convert(SOURCE)
    twice, stats = profile.convert(once)
    assert twice == once
    assert stats["removed_fr_agent_lines"] == 0
    assert stats["removed_fr_classpath_tokens"] == 0


def test_convert_keeps_lookalike_tokens():
    text = SOURCE.replace("janino.jar", "notfr.jar;fr.jar.bak")
    out, stats = profile.convert(text)
    assert "notfr.jar" in out
    assert "fr.jar.bak" in out
    assert stats["removed_fr_classpath_tokens"] == 1


def test_convert_refuses_missing_hypernova_agent():
    text = SOURCE.replace(
        "-javaagent:../mods/hypernova_infinite_engine/jars/hypernova.agent.jar\r\n", "")
    with pytest.raises(profile.ProfileError, match="Hypernova agent"):
        profile.convert(text)


def test_convert_refuses_split_classpath():
    text = SOURCE.replace(
        "-classpath fr.jar;janino.jar;starfarer.api.jar",
        "-classpath\r\nfr.jar;janino.jar")
    with pytest.raises(profile.ProfileError, match="same line"):
        profile.convert(text)


def test_convert_refuses_duplicate_classpath():
    text = SOURCE.replace(
        "-classpath fr.jar;janino.jar;starfarer.api.jar",
        "-classpath fr.jar;janino.jar\n-classpath other.jar")
    with pytest.raises(profile.ProfileError, match="multiple -classpath"):
        profile.convert(text)


def test_cli_does_not_modify_source(tmp_path):
    src = tmp_path / "Miko_Lite.txt"
    src.write_bytes(SOURCE.encode("utf-8"))
    out = tmp_path / "Miko_Lite_nofr.txt"

    assert profile.main(["--src", str(src), "--out", str(out)]) == 0
    assert src.read_bytes() == SOURCE.encode("utf-8")
    assert out.exists()
    assert "fr.agent.jar" not in out.read_text(encoding="utf-8")


def test_cli_refuses_overwrite_without_force(tmp_path):
    src = tmp_path / "Miko_Lite.txt"
    src.write_bytes(SOURCE.encode("utf-8"))
    out = tmp_path / "Miko_Lite_nofr.txt"
    out.write_text("old", encoding="utf-8")

    assert profile.main(["--src", str(src), "--out", str(out)]) == 2
    assert out.read_text(encoding="utf-8") == "old"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/tools/test_m1e_profile.py -q`
Expected: FAIL（`m1e_profile.py` 不存在）。

- [ ] **Step 3: 实现 `tools/m1e_profile.py`**

```python
#!/usr/bin/env python3
"""Derive a true no-Fast-Rendering launch profile from an existing profile.

The no-FR arm must remove FR from the *classpath* as well as from the
`-javaagent` list. `HypernovaAgent.frPresent()` is
`Class.forName("com.genir.renderer.Version")`, so deleting only the agent line
leaves FR present and the arm proves nothing about a missing FR.

The tool writes a new file and never touches the source. It fails closed when
the source has no Hypernova agent line (the derived profile would not exercise
our agent) or when the layout is not understood.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

FR_AGENT_LINE = "-javaagent:fr.agent.jar"
FR_CLASSPATH_TOKENS = {"fr.jar", "fr.agent.jar"}
HYPERNOVA_AGENT_TOKEN = "hypernova.agent.jar"
MAIN_CLASS = "com.fs.starfarer.StarfarerLauncher"


class ProfileError(Exception):
    """The source profile cannot be converted without guessing."""


def _newline_for(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _classpath_tokens(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("-classpath"):
        return []
    rest = stripped[len("-classpath"):].strip()
    return [t.strip() for t in rest.split(";") if t.strip()]


def convert(text: str) -> tuple[str, dict]:
    newline = _newline_for(text)
    lines = text.splitlines()
    out: list[str] = []
    removed_agents = 0
    removed_tokens = 0
    classpath_lines = 0

    for line in lines:
        stripped = line.strip()
        if stripped == FR_AGENT_LINE:
            removed_agents += 1
            continue
        if stripped.startswith("-classpath"):
            rest = stripped[len("-classpath"):].strip()
            if not rest:
                raise ProfileError(
                    "-classpath must carry its jars on the same line; "
                    "split -classpath lines are not supported")
            classpath_lines += 1
            if classpath_lines > 1:
                raise ProfileError("multiple -classpath lines are not supported")
            tokens = [t.strip() for t in rest.split(";") if t.strip()]
            kept = [t for t in tokens if t not in FR_CLASSPATH_TOKENS]
            removed_tokens += len(tokens) - len(kept)
            if not kept:
                raise ProfileError("-classpath would become empty")
            indent = line[:len(line) - len(line.lstrip())]
            out.append(f"{indent}-classpath {';'.join(kept)}")
            continue
        out.append(line)

    if classpath_lines == 0:
        raise ProfileError("no -classpath line found")
    if not any(HYPERNOVA_AGENT_TOKEN in line for line in out):
        raise ProfileError(
            "Hypernova agent line is missing; install the agent into the source "
            "profile first (tools/install_agent.py)")
    if any(line.strip() == FR_AGENT_LINE for line in out):
        raise ProfileError("FR agent line survived conversion")
    for line in out:
        if any(t in FR_CLASSPATH_TOKENS for t in _classpath_tokens(line)):
            raise ProfileError("FR jar survived conversion")

    nonempty = [line.strip() for line in out if line.strip()]
    if not nonempty or nonempty[-1] != MAIN_CLASS:
        raise ProfileError(
            f"main class must stay last; got {nonempty[-1] if nonempty else '<empty>'!r}")

    stats = {
        "removed_fr_agent_lines": removed_agents,
        "removed_fr_classpath_tokens": removed_tokens,
        "classpath_lines": classpath_lines,
    }
    return newline.join(out) + newline, stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    src = Path(args.src)
    out = Path(args.out)
    if src.resolve() == out.resolve():
        print("FATAL: --out must differ from --src", file=sys.stderr)
        return 2
    if out.exists() and not args.force:
        print(f"FATAL: {out} exists; pass --force to overwrite", file=sys.stderr)
        return 2

    raw = src.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    try:
        converted, stats = convert(text)
    except ProfileError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 1

    payload = converted.encode("utf-8")
    if bom:
        payload = b"\xef\xbb\xbf" + payload
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(payload)
    print(f"wrote {out}: removed {stats['removed_fr_agent_lines']} FR agent line(s), "
          f"{stats['removed_fr_classpath_tokens']} classpath token(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/tools/test_m1e_profile.py -q`
Expected: PASS。

- [ ] **Step 5: 写 `smoke_run` / `m1b_measure` 的失败测试**

创建 `tests/tools/test_smoke_run.py`：

```python
import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("smoke_run", REPO / "tools" / "smoke_run.py")
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)


def test_nofr_profile_points_at_generated_file():
    profile = smoke.PROFILES["miko-lite-nofr"]
    assert profile["game"] == "Starsector-098-260mods"
    assert profile["java"] == "jdk-28+13/bin/java.exe"
    assert profile["vmparams"] == "../Miko_Lite_nofr.txt"
    assert profile["cwd"] == "starsector-core"


def test_build_command_puts_jvm_args_before_argfile():
    cmd = smoke.build_command(
        "java.exe", "../Miko_Lite.txt",
        ["-DlaunchDirect=true"], ["-Dhypernova.textures=false"])
    assert cmd == [
        "java.exe",
        "-DlaunchDirect=true",
        "-Dhypernova.textures=false",
        "@../Miko_Lite.txt",
    ]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only I/O counters")
def test_io_read_bytes_for_own_process():
    value = smoke.io_read_bytes(os.getpid())
    assert value is not None
    assert value > 0
```

在 `tests/tools/test_m1b_measure.py` 末尾追加：

```python
def write_nofr_log(path, normals_before, normals_after, failures=0, old_fr_session=True):
    lines = []
    if old_fr_session:
        lines.append("100000 [main] INFO  com.genir.renderer.agent.Agent  - Fast Rendering: v0.9.5")
        lines.append("100010 [Thread-3] INFO  com.fs.graphics.TextureLoader  - "
                     "Loading image [cache/old_normal.png]")
    t = 0
    for i in range(failures):
        t += 1
        lines.append(f"{t} [Thread-3] ERROR com.fs.graphics.TextureLoader  - "
                     f"Failed to load texture [broken{i}]")
    for i in range(normals_before):
        t += 10
        lines.append(f"{t} [Thread-3] INFO  com.fs.graphics.TextureLoader  - "
                     f"Loading image [cache/x{i}_normal.png]")
    t += 1000
    lines.append(f"{t} [Thread-21] INFO  sound.H  - "
                 "Playing music with id [miscallenous_main_menu.ogg]")
    for i in range(normals_after):
        t += 10
        lines.append(f"{t} [Thread-3] INFO  com.fs.graphics.TextureLoader  - "
                     f"Loading image [cache/y{i}_normal.png]")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


NOFR_AGENT = (
    "2026-01-01T00:00:00Z INFO hypernova agent premain; config=x\n"
    "2026-01-01T00:00:01Z INFO FR missing; scripts cache disabled\n"
    "2026-01-01T00:00:02Z INFO textures: patched org/dark/shaders/util/TextureData\n"
)


def _run_measure(log, agent, out, *extra):
    return subprocess.run(
        [sys.executable, str(ROOT / "tools/m1b_measure.py"),
         "--log", str(log), "--agent-log", str(agent),
         "--baseline", "100", "--json-out", str(out), *extra],
        capture_output=True, text=True)


def test_nofr_session_selected_by_rollover_and_gate_passes(tmp_path):
    log = tmp_path / "starsector.log"
    agent = tmp_path / "agent.log"
    out = tmp_path / "out.json"
    write_nofr_log(log, 0, 2)
    agent.write_text(NOFR_AGENT, encoding="utf-8")

    r = _run_measure(log, agent, out, "--expect-no-fr")
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["session_source"] == "rollover"
    assert d["fr_present"] is False
    assert d["fr_missing_disabled"] is True
    assert d["failed_texture_lines"] == 0
    assert d["gate_ok"] is True


def test_expect_no_fr_fails_when_fr_anchor_present(tmp_path):
    log = tmp_path / "starsector.log"
    agent = tmp_path / "agent.log"
    out = tmp_path / "out.json"
    write_log(log, 0, 0)
    agent.write_text(NOFR_AGENT, encoding="utf-8")

    r = _run_measure(log, agent, out, "--expect-no-fr")
    assert r.returncode == 1
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["fr_present"] is True
    assert d["gate_ok"] is False


def test_expect_no_fr_requires_agent_fr_missing_line(tmp_path):
    log = tmp_path / "starsector.log"
    agent = tmp_path / "agent.log"
    out = tmp_path / "out.json"
    write_nofr_log(log, 0, 0)
    agent.write_text(
        "2026-01-01T00:00:00Z INFO hypernova agent premain; config=x\n"
        "2026-01-01T00:00:02Z INFO textures: patched org/dark/shaders/util/TextureData\n",
        encoding="utf-8")

    r = _run_measure(log, agent, out, "--expect-no-fr")
    assert r.returncode == 1
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["fr_missing_disabled"] is False
    assert d["gate_ok"] is False


def test_expect_no_fr_fails_on_failed_texture(tmp_path):
    log = tmp_path / "starsector.log"
    agent = tmp_path / "agent.log"
    out = tmp_path / "out.json"
    write_nofr_log(log, 0, 0, failures=1)
    agent.write_text(NOFR_AGENT, encoding="utf-8")

    r = _run_measure(log, agent, out, "--expect-no-fr")
    assert r.returncode == 1
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["failed_texture_lines"] == 1
    assert d["gate_ok"] is False
```

- [ ] **Step 6: 跑测试确认失败**

Run: `python -m pytest tests/tools/test_smoke_run.py tests/tools/test_m1b_measure.py -q`
Expected: FAIL（`miko-lite-nofr` 不存在、`build_command`/`io_read_bytes` 不存在、`--expect-no-fr` 未实现）。

- [ ] **Step 7: 实现 `smoke_run` 改动**

1. 顶部 import 增加 `import ctypes`。
2. `PROFILES` 增加：

```python
    "miko-lite-nofr": {
        "game": "Starsector-098-260mods",
        "java": "jdk-28+13/bin/java.exe",
        "vmparams": "../Miko_Lite_nofr.txt",
        "cwd": "starsector-core",
    },
```

3. 在 `one_round` 前增加命令构造与 I/O 探针：

```python
def build_command(java: str, vmparams_arg: str, direct: list[str],
                  jvm_args: list[str]) -> list[str]:
    """JVM props and the argfile are all JVM args; -D must come before @file."""
    return [java, *direct, *jvm_args, f"@{vmparams_arg}"]


if sys.platform == "win32":
    from ctypes import wintypes

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.GetProcessIoCounters.argtypes = [wintypes.HANDLE, ctypes.POINTER(_IoCounters)]
    _k32.GetProcessIoCounters.restype = wintypes.BOOL
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.CloseHandle.restype = wintypes.BOOL

    def io_read_bytes(pid: int) -> int | None:
        # PROCESS_QUERY_LIMITED_INFORMATION works for same-user processes.
        handle = _k32.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            counters = _IoCounters()
            if not _k32.GetProcessIoCounters(handle, ctypes.byref(counters)):
                return None
            return int(counters.ReadTransferCount)
        finally:
            _k32.CloseHandle(handle)
else:
    def io_read_bytes(pid: int) -> int | None:
        return None
```

4. `one_round` 内把 `cmd` 改为：

```python
    cmd = build_command(str(java), vmparams_arg, direct, args.jvm_arg)
```

5. 主菜单后、退出前记录 I/O：

```python
    read_menu = io_read_bytes(proc.pid)

    if args.linger > 0:
        print(f">>> 停留 {args.linger:.0f}s（给 CacheWriter 稳定窗口）")
        time.sleep(args.linger)

    read_exit = io_read_bytes(proc.pid)
    how = graceful_stop(proc)
```

返回字典增加：

```python
        "read_bytes_menu": read_menu,
        "read_bytes_exit": read_exit,
```

6. `agent_results` 的循环增加分支：

```python
        elif "FR missing; scripts cache disabled" in line:
            out["fr_missing"] = line
        elif "textures: patched" in line:
            out["textures_patched"] = line
        elif "textures: TextureData sha mismatch" in line:
            out["textures_mismatch"] = line
        elif "cache key ready (background):" in line:
            out["key_ready"] = line
        elif "cache key breakdown:" in line:
            out["key_breakdown"] = line
```

7. `main` 的 argparse 增加：

```python
    ap.add_argument("--jvm-arg", action="append", default=[],
                    help="extra JVM argument, e.g. -Dhypernova.textures=false")
```

8. `summarize` 打印增加标志：

```python
        flags = []
        if "fr_missing" in a:
            flags.append("no-FR")
        if "textures_patched" in a:
            flags.append("textures:patched")
        if "textures_mismatch" in a:
            flags.append("textures:MISMATCH")
        print(f"#{i}: menu={r['menu_s']}s wall={r['wall_s']}s preload={pre}({pre_ms}) "
              f"stop={r['stop']} {' '.join(flags)}")
```

- [ ] **Step 8: 实现 `m1b_measure` 改动**

1. 常量区增加：

```python
FAILED_TEXTURE = "Failed to load texture"
FR_MISSING = "FR missing; scripts cache disabled"
```

2. `measure` 签名改为：

```python
def measure(log_path: str | Path, agent_log: str | Path | None = None,
            baseline: int = 30378, threshold: float = 0.2,
            max_normal: int = 50, expect_no_fr: bool = False) -> dict:
```

3. 选完 session 后立即计算：

```python
    lines, session_source = _select_session(lines)
    fr_present = any(SESSION_ANCHOR in line for line in lines)
    failed_texture_lines = sum(1 for line in lines if FAILED_TEXTURE in line)
```

4. agent 解析循环增加：

```python
            if FR_MISSING in line:
                fr_missing_disabled = True
```

并在循环前初始化 `fr_missing_disabled = False`。

5. `gate_ok` 改为：

```python
    gate_ok = (
        menu_t is not None
        and patched
        and mismatch_line is None
        and before <= cap
        and (not expect_no_fr or (not fr_present and fr_missing_disabled
                                  and failed_texture_lines == 0))
    )
```

6. 返回字典增加：

```python
        "fr_present": fr_present,
        "fr_missing_disabled": fr_missing_disabled,
        "failed_texture_lines": failed_texture_lines,
        "expect_no_fr": expect_no_fr,
```

7. CLI 增加：

```python
    ap.add_argument("--expect-no-fr", action="store_true",
                    help="require a true no-FR session: no FR anchor, agent logs "
                         "'FR missing', and no failed texture loads")
```

并把 `args.expect_no_fr` 传给 `measure(...)`。

- [ ] **Step 9: 跑测试确认通过**

Run: `python -m pytest tests/tools/test_m1e_profile.py tests/tools/test_smoke_run.py tests/tools/test_m1b_measure.py -q`
Expected: PASS。

- [ ] **Step 10: 全量工具测试**

Run: `python -m pytest tests/tools -q`
Expected: 全绿；若 `test_smoke_check.py` 的 M-1d 遗留失败仍在，记录为 deferred，不得新增失败。

- [ ] **Step 11: 重建并安装 agent，生成 no-FR profile**

```bash
bash tools/java/build-agent.sh
python tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite \
  --jar build/agent/hypernova.agent.jar
python -I tools/m1e_profile.py \
  --src Starsector-098-260mods/Miko_Lite.txt \
  --out Starsector-098-260mods/Miko_Lite_nofr.txt --force
```

Expected：
- `build-agent.sh` 输出 `OK: .../hypernova.agent.jar`；
- `install_agent.py` 输出 `installed:` 与 `no vmparams change:`（若输出 `install:`，说明它改了 `Miko_Lite.txt` → 停下检查行尾）；
- `m1e_profile.py` 输出 `removed 1 FR agent line(s), 1 classpath token(s)`。

核对派生档：

```bash
grep -n "javaagent\|-classpath" Starsector-098-260mods/Miko_Lite_nofr.txt
```

Expected：只剩 Hypernova agent 行；classpath 不再以 `fr.jar` 开头；`com.fs.starfarer.StarfarerLauncher` 仍在最后。

- [ ] **Step 12: 确认没有残留游戏进程**

```bash
tasklist //FI "IMAGENAME eq java.exe" //NH
```

Expected：`No tasks are running...`。若有残留，停下报告，不要用 `/IM` 强杀。

- [ ] **Step 13: 跑 no-FR 臂 B（textures off，取法线基线）**

```bash
python -I tools/smoke_run.py --profile miko-lite-nofr --rounds 1 \
  --jvm-arg=-Dhypernova.textures=false --json-out build/m1e-nofr-off.json
cp Starsector-098-260mods/starsector-core/starsector.log build/m1e-nofr-off.log
cp Starsector-098-260mods/saves/hypernova/scripts-agent.log build/m1e-nofr-off-agent.log
python -I tools/m1b_measure.py --log build/m1e-nofr-off.log \
  --agent-log build/m1e-nofr-off-agent.log \
  --json-out build/m1e-nofr-off-measure.json
```

Expected：
- 到主菜单（no-FR 下可能 130–200 s；`--wait-menu` 默认 300 s）；
- smoke JSON 的 `agent.fr_missing` 存在、`agent.textures_patched` **不存在**；
- `m1b_measure` 退出码 **1**（`patched=false`，这是预期）；读出 `normal_before_menu` 作为 no-FR 基线，并确认 `fr_present=false`、`fr_missing_disabled=true`、`failed_texture_lines=0`。
- 若游戏在 no-FR 下崩溃/超时 → 按 Escape Hatch 改用 Base + 目标 mod 子集，停止本轮并报告。

- [ ] **Step 14: 跑 no-FR 臂 A（textures on，门禁）**

```bash
python -I tools/smoke_run.py --profile miko-lite-nofr --rounds 1 \
  --jvm-arg=-Dhypernova.textures=true --json-out build/m1e-nofr-on.json
cp Starsector-098-260mods/starsector-core/starsector.log build/m1e-nofr-on.log
cp Starsector-098-260mods/saves/hypernova/scripts-agent.log build/m1e-nofr-on-agent.log
python -I tools/m1b_measure.py --log build/m1e-nofr-on.log \
  --agent-log build/m1e-nofr-on-agent.log --expect-no-fr \
  --baseline <臂 B 的 normal_before_menu> \
  --json-out build/m1e-nofr-on-measure.json
```

Expected：
- `m1b_measure` 退出码 **0**；
- `fr_present=false`、`fr_missing_disabled=true`、`patched=true`、`failed_texture_lines=0`；
- `normal_before_menu` ≤ 50，且相对臂 B 基线下降 ≥80%；
- smoke JSON 有 `agent.textures_patched` 与 `agent.fr_missing`。

补充证据（写进报告）：

```bash
grep -a -m3 "FR missing; scripts cache disabled" build/m1e-nofr-on-agent.log
grep -a -m3 "textures: patched" build/m1e-nofr-on-agent.log
grep -a -c "Fast Rendering: v" build/m1e-nofr-on.log
grep -a -m3 "FR not enabled, handling DDS files manually" build/m1e-nofr-on.log
```

Expected：前两条各有输出；第三条 **0**；第四条若出现则记录，证明 VOpt 在 no-FR 下回退手动 DDS（不出现也不失败，但要在报告里说明）。

- [ ] **Step 15: Commit**

```bash
git add tools/m1e_profile.py tests/tools/test_m1e_profile.py \
  tools/smoke_run.py tests/tools/test_smoke_run.py \
  tools/m1b_measure.py tests/tools/test_m1b_measure.py
git commit -m "feat(m1e): add a true no-FR arm and its measurement gate

Derive Miko_Lite_nofr.txt from the installed profile by removing fr.jar
from the classpath and the FR javaagent line, keeping the Hypernova agent.
Teach the smoke runner to pass extra -D arguments and record process read
bytes, and teach m1b_measure to require positive no-FR evidence.

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: 受控 OS 缓存测量

**Files:**
- Create: `tools/clear_standby.ps1`
- Create: `tools/m1e_rounds.py`
- Create: `tests/tools/test_m1e_rounds.py`

**Interfaces:**
- Consumes: `smoke_run` CLI 的 `--jvm-arg`/`--json-out` 与 JSON 字段 `menu_s`/`read_bytes_menu`/`agent.key_ready`；`tools/clear_standby.ps1`。
- Produces:
  - `m1e_rounds.build_smoke_command(profile: str, json_out: Path, jvm_args: list[str], rounds: int = 1) -> list[str]`
  - `m1e_rounds.purge_standby() -> tuple[bool, str]`
  - `m1e_rounds.parse_key_ms(line: str) -> int | None`
  - `m1e_rounds.summarize(rows: list[dict]) -> dict`
  - JSON 形状：`{profile, tag, cache_control, purge_log, jvm_args, summary, rows}`；`summary` 含 `menu_s`/`read_bytes_menu`/`key_ms` 的 `{n, median, min, max}`。

**Dependencies:** Task 1（需要 `--jvm-arg`、I/O 字段与 `key_ready`）。
**Touches:** `tools/clear_standby.ps1`、`tools/m1e_rounds.py`、`tests/tools/test_m1e_rounds.py`。

- [ ] **Step 1: 写失败测试**

创建 `tests/tools/test_m1e_rounds.py`：

```python
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("m1e_rounds", REPO / "tools" / "m1e_rounds.py")
rounds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rounds)

PURGE = REPO / "tools" / "clear_standby.ps1"


def test_build_smoke_command_includes_profile_jvm_args_and_json():
    cmd = rounds.build_smoke_command(
        "miko-lite", Path("build/out.json"), ["-Dhypernova.textures=false"])
    assert cmd[:3] == [sys.executable, "-I", str(REPO / "tools" / "smoke_run.py")]
    assert cmd[cmd.index("--profile") + 1] == "miko-lite"
    assert cmd[cmd.index("--json-out") + 1] == "build/out.json"
    assert cmd[cmd.index("--jvm-arg") + 1] == "-Dhypernova.textures=false"


def test_parse_key_ms():
    line = "2026-10-31T00:00:00Z INFO cache key ready (background): abc, took 458 ms"
    assert rounds.parse_key_ms(line) == 458
    assert rounds.parse_key_ms("") is None
    assert rounds.parse_key_ms("no timing here") is None


def test_summarize_medians_and_ok_count():
    rows = [
        {"ok": True, "menu_s": 80.0, "read_bytes_menu": 100,
         "agent": {"key_ready": "took 500 ms"}},
        {"ok": True, "menu_s": 90.0, "read_bytes_menu": 300,
         "agent": {"key_ready": "took 700 ms"}},
        {"ok": False},
    ]
    summary = rounds.summarize(rows)
    assert summary["rounds"] == 3
    assert summary["ok_rounds"] == 2
    assert summary["menu_s"] == {"n": 2, "median": 85.0, "min": 80.0, "max": 90.0}
    assert summary["read_bytes_menu"]["max"] == 300
    assert summary["key_ms"]["median"] == 600.0


def test_summarize_empty():
    summary = rounds.summarize([])
    assert summary["ok_rounds"] == 0
    assert summary["menu_s"] is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_purge_script_reports_not_elevated_in_this_shell():
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PURGE)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    out = (r.stdout or "") + (r.stderr or "")
    if "ELEVATED" in out:
        pytest.skip("this shell is elevated")
    assert r.returncode == 3
    assert "NOT_ELEVATED" in out


def test_purge_script_contract():
    text = PURGE.read_text(encoding="utf-8")
    assert "NtSetSystemInformation" in text
    assert "SeProfileSingleProcessPrivilege" in text
    assert "MemoryPurgeStandbyList" in text
    assert "NOT_ELEVATED" in text
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/tools/test_m1e_rounds.py -q`
Expected: FAIL（`tools/m1e_rounds.py` / `tools/clear_standby.ps1` 不存在）。

- [ ] **Step 3: 实现 `tools/clear_standby.ps1`**

```powershell
# Purge the Windows standby list (the OS file cache) before a measurement round.
# Requires an elevated PowerShell; exits 3 without doing anything when not elevated.
param([switch]$CheckOnly)

$ErrorActionPreference = "Stop"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Output "NOT_ELEVATED"
    exit 3
}
if ($CheckOnly) {
    Write-Output "ELEVATED"
    exit 0
}

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class StandbyPurge {
    [StructLayout(LayoutKind.Sequential)]
    public struct LUID { public uint LowPart; public int HighPart; }
    [StructLayout(LayoutKind.Sequential)]
    public struct LUID_AND_ATTRIBUTES { public LUID Luid; public uint Attributes; }
    [StructLayout(LayoutKind.Sequential)]
    public struct TOKEN_PRIVILEGES {
        public uint PrivilegeCount;
        public LUID_AND_ATTRIBUTES Privileges;
    }
    [DllImport("advapi32.dll", SetLastError = true)]
    public static extern bool OpenProcessToken(IntPtr h, uint access, out IntPtr token);
    [DllImport("advapi32.dll", SetLastError = true)]
    public static extern bool LookupPrivilegeValue(string system, string name, out LUID luid);
    [DllImport("advapi32.dll", SetLastError = true)]
    public static extern bool AdjustTokenPrivileges(IntPtr token, bool disableAll,
        ref TOKEN_PRIVILEGES newState, uint bufferLength, IntPtr previous, IntPtr returnLength);
    [DllImport("kernel32.dll")]
    public static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32.dll")]
    public static extern bool CloseHandle(IntPtr h);
    [DllImport("ntdll.dll")]
    public static extern int NtSetSystemInformation(int infoClass, ref int info, int length);

    public static int Purge() {
        IntPtr token;
        // TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY
        if (!OpenProcessToken(GetCurrentProcess(), 0x0020 | 0x0008, out token)) return -1;
        try {
            LUID luid;
            if (!LookupPrivilegeValue(null, "SeProfileSingleProcessPrivilege", out luid)) return -2;
            TOKEN_PRIVILEGES tp = new TOKEN_PRIVILEGES();
            tp.PrivilegeCount = 1;
            tp.Privileges = new LUID_AND_ATTRIBUTES();
            tp.Privileges.Luid = luid;
            tp.Privileges.Attributes = 2; // SE_PRIVILEGE_ENABLED
            if (!AdjustTokenPrivileges(token, false, ref tp, 0, IntPtr.Zero, IntPtr.Zero)) return -3;
            int command = 4; // MemoryPurgeStandbyList
            return NtSetSystemInformation(80, ref command, 4); // SystemMemoryListInformation
        } finally {
            CloseHandle(token);
        }
    }
}
"@

$status = [StandbyPurge]::Purge()
if ($status -ne 0) {
    Write-Output ("FAILED 0x{0:X8}" -f $status)
    exit 4
}
Write-Output "PURGED"
exit 0
```

- [ ] **Step 4: 实现 `tools/m1e_rounds.py`**

```python
#!/usr/bin/env python3
"""Run M-1e startup rounds and summarize the OS-cache state.

Each round delegates to tools/smoke_run.py so the launch path, menu anchor and
process shutdown stay in one place. This orchestrator adds:

  * an optional standby-list purge (tools/clear_standby.ps1) before a round;
  * a JSON summary with median/min/max for menu time, process read bytes and
    the agent's cache-key time.

`ReadTransferCount` is the objective cache-state evidence: a warm OS cache
means the game reads far less from disk than a cold one. When the standby
purge cannot run (no elevation), `cache_control` stays "none" and the results
must be reported as an observation, not as a controlled cold/warm comparison.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "tools" / "smoke_run.py"
PURGE = ROOT / "tools" / "clear_standby.ps1"
KEY_MS = re.compile(r"took (\d+) ms")


def build_smoke_command(profile: str, json_out: Path, jvm_args: list[str],
                        rounds: int = 1) -> list[str]:
    cmd = [sys.executable, "-I", str(SMOKE), "--profile", profile,
           "--rounds", str(rounds), "--json-out", str(json_out)]
    for arg in jvm_args:
        # argparse rejects an option-like value after a space; use the = form.
        cmd.append(f"--jvm-arg={arg}")
    return cmd


def purge_standby() -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(PURGE)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120)
    except Exception as e:  # noqa: BLE001 - reported, never fatal
        return False, f"error: {e}"
    out = (r.stdout or r.stderr or "").strip()
    return (r.returncode == 0 and "PURGED" in out), out


def parse_key_ms(line: str) -> int | None:
    m = KEY_MS.search(line or "")
    return int(m.group(1)) if m else None


def _stats(values: list[float]) -> dict | None:
    if not values:
        return None
    return {
        "n": len(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
    }


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if r.get("ok")]
    menus = [r["menu_s"] for r in ok if r.get("menu_s") is not None]
    reads = [r["read_bytes_menu"] for r in ok
             if r.get("read_bytes_menu") is not None]
    keys = []
    for r in ok:
        key = parse_key_ms(r.get("agent", {}).get("key_ready", ""))
        if key is not None:
            keys.append(key)
    return {
        "rounds": len(rows),
        "ok_rounds": len(ok),
        "menu_s": _stats(menus),
        "read_bytes_menu": _stats(reads),
        "key_ms": _stats(keys),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="miko-lite")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--purge", choices=["never", "once", "each"], default="never")
    ap.add_argument("--jvm-arg", action="append", default=[])
    ap.add_argument("--tag", default="run")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args(argv)

    out = (Path(args.json_out) if args.json_out
           else ROOT / "build" / f"m1e-rounds-{args.tag}.json")
    out.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    purge_log: list[str] = []
    cache_control = "none"
    purge_mode = args.purge

    for i in range(1, args.rounds + 1):
        if purge_mode == "each" or (purge_mode == "once" and i == 1):
            ok, msg = purge_standby()
            purge_log.append(f"round {i}: {msg}")
            print(f"[m1e] standby purge: {msg}", flush=True)
            if ok:
                cache_control = "standby-purged"
            else:
                cache_control = "none"
                purge_mode = "never"
        round_json = out.with_name(f"{out.stem}-r{i}.json")
        cmd = build_smoke_command(args.profile, round_json, args.jvm_arg)
        print(f"[m1e] round {i}/{args.rounds}: {' '.join(cmd)}", flush=True)
        r = subprocess.run(cmd, cwd=str(ROOT))
        if r.returncode != 0:
            print(f"[m1e] smoke exited {r.returncode}", file=sys.stderr)
        if round_json.is_file():
            rows.extend(json.loads(round_json.read_text(encoding="utf-8")))
            round_json.unlink()

    summary = summarize(rows)
    payload = {
        "profile": args.profile,
        "tag": args.tag,
        "cache_control": cache_control,
        "purge_log": purge_log,
        "jvm_args": args.jvm_arg,
        "summary": summary,
        "rows": rows,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"cache_control": cache_control, "summary": summary},
                     ensure_ascii=False, indent=2))
    print(f"[m1e] json -> {out}")
    return 0 if summary["ok_rounds"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/tools/test_m1e_rounds.py -q`
Expected: PASS（`test_purge_script_reports_not_elevated_in_this_shell` 在非提权 shell 下应 PASS；若当前 shell 已提权则 SKIP）。

- [ ] **Step 6: 3 轮热启动（warm 口径）**

先确认没有残留进程：

```bash
tasklist //FI "IMAGENAME eq java.exe" //NH
```

Expected：`No tasks are running...`。

然后：

```bash
python -I tools/m1e_rounds.py --profile miko-lite --rounds 3 \
  --tag warm --json-out build/m1e-rounds-warm.json
```

Expected：
- 3/3 到主菜单；每轮 75–130 s（历史 76.9–98.2 s 覆盖 77.6，不要宣称收益）；
- `cache_control="none"`（未 purge）；
- `summary.menu_s.n=3`，有 `median/min/max`；
- `summary.read_bytes_menu` 有值（Windows I/O 计数器）；若为 `null`，记录为“I/O 探针不可用”；
- `summary.key_ms` 有 3 个值，量级应与 M-1d-2 的 452–481 ms 一致（若明显偏离，记录并检查是否冷缓存）。

- [ ] **Step 7: 尝试受控（post-purge）口径**

先做一次提权检查：

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File tools/clear_standby.ps1
```

Expected（当前非管理员）：`NOT_ELEVATED`，退出码 3。

- 若输出 `PURGED`（说明当前 shell 已提权）：继续跑 post-purge 3 轮：

```bash
python -I tools/m1e_rounds.py --profile miko-lite --rounds 3 --purge once \
  --tag cold --json-out build/m1e-rounds-cold.json
```

Expected：`cache_control="standby-purged"`；第 1 轮 `read_bytes_menu` 明显高于后两轮（冷 OS 缓存 → 从磁盘读更多）；报告中把第 1 轮标为 “post-purge”，第 2–3 轮标为 “warm-after-purge”。

- 若输出 `NOT_ELEVATED`：**不跑** post-purge 臂；在报告中写 `cache_control=none`，并明确“warm 口径是观察，不是受控冷/热对比”（规格停止条件允许降级）。若用户愿意，可在管理员 PowerShell 中运行 `python -I tools/m1e_rounds.py --profile miko-lite --rounds 3 --purge once --tag cold`，把结果补进报告。

- [ ] **Step 8: 全量工具测试**

Run: `python -m pytest tests/tools -q`
Expected: 全绿（允许既有 M-1d 遗留失败，但不得新增）。

- [ ] **Step 9: Commit**

```bash
git add tools/clear_standby.ps1 tools/m1e_rounds.py tests/tools/test_m1e_rounds.py
git commit -m "feat(m1e): measure startup rounds with OS-cache evidence

Add a standby-list purge helper (fail-soft when the shell is not
elevated) and an orchestrator that records menu time, process read
bytes and cache-key time per round with median/min/max. Results stay
observations when the OS cache cannot be controlled.

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: Java 21 审计 + JRE17 全量测试

**Files:**
- Create: `tools/m1e_java_audit.py`
- Create: `tests/tools/test_m1e_java_audit.py`
- Modify: `tools/java/run-agent-tests.sh`
- Modify: `tools/java/run-tests.sh`
- Create: `tests/tools/test_jre17_runner.py`

**Interfaces:**
- Consumes: `build/agent/classes/**`、`build/java/classes/**`、`build/agent/hypernova.agent.jar`、`build/java/hypernova.jar`、系统 `javac`、Base `jre/bin/java.exe`。
- Produces:
  - `m1e_java_audit.class_major(data: bytes) -> int`（magic 校验，读 offset 6..8）。
  - `m1e_java_audit.audit_text(text: str) -> list[str]`（Java 18–21 API 正则）。
  - `m1e_java_audit.scan_class_dir(root: Path) -> list[tuple[Path, int]]`。
  - `m1e_java_audit.scan_jar(path: Path) -> list[tuple[str, int]]`。
  - `m1e_java_audit.main(argv: list[str] | None = None) -> int`；`--classes` 目录内任一 class ≠ `--expect-major` 或任一 API 命中 → 退出 1。
  - `run-agent-tests.sh` / `run-tests.sh` 支持 `JAVA_RUNTIME` 环境变量；默认 `java`，运行日志首行打印 runtime 版本。

**Dependencies:** 无（可与 Task 1/2 并行，但 pipeline 下顺序执行）。
**Touches:** `tools/m1e_java_audit.py`、`tests/tools/test_m1e_java_audit.py`、`tools/java/run-agent-tests.sh`、`tools/java/run-tests.sh`、`tests/tools/test_jre17_runner.py`。

- [ ] **Step 1: 写失败测试**

创建 `tests/tools/test_m1e_java_audit.py`：

```python
import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("m1e_java_audit", REPO / "tools" / "m1e_java_audit.py")
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)


def _class(major: int) -> bytes:
    return b"\xca\xfe\xba\xbe" + (0).to_bytes(2, "big") + major.to_bytes(2, "big") + b"\x00" * 4


def test_class_major_reads_header():
    assert audit.class_major(_class(61)) == 61


def test_class_major_rejects_bad_magic():
    with pytest.raises(ValueError, match="magic"):
        audit.class_major(b"\x00\x00\x00\x00" + b"\x00" * 4)


def test_class_major_rejects_short_file():
    with pytest.raises(ValueError, match="short"):
        audit.class_major(b"\xca\xfe\xba")


def test_scan_class_dir_reports_all(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "A.class").write_bytes(_class(61))
    (pkg / "B.class").write_bytes(_class(65))
    got = {p.name: m for p, m in audit.scan_class_dir(tmp_path)}
    assert got == {"A.class": 61, "B.class": 65}


def test_scan_jar(tmp_path):
    jar = tmp_path / "x.jar"
    with zipfile.ZipFile(jar, "w") as z:
        z.writestr("pkg/A.class", _class(52))
    assert audit.scan_jar(jar) == [("pkg/A.class", 52)]


def test_audit_text_detects_java21_apis():
    hits = audit.audit_text(
        "java/util/SequencedCollection\n"
        "// Method java/lang/Math.clamp:(JII)J\n"
        "java/lang/Thread.ofVirtual")
    assert "java/util/SequencedCollection" in hits
    assert any("clamp" in h for h in hits)
    assert any("ofVirtual" in h for h in hits)


def test_audit_text_ignores_java17_code():
    assert audit.audit_text("java/util/ArrayList\nMath.max\nThread.currentThread") == []


def test_cli_fails_on_wrong_major(tmp_path):
    pkg = tmp_path / "classes" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "A.class").write_bytes(_class(65))
    r = subprocess.run(
        [sys.executable, str(REPO / "tools" / "m1e_java_audit.py"),
         "--classes", str(tmp_path / "classes"), "--skip-api-scan"],
        capture_output=True, text=True)
    assert r.returncode == 1


def test_cli_passes_on_17(tmp_path):
    pkg = tmp_path / "classes" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "A.class").write_bytes(_class(61))
    out = tmp_path / "audit.json"
    r = subprocess.run(
        [sys.executable, str(REPO / "tools" / "m1e_java_audit.py"),
         "--classes", str(tmp_path / "classes"), "--skip-api-scan",
         "--json-out", str(out)],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["ok"] is True
    assert d["class_dirs"][str(tmp_path / "classes")]["count"] == 1


def test_cli_fails_on_source_api(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "A.java").write_text("class A { int x = Math.clamp(1, 0, 2); }", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(REPO / "tools" / "m1e_java_audit.py"),
         "--source", str(src), "--skip-api-scan"],
        capture_output=True, text=True)
    assert r.returncode == 1
```

创建 `tests/tools/test_jre17_runner.py`：

```python
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _assert_runtime_override(script: Path) -> None:
    text = script.read_text(encoding="utf-8")
    assert 'JAVA_RUNTIME="${JAVA_RUNTIME:-java}"' in text, script
    assert '"$JAVA_RUNTIME" -jar' in text, script
    for line in text.splitlines():
        if line.strip().startswith("java -jar"):
            raise AssertionError(f"bare java -jar remains in {script}: {line}")


def test_agent_runner_uses_runtime_override():
    _assert_runtime_override(REPO / "tools" / "java" / "run-agent-tests.sh")


def test_mod_runner_uses_runtime_override():
    _assert_runtime_override(REPO / "tools" / "java" / "run-tests.sh")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/tools/test_m1e_java_audit.py tests/tools/test_jre17_runner.py -q`
Expected: FAIL（工具与 `JAVA_RUNTIME` 未实现）。

- [ ] **Step 3: 实现 `tools/m1e_java_audit.py`**

```python
#!/usr/bin/env python3
"""Audit compiled classes for Java 17 compatibility (M-1e gate 3).

Checks:
  1. Every class under each --classes directory has major version 61.
     Third-party classes bundled in --jar are reported but not failed.
  2. No Java 18-21-only API appears in --source files or in any class
     constant pool (checked with one batched `javap -verbose` per directory).

The major version is read from the class-file header, which is the same field
`javap -verbose` prints. Reading it per class covers every class without
spawning one process per class.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

CLASS_MAGIC = b"\xca\xfe\xba\xbe"
JAVA21_RE = re.compile(
    r"java/util/Sequenced(?:Collection|Set|Map)"
    r"|java/lang/Math[./\s]clamp|Math\.clamp"
    r"|java/lang/Thread[./\s]of(?:Virtual|Platform)|Thread\.of(?:Virtual|Platform)"
    r"|java/util/concurrent/StructuredTaskScope"
    r"|java/util/concurrent/ScopedValue"
    r"|java/lang/StringTemplate"
    r"|java/util/FormatProcessor"
    r"|java/lang/foreign/"
)


def class_major(data: bytes) -> int:
    if len(data) < 8:
        raise ValueError("class file too short")
    if data[:4] != CLASS_MAGIC:
        raise ValueError("bad class magic")
    return int.from_bytes(data[6:8], "big")


def scan_class_dir(root: Path) -> list[tuple[Path, int]]:
    return [(p, class_major(p.read_bytes())) for p in sorted(root.rglob("*.class"))]


def scan_jar(path: Path) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    with zipfile.ZipFile(path) as z:
        for name in sorted(z.namelist()):
            if name.endswith(".class"):
                out.append((name, class_major(z.read(name))))
    return out


def audit_text(text: str) -> list[str]:
    return sorted({m.group(0) for m in JAVA21_RE.finditer(text)})


def class_name(root: Path, path: Path) -> str:
    return ".".join(path.relative_to(root).with_suffix("").parts)


def javap_dump(javap: str, root: Path, names: list[str], chunk: int = 40) -> str:
    parts: list[str] = []
    for i in range(0, len(names), chunk):
        r = subprocess.run(
            [javap, "-verbose", "-classpath", str(root), *names[i:i + chunk]],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise RuntimeError(f"javap failed for {root}: {r.stderr.strip()[:300]}")
        parts.append(r.stdout)
    return "\n".join(parts)


def _majors(entries: list[tuple[object, int]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for _, major in entries:
        counts[str(major)] = counts.get(str(major), 0) + 1
    return dict(sorted(counts.items()))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--classes", action="append", default=[],
                    help="first-party class directory; every class must be --expect-major")
    ap.add_argument("--jar", action="append", default=[],
                    help="jar to report (third-party classes are not failed)")
    ap.add_argument("--source", action="append", default=[],
                    help="source root to scan for Java 18-21 APIs")
    ap.add_argument("--javap", default="javap")
    ap.add_argument("--expect-major", type=int, default=61)
    ap.add_argument("--skip-api-scan", action="store_true")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args(argv)

    if not args.classes and not args.jar and not args.source:
        print("FATAL: pass at least one --classes, --jar or --source", file=sys.stderr)
        return 2

    result: dict = {
        "expected_major": args.expect_major,
        "class_dirs": {},
        "jars": {},
        "java21_api_hits": [],
        "ok": False,
    }
    bad: list[str] = []

    for d in args.classes:
        root = Path(d)
        if not root.is_dir():
            print(f"FATAL: class dir not found: {root}", file=sys.stderr)
            return 2
        entries = scan_class_dir(root)
        wrong = [(p, m) for p, m in entries if m != args.expect_major]
        bad.extend(f"{p}: major {m}" for p, m in wrong)
        result["class_dirs"][d] = {
            "count": len(entries),
            "majors": _majors(entries),
            "bad": [f"{p}: major {m}" for p, m in wrong],
        }
        if not args.skip_api_scan and entries:
            names = [class_name(root, p) for p, _ in entries
                     if p.name != "module-info.class"]
            if names:
                try:
                    result["java21_api_hits"].extend(
                        audit_text(javap_dump(args.javap, root, names)))
                except (OSError, RuntimeError) as e:
                    print(f"FATAL: {e}", file=sys.stderr)
                    return 2

    for j in args.jar:
        path = Path(j)
        if not path.is_file():
            print(f"FATAL: jar not found: {path}", file=sys.stderr)
            return 2
        entries = scan_jar(path)
        result["jars"][j] = {"count": len(entries), "majors": _majors(entries)}

    for s in args.source:
        root = Path(s)
        if not root.is_dir():
            print(f"FATAL: source root not found: {root}", file=sys.stderr)
            return 2
        for p in sorted(root.rglob("*.java")):
            result["java21_api_hits"].extend(
                audit_text(p.read_text(encoding="utf-8", errors="replace")))

    result["java21_api_hits"] = sorted(set(result["java21_api_hits"]))
    result["ok"] = not bad and not result["java21_api_hits"]

    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8", newline="\n")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 修改两个 runner**

`tools/java/run-agent-tests.sh`：在 `ASM=` 之前或参数解析后增加

```bash
JAVA_RUNTIME="${JAVA_RUNTIME:-java}"
echo "runtime: $("$JAVA_RUNTIME" -version 2>&1 | head -n 1)"
```

把 JUnit 调用从

```bash
java -jar "$LIB/junit-platform-console-standalone.jar" \
```

改为

```bash
"$JAVA_RUNTIME" -jar "$LIB/junit-platform-console-standalone.jar" \
```

`tools/java/run-tests.sh` 做同样的两处修改（`JAVA_RUNTIME` + 打印 + 调用）。

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/tools/test_m1e_java_audit.py tests/tools/test_jre17_runner.py -q`
Expected: PASS。

- [ ] **Step 6: 构建 agent 与 mod**

```bash
bash tools/java/build-agent.sh
bash tools/java/build-mod.sh
```

Expected：`OK: .../hypernova.agent.jar`、`OK: .../hypernova.jar`、`OK: .../hypernova-0.1.0.zip`。

- [ ] **Step 7: 跑全量 Java 审计**

```bash
python -I tools/m1e_java_audit.py \
  --classes build/agent/classes \
  --classes build/java/classes \
  --jar build/agent/hypernova.agent.jar \
  --jar build/java/hypernova.jar \
  --source src \
  --json-out build/m1e-java-audit.json
```

Expected：
- 退出码 0；
- `class_dirs` 两个目录的 `majors` 只有 `"61"`；`bad` 为空；
- `jars` 里 agent jar 会同时出现 `52`（ASM 9.1）与 `61`（我们的类）——这是允许的，第三方类不参与失败判定；
- `java21_api_hits` 为空。

若 `bad` 非空：记录完整路径与 major；不要自行改 `pom`/脚本绕过。

- [ ] **Step 8: 用 Base JRE 17 跑全量 agent 测试**

```bash
JAVA_RUNTIME="D:/github/Hypernova-Infinite-Engine/Starsector-098-Base/jre/bin/java.exe" \
  bash tools/java/run-agent-tests.sh 2>&1 | tee build/m1e-jre17-agent-tests.log
```

Expected：
- 首行 `runtime: openjdk version "17.0.10" ...`；
- JUnit 汇总 `tests found` / `tests successful` 与系统 Java 21 一致（历史 64 found / 63 pass / 1 abort）；
- 退出码 0（symlink assumption abort 不算失败）。

`run-agent-tests.sh` 内部会先 `build-agent.sh`，所以 Steps 6/8 有重复构建，无害。

- [ ] **Step 9: 用 Base JRE 17 跑全量 mod 测试**

```bash
JAVA_RUNTIME="D:/github/Hypernova-Infinite-Engine/Starsector-098-Base/jre/bin/java.exe" \
  bash tools/java/run-tests.sh 2>&1 | tee build/m1e-jre17-mod-tests.log
```

Expected：首行 runtime 17；M1 测试全绿（历史 95/95）；退出码 0。

- [ ] **Step 10: 全量工具测试**

Run: `python -m pytest tests/tools -q`
Expected: 全绿（允许既有 M-1d 遗留失败，但不得新增）。

- [ ] **Step 11: Commit**

```bash
git add tools/m1e_java_audit.py tests/tools/test_m1e_java_audit.py \
  tools/java/run-agent-tests.sh tools/java/run-tests.sh \
  tests/tools/test_jre17_runner.py
git commit -m "feat(m1e): audit Java 17 compatibility and run tests on JRE 17

Scan every first-party class for major 61, scan sources and constant
pools for Java 18-21 APIs, and let both test runners use an explicit
JAVA_RUNTIME so the Base JRE 17 can run the full suites.

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: 结果文档 + 规格回写

**Files:**
- Create: `docs/m1e-results.md`
- Modify: `技术笔记-纹理按需加载.md`（§0.2、§7 里程碑顺序、§7 M-1e）

**Interfaces:**
- Consumes: `build/m1e-nofr-off.json`、`build/m1e-nofr-off-measure.json`、`build/m1e-nofr-on.json`、`build/m1e-nofr-on-measure.json`、`build/m1e-nofr-on.log`、`build/m1e-nofr-on-agent.log`、`build/m1e-rounds-warm.json`、`build/m1e-rounds-cold.json`（若存在）、`build/m1e-java-audit.json`、`build/m1e-jre17-agent-tests.log`、`build/m1e-jre17-mod-tests.log`。
- Produces: `docs/m1e-results.md`；规格 §7 的 M-1e 状态与实测数字。

**Dependencies:** Task 1、Task 2、Task 3。
**Touches:** `docs/m1e-results.md`、`技术笔记-纹理按需加载.md`。

- [ ] **Step 1: 汇总原始值**

```bash
python - <<'EOF'
import json, glob
for p in sorted(glob.glob('build/m1e-*.json')):
    print('===', p)
    d = json.load(open(p, encoding='utf-8'))
    if 'rows' in d:
        print('cache_control:', d.get('cache_control'))
        print('summary:', json.dumps(d.get('summary'), ensure_ascii=False))
        for i, r in enumerate(d.get('rows', []), 1):
            a = r.get('agent', {})
            print(f"  r{i}: ok={r.get('ok')} menu={r.get('menu_s')} "
                  f"read_menu={r.get('read_bytes_menu')} "
                  f"key={a.get('key_ready', '')[-40:]}")
    else:
        print(json.dumps(d, ensure_ascii=False, indent=2))
EOF
```

Expected：能读到三项证据的全部原始值。若某个文件缺失，回到对应任务补齐；**不得用期望值代替实测值**。

- [ ] **Step 2: 写 `docs/m1e-results.md`**

必须包含以下结构与全部原始值（`<填>` 按 Step 1 的实测填；没有的数字写 `n/a` 并说明原因）：

```markdown
# M-1e 发布前验证结果

> 日期：2026-10-31
> 环境：Starsector 0.98a + 260mods、Miko Lite（JDK 28）、`Miko_Lite.txt`（FR 0.9.5）
> 结论：no-FR 臂 / OS 缓存 / Java 17 三门禁的判定见 §1。

## 1. 结论

| 门禁 | 结果 | 证据 |
|---|---|---|
| no-FR 臂 | <通过/不通过/降级> | §2；`build/m1e-nofr-on-measure.json` |
| OS 缓存测量 | <受控/观察>（`cache_control=<填>`） | §3；`build/m1e-rounds-warm.json` |
| Java 17 审计 | <通过/不通过> | §4；`build/m1e-java-audit.json` |

- 菜单时间：3 轮 warm 中位数 **<填> s**（<min>–<max>），落在历史 76.9–98.2 s 内/外；**不宣称收益**。
- no-FR 法线：`normal_before_menu` **<填>**（臂 B 基线 **<填>**），下降 **<填>%**；`textures patched` = <是/否>；`FR missing` = <是/否>；`Failed to load texture` = <填>。
- JRE17：agent **<found/successful/aborted>**；mod **<passed/total>**；runtime 首行 = `<填>`。

## 2. no-FR 臂

### 2.1 环境构造

- 源档：`Starsector-098-260mods/Miko_Lite.txt`（**未修改**；sha256=<填>）。
- 派生档：`Starsector-098-260mods/Miko_Lite_nofr.txt`，由 `tools/m1e_profile.py` 生成：
  - 移除 `-javaagent:fr.agent.jar` 1 行；
  - 从 `-classpath` 移除 `fr.jar` 1 个 token；
  - 保留 `-javaagent:../mods/hypernova_infinite_engine/jars/hypernova.agent.jar`；
  - 主类仍为最后一行。
- 真无 FR 的定义：classpath 无 `fr.jar` **且** agent 未加载 FR javaagent；`HypernovaAgent.frPresent()` 用 `Class.forName("com.genir.renderer.Version")` 正向验证。

### 2.2 证据

| 检查 | 命令/来源 | 实测 |
|---|---|---|
| 日志无 FR | `grep -ac "Fast Rendering: v" build/m1e-nofr-on.log` | <填>（要求 0） |
| agent 记 FR missing | `grep -m1 "FR missing; scripts cache disabled" build/m1e-nofr-on-agent.log` | <填> |
| textures 仍 patched | `grep -m1 "textures: patched" build/m1e-nofr-on-agent.log` | <填> |
| 无失败纹理 | `m1b_measure.failed_texture_lines` | <填>（要求 0） |
| 到主菜单 | `build/m1e-nofr-on.json` `menu_s` | <填> s |
| VOpt 回退 | `grep -m1 "FR not enabled, handling DDS files manually" build/m1e-nofr-on.log` | <填/未出现，不失败> |

### 2.3 A/B 法线

| 臂 | `textures.enabled` | `normal_before_menu` | `patched` | `fr_present` | `failed_texture_lines` | `menu_s` |
|---|---|---:|---|---|---:|---:|
| B（基线） | false | <填> | false | false | <填> | <填> |
| A（门禁） | true | <填> | true | false | <填> | <填> |

- 下降 = 1 − A/B = **<填>%**（门禁 ≥80%）。
- 绝对行数 A = **<填>**（门禁 ≤50）。

## 3. OS 缓存测量

### 3.1 口径

- warm：连续 3 轮，不 purge；每轮记录 `ReadTransferCount`（进程累计从磁盘读的字节）。
- post-purge（若可用）：`tools/clear_standby.ps1` 清 standby list 后跑 3 轮；`cache_control=standby-purged`。
- 本机默认非管理员；`clear_standby.ps1` 返回 `NOT_ELEVATED` 时 **不跑** post-purge 臂，结论降级为“观察”。

### 3.2 warm 3 轮

| 轮 | `menu_s` | `read_bytes_menu` | key `took` (ms) | `stop` |
|---:|---:|---:|---:|---|
| 1 | <填> | <填> | <填> | <填> |
| 2 | <填> | <填> | <填> | <填> |
| 3 | <填> | <填> | <填> | <填> |
| 中位数 | **<填>** | **<填>** | **<填>** | — |
| min–max | <填> | <填> | <填> | — |

- `cache_control` = `<填>`。
- 若 `read_bytes_menu` 为 null：写明“I/O 探针不可用，OS 缓存状态未测”。

### 3.3 post-purge（仅当 `PURGED`）

| 轮 | `menu_s` | `read_bytes_menu` | 备注 |
|---:|---:|---:|---|
| 1 | <填> | <填> | post-purge |
| 2 | <填> | <填> | warm-after-purge |
| 3 | <填> | <填> | warm-after-purge |

- 第 1 轮 read bytes 是否显著高于后两轮：<是/否>；结论只用分布，不用单轮差值。

### 3.4 与历史同口径对照

- key：旧 15 次中位 7,606 ms（3,336–14,402）vs 新 3 次 **<填>**（<min>–<max>）。
- 菜单：本轮 3 次 **<填>** vs 历史 76.9–98.2 s；落在区间内 → 不宣称收益。

## 4. Java 17 审计

### 4.1 class major

| 目录 | class 数 | majors | 非 61 |
|---|---:|---|---|
| `build/agent/classes` | <填> | <填> | <填> |
| `build/java/classes` | <填> | <填> | <填> |
| `build/agent/hypernova.agent.jar` | <填> | <填>（ASM 52 允许） | — |
| `build/java/hypernova.jar` | <填> | <填> | — |

### 4.2 Java 21 API

- `java21_api_hits` = `<填>`（要求空）。
- 扫描范围：`src/**/*.java` + 两个 classes 目录的全部 constant pool（`javap -verbose`）。

### 4.3 JRE17 全量

| 套件 | runtime | 结果 | 日志 |
|---|---|---|---|
| agent | `openjdk 17.0.10` | <填> | `build/m1e-jre17-agent-tests.log` |
| mod | `openjdk 17.0.10` | <填> | `build/m1e-jre17-mod-tests.log` |

- 与系统 Java 21 的差异：<填/无>。
- symlink assumption：<abort/通过>。

## 5. 回滚与重跑

```bash
# 重新生成 no-FR 档
python -I tools/m1e_profile.py --src Starsector-098-260mods/Miko_Lite.txt \
  --out Starsector-098-260mods/Miko_Lite_nofr.txt --force
# no-FR 单轮
python -I tools/smoke_run.py --profile miko-lite-nofr --jvm-arg=-Dhypernova.textures=true
# warm 3 轮
python -I tools/m1e_rounds.py --profile miko-lite --rounds 3 --tag warm
# Java 审计
python -I tools/m1e_java_audit.py --classes build/agent/classes --classes build/java/classes \
  --jar build/agent/hypernova.agent.jar --jar build/java/hypernova.jar --source src
# JRE17
JAVA_RUNTIME="D:/github/Hypernova-Infinite-Engine/Starsector-098-Base/jre/bin/java.exe" \
  bash tools/java/run-agent-tests.sh
```

## 6. 已知限制

- OS 缓存未受控时，warm 数字只能作观察；`read_bytes_menu` 是启发式证据，不是内存映射的完整证明。
- no-FR 臂没有覆盖“FR 0.9.7rc2 + Hypernova”组合（那是后续独立任务）。
- 260mods 的 256 个启用 mod 中只有 VOpt 引用 `com/genir`；其它 mod 的反射/字节码未逐一证明。
- Java 审计的 API 列表是已知清单，不是 JDK 17/21 全量 diff。
```

- [ ] **Step 3: 回写规格 §7**

把 `技术笔记-纹理按需加载.md` 的 M-1e 段改为（数字按 Step 1 实测填）：

```markdown
### M-1e 发布前验证（已完成，2026-10-31）

- **状态**：完成。三项门禁：no-FR 臂 **<通过/降级>**、OS 缓存 **<受控/观察>**、Java 17 **<通过>**。
- **no-FR 臂**：`Miko_Lite_nofr.txt` 由 `tools/m1e_profile.py` 从 `Miko_Lite.txt` 派生（移除 `fr.jar` classpath token 与 `-javaagent:fr.agent.jar`，保留 Hypernova agent）。实测：日志 `Fast Rendering: v` **<填>** 条；agent `FR missing; scripts cache disabled`；`textures: patched`；`normal_before_menu` **<填>**（臂 B 基线 **<填>**，下降 **<填>%**）；无 `Failed to load texture`；正常到主菜单。
- **OS 缓存**：warm 3 轮中位 **<填> s**（<min>–<max>），`cache_control=<填>`；`ReadTransferCount` **<填>**。post-purge 臂 **<已跑/未跑>**；未受控时结论为“观察”，不宣称净收益。
- **Java 17**：`build/agent/classes` 与 `build/java/classes` 全部 class major=61；`java21_api_hits` 空；Base JRE 17 下 agent **<填>**、mod **<填>** 全绿（symlink assumption 可 abort）。
- **证据**：`docs/m1e-results.md`、`build/m1e-*.json`、`build/m1e-jre17-*.log`。
- **顺序**：M-1e 已完成；下一步按 ADR-03/OD-01 裁决 M2 / M3 / 修订 G-01，**不要**把 M-1e 当成 M3 的前置替代。
```

同时更新：
1. §7 里程碑顺序行：把 `**M-1e（发布前验证，下一个，2026-10-31 立项）**` 改为 `**M-1e（发布前验证）✔（已完成，2026-10-31）**`。
2. §0.2 末尾追加一条：

```markdown
6. **M-1e 已完成（2026-10-31）**：no-FR 臂 / OS 缓存 / Java 17 三门禁见 §7 与 `docs/m1e-results.md`。下一步是 M2/M3/修订 G-01 的裁决。
```

- [ ] **Step 4: 核对回写没有夸大**

```bash
grep -n "M-1e" 技术笔记-纹理按需加载.md | head -20
grep -n "不宣称\|观察\|未受控\|受控" docs/m1e-results.md
```

Expected：结果文档里每个数字都能在 `build/m1e-*.json` 找到；没有“净收益/提速 X%”这类超出证据的措辞；菜单时间明确写“不宣称收益”。

- [ ] **Step 5: Commit**

```bash
git add docs/m1e-results.md 技术笔记-纹理按需加载.md
git commit -m "docs(m1e): record the release-readiness evidence

Record the no-FR arm, the OS-cache-controlled startup distribution, and
the Java 17 audit/test results, then write the status back into spec §7.
Menu time is reported as a distribution, not as a claimed gain.

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Self-Review

### 1. Spec coverage

| 规格 §7 M-1e 条目 | 任务 |
|---|---|
| no-FR 定义：agent 未加载 **且** `com.genir.renderer.Version` 不在 classpath | Task 1 `m1e_profile.convert` 移除 `fr.jar` + `-javaagent:fr.agent.jar`；`m1b_measure --expect-no-fr` 要求 `fr_present=false` + agent `FR missing` |
| 不得永久破坏 260mods 启动文件，用副本/独立 profile | Task 1 只写 `Miko_Lite_nofr.txt`；`test_cli_does_not_modify_source`；CLI 拒绝 `--src == --out` |
| 正常到主菜单 | Task 1 Step 13/14 smoke `menu_s` 非空 |
| 日志无 `Fast Rendering: v0.9.5` | Task 1 `m1b_measure.fr_present` + Step 14 `grep -c` |
| `scripts` 出现 `FR missing; scripts cache disabled` 且不崩 | Task 1 `fr_missing_disabled` 门禁 + agent 日志 |
| `textures` 仍 `patched` | Task 1 `patched` 门禁 + `agent.textures_patched` |
| `normal_before_menu` 相对 B 组下降 ≥80%、绝对 ≤50 | Task 1 Step 13/14 A/B + `m1b_measure` cap |
| 无 `Failed to load texture` | Task 1 `failed_texture_lines` 进入 no-FR 门禁 |
| 停止条件：无法移除 FR → Base + 子集 | Escape Hatch + Task 1 Step 13 |
| OS 缓存清/控后至少 3 轮，中位数与分布 | Task 2 `m1e_rounds --rounds 3` + `summary` |
| 明确冷/热口径，不用单轮宣称收益 | Task 2 `cache_control` + Task 4 模板 §3.1/§3.4 |
| 停止条件：无法控制 → 降级观察 | Task 2 Step 7 + Task 4 模板 |
| M-1d-2 前后 key 同口径对比 + 菜单分布 | Task 2 `summary.key_ms` + Task 4 §3.4 |
| 逐个 `javap -verbose` 检查 `build/agent/classes/**` major | Task 3 `class_major` 逐类读头（与 javap 同源字段）+ `javap -verbose` 批量扫 constant pool；`scan_class_dir` 覆盖全部 |
| 全文搜索 Java 21 特有 API | Task 3 `audit_text` 扫 `src/**/*.java` + javap 输出 |
| 用 Base JRE 17 跑全量 agent 测试 | Task 3 `JAVA_RUNTIME` + Step 8 |
| 验收：所有 agent class major=61；无 21-only API；JRE17 全绿 | Task 3 Step 7/8 门禁 |
| 出口：`docs/m1e-results.md` 含三项证据；§7 回写；三项全过才进入发布/M2-M3 裁决 | Task 4 |
| 顺序：M-1e 完成后再裁决 M2/M3/修订 G-01 | Task 4 §7 回写 + §0.2 追加 |

### 2. Placeholder scan

- 代码块无 TBD/TODO；Task 4 的 `<填>` 是**要求填实测值**的占位，不是未决设计，Step 1 给了提取命令。
- 所有新增函数都有完整实现；所有修改点给出了方法级替换代码。
- 唯一“未决”的是 OS 缓存能否提权——这是规格明确允许的停止/降级分支，不是计划缺口。

### 3. Type consistency

- `convert(text: str) -> tuple[str, dict]`：Task 1 测试与 CLI 使用一致。
- `build_command(java, vmparams_arg, direct, jvm_args)`：Task 1 定义；Task 1 测试与 `one_round` 使用一致。
- `io_read_bytes(pid: int) -> int | None`：Task 1 定义；`one_round` 与测试使用一致。
- `measure(..., expect_no_fr: bool = False)`：Task 1 CLI 传参；输出字段名与 Task 4 模板一致。
- `build_smoke_command(profile, json_out, jvm_args, rounds=1)`：Task 2 测试与 `main` 使用一致。
- `summarize(rows) -> dict` 的键 `menu_s`/`read_bytes_menu`/`key_ms`：Task 4 模板按同名键引用。
- `class_major(data: bytes) -> int`、`audit_text(text) -> list[str]`：Task 3 测试与 CLI 使用一致。

### 4. Review Focus tests

1. 假 no-FR → `test_convert_removes_fr_from_agent_and_classpath`、`test_convert_refuses_missing_hypernova_agent`、`test_expect_no_fr_fails_when_fr_anchor_present`。
2. no-FR 下 VOpt 崩溃 → Task 1 Step 14 抓 VOpt 回退日志；跑通主菜单是硬门禁（不是单测）。
3. OS 缓存未受控却宣称收益 → `test_summarize_*`、`test_purge_script_reports_not_elevated_in_this_shell`；Task 4 §3.1 口径。
4. JRE17 runner 偷偷回退 21 → `test_agent_runner_uses_runtime_override`、`test_mod_runner_uses_runtime_override`；Step 8/9 日志首行。
5. 审计只查一个类 → `test_scan_class_dir_reports_all`、`test_cli_fails_on_wrong_major`。
6. 派生 profile 反向污染源文件 → `test_cli_does_not_modify_source`、`test_cli_refuses_overwrite_without_force`。

### 5. Proportion

- 规格 §7 M-1e 是“验证 + 修门禁”，不是功能开发；计划的新增代码集中在 4 个小工具与 2 处 runner 开关，生产 Java 代码零改动。
- 最大的代码块是 `m1e_java_audit.py` 与 `m1e_rounds.py`，都是可独立测试的纯函数 + CLI；没有复述现有 `smoke_run`/`m1b_measure` 的全文。

---

## Execution Handoff

本计划按 **pipeline** 执行：

- Task 1 的 no-FR 臂是 M-1e 的核心；若它在 260mods 上失败，按规格停止条件改用 Base + 目标 mod 子集，并在报告里写明环境差异。
- Task 2 的 OS 缓存臂默认只能做到“观察”（本机非管理员）；不得为了凑“受控”而改口径。
- Task 3 的 JRE17 测试若失败，停并报告；是否改生产代码由 controller 裁决。
- Task 4 的数字只能来自 `build/m1e-*.json` 与日志，不能来自期望值。
- 每个任务独立 commit；审查输入为 brief + report + diff。
