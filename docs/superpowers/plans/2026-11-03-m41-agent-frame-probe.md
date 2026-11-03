# M4.1 Agent 侧 frame probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 frame-time probe 在 260mods 的 agent-only 配置里也能工作：由 `-javaagent` 加载的 agent 在 campaign/title/combat 的每帧 `Display.update` 上采样，输出 `HYPERNOVA_FRAME` 到 `scripts-agent.log`，报告工具优先解析 agent 日志。

**Architecture:** 新增 `hypernova.agent.FrameProbe`（纯计时器）与 `FrameProbeTransformer`（ASM 在 `org.lwjgl.opengl.Display.update()V` 和 `update(Z)V` 的入口注入采样调用）。`Display.update` 是每帧的 buffer swap，在 title/campaign/combat 的帧循环里各调用一次；`BaseGameState.traverse`/`CombatState.traverse` 本身是**整个状态循环**，不是逐帧回调，不能作为采样点。`HypernovaAgent.premain` 在 `-Dhypernova.frameProbe=true` 时注册 transformer，独立于 lazy/FR/scripts 开关。`tools/m4_session_report.py` 先从最后一个 agent premain 之后的日志找帧行，找不到再回退到 starsector.log；`frame_probe.source` 标明来源。

**Tech Stack:** Java 17、ASM 9.1、JUnit 5、Python 3/pytest。

**Spec:** `技术笔记-纹理按需加载.md` §7 M4 行；`docs/m4-results.md` I-5 限制；`docs/m4-manual-acceptance.md`。

## Global Constraints

- probe 默认 off；只有 `-Dhypernova.frameProbe=true` 才注册 transformer/采样；关闭时零采样成本。
- probe 不能依赖 lazy、FR、scripts、主 mod；260mods agent-only 必须可用。
- 每帧采样点在 `org.lwjgl.opengl.Display.update`（`()V` 与 `(Z)V` 两个重载）的入口；这是 title/campaign/combat 帧循环里的 buffer swap。**不要**注入 `BaseGameState.traverse`/`CombatState.traverse`，它们是整段状态循环，只在状态切换时返回。
- `HYPERNOVA_FRAME` 行格式与主 mod 完全一致：`frames=<int> over200=<int> maxMs=<int> p99Ms=<int> lastMs=<int> longGaps=<int>`。
- `over200` 严格 >200 ms；`longGaps` >5 s，不计入 frames/max/直方图；`p99Ms` 1 ms 直方图；`maxMs` 向上取整。
- 注入失败必须 fail-open+可见：写 `frame probe: ... failed/missing`，不影响游戏。
- 不默认开启；不改发行配置/默认开关；不 push，除非用户确认。
- **Escape hatch**：若断言数字/测试顺序与实现不符，按实际修正并报告。**若需求自相矛盾或无法同时满足 → 停下报告，不许挑一半照做。**

## Review Focus

1. 采样点必须是真逐帧：`Display.update` 是 buffer swap；`BaseGameState.traverse`/`CombatState.traverse` 是整段循环，只在状态切换时返回，不能作为采样点。实机 smoke 必须出现 `HYPERNOVA_FRAME` 行，否则说明采样点仍不是逐帧。
2. probe 与 lazy 的注册顺序/早退：scripts 关闭、lazy 关闭、FR 缺失时 probe 仍要注册。
3. 关闭时零成本：属性 false 时不注册 transformer、不建采样器。
4. agent 日志会话切片：只认最后一个 `hypernova agent premain` 之后的帧行，不能拿上一局。
5. 报告双来源：agent 优先、starsector.log 回退；不能把两条来源混成一份。

---

### Task 1: Agent FrameProbe + transformer + wiring

**Files:**
- Create: `src/agent/java/hypernova/agent/FrameProbe.java`
- Create: `src/agent/java/hypernova/agent/FrameProbeTransformer.java`
- Modify: `src/agent/java/hypernova/agent/HypernovaAgent.java`
- Test: `tests/agent/java/hypernova/agent/FrameProbeTest.java`
- Test: `tests/agent/java/hypernova/FrameProbeTransformTest.java`
- Test: `tests/agent/java/hypernova/FrameProbeWiringTest.java`

**Interfaces:**
- Produces:
  - `public static void FrameProbe.frame(String source)`
  - `public static final String FrameProbe.LINE_PREFIX = "HYPERNOVA_FRAME "`
  - `FrameProbeTransformer` targets `org/lwjgl/opengl/Display`, methods `update()V` and `update(Z)V`
  - log markers: `frame probe: enabled`, `frame probe: hook added to Display.update` (once per class), `frame probe: samples started from Display.update`

**Dependencies:** 无
**Touches:** the six files above

- [ ] **Step 1: 写失败测试**

`tests/agent/java/hypernova/agent/FrameProbeTest.java`:

```java
package hypernova.agent;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class FrameProbeTest {
    private static final long MS = 1_000_000L;
    private static final long T0 = 1_000L * MS;

    @Test
    void firstCallStartsClock() {
        FrameProbe.State s = new FrameProbe.State(600);
        assertNull(s.sample(T0));
        assertTrue(s.line().contains("frames=0"));
    }

    @Test
    void countsFramesAndP99() {
        FrameProbe.State s = new FrameProbe.State(600);
        s.sample(T0);
        long now = T0;
        for (int i = 0; i < 100; i++) {
            now += 16 * MS;
            s.sample(now);
        }
        String line = s.line();
        assertTrue(line.contains("frames=100"), line);
        assertTrue(line.contains("over200=0"), line);
        assertTrue(line.contains("maxMs=16"), line);
        assertTrue(line.contains("p99Ms=16"), line);
    }

    @Test
    void countsStutterAndExactBoundaries() {
        FrameProbe.State s = new FrameProbe.State(600);
        s.sample(T0);
        s.sample(T0 + 200 * MS);
        assertTrue(s.line().contains("over200=0"));
        s.sample(T0 + 450 * MS);
        assertTrue(s.line().contains("over200=1"));
        assertTrue(s.line().contains("maxMs=250"));
    }

    @Test
    void longGapIsExcluded() {
        FrameProbe.State s = new FrameProbe.State(600);
        s.sample(T0);
        s.sample(T0 + 5_000 * MS);
        assertTrue(s.line().contains("frames=1"));
        assertTrue(s.line().contains("longGaps=0"));
        s.sample(T0 + 5_000 * MS + 6_000 * MS);
        assertTrue(s.line().contains("longGaps=1"));
    }

    @Test
    void lineIsDueEveryConfiguredFrames() {
        FrameProbe.State s = new FrameProbe.State(2);
        s.sample(T0);
        assertNull(s.sample(T0 + 16 * MS)); // frames=1
        String due = s.sample(T0 + 32 * MS); // frames=2, due
        assertNotNull(due);
        assertTrue(due.startsWith(FrameProbe.LINE_PREFIX));
        assertTrue(due.contains("frames=2"));
        assertNull(s.sample(T0 + 48 * MS)); // frames=3
    }
}
```

`tests/agent/java/hypernova/FrameProbeTransformTest.java`:

```java
package hypernova;

import hypernova.agent.FrameProbeTransformer;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class FrameProbeTransformTest {
    private static final String DISPLAY = "org/lwjgl/opengl/Display";

    @Test
    void injectsIntoBothDisplayUpdateOverloads() {
        byte[] in = displayClass(true, true);
        byte[] out = new FrameProbeTransformer().transform(null, DISPLAY, null, null, in);
        assertNotNull(out);
        assertEquals(2, calls(out, "hypernova/agent/FrameProbe", "frame"));
    }

    @Test
    void injectsIntoOnlyThePresentOverload() {
        byte[] out = new FrameProbeTransformer().transform(
                null, DISPLAY, null, null, displayClass(true, false));
        assertNotNull(out);
        assertEquals(1, calls(out, "hypernova/agent/FrameProbe", "frame"));
    }

    @Test
    void missingUpdateIsUntouched() {
        assertNull(new FrameProbeTransformer().transform(
                null, DISPLAY, null, null, classBytesWithoutUpdate()));
    }

    @Test
    void otherClassAndMalformedBytesAreIgnored() {
        assertNull(new FrameProbeTransformer().transform(
                null, "org/lwjgl/opengl/Other", null, null, displayClass(true, true)));
        assertNull(new FrameProbeTransformer().transform(
                null, DISPLAY, null, null, new byte[]{1, 2, 3}));
    }

    private static byte[] displayClass(boolean noArg, boolean boolArg) {
        ClassWriter cw = new ClassWriter(0);
        cw.visit(Opcodes.V17, Opcodes.ACC_PUBLIC | Opcodes.ACC_FINAL,
                DISPLAY, null, "java/lang/Object", null);
        if (noArg) {
            MethodVisitor mv = cw.visitMethod(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
                    "update", "()V", null, null);
            mv.visitCode(); mv.visitInsn(Opcodes.RETURN); mv.visitMaxs(0, 0); mv.visitEnd();
        }
        if (boolArg) {
            MethodVisitor mv = cw.visitMethod(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
                    "update", "(Z)V", null, null);
            mv.visitCode(); mv.visitInsn(Opcodes.RETURN); mv.visitMaxs(0, 0); mv.visitEnd();
        }
        cw.visitEnd();
        return cw.toByteArray();
    }

    private static byte[] classBytesWithoutUpdate() {
        ClassWriter cw = new ClassWriter(0);
        cw.visit(Opcodes.V17, Opcodes.ACC_PUBLIC, DISPLAY, null, "java/lang/Object", null);
        MethodVisitor mv = cw.visitMethod(Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
                "sync", "(I)V", null, null);
        mv.visitCode(); mv.visitInsn(Opcodes.RETURN); mv.visitMaxs(0, 0); mv.visitEnd();
        cw.visitEnd();
        return cw.toByteArray();
    }

    private static int calls(byte[] bytes, String owner, String name) {
        List<String> hits = new ArrayList<>();
        new ClassReader(bytes).accept(new ClassVisitor(Opcodes.ASM9) {
            @Override public MethodVisitor visitMethod(int a, String n, String d, String s, String[] e) {
                return new MethodVisitor(Opcodes.ASM9) {
                    @Override public void visitMethodInsn(int op, String o, String mn, String dd, boolean itf) {
                        if (owner.equals(o) && name.equals(mn)) hits.add(mn);
                    }
                };
            }
        }, 0);
        return hits.size();
    }
}
```

`tests/agent/java/hypernova/FrameProbeWiringTest.java`:

```java
package hypernova;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class FrameProbeWiringTest {
    @Test
    void premainRegistersInsidePropertyGateBeforeScriptsEarlyReturn() throws Exception {
        String src = Files.readString(
                Path.of("src/agent/java/hypernova/agent/HypernovaAgent.java"));
        int gate = src.indexOf(
                "if (Boolean.getBoolean(\"hypernova.frameProbe\"))");
        int probe = src.indexOf("new FrameProbeTransformer()");
        int scriptsGate = src.indexOf("scripts cache disabled by config");
        assertTrue(gate > 0, "probe must be gated by the system property");
        assertTrue(probe > gate,
                "addTransformer must be inside the property gate");
        assertTrue(probe < scriptsGate,
                "probe must register before the scripts early return");
    }

    @Test
    void transformerTargetsBothDisplayUpdateOverloads() throws Exception {
        String src = Files.readString(
                Path.of("src/agent/java/hypernova/agent/FrameProbeTransformer.java"));
        assertTrue(src.contains("org/lwjgl/opengl/Display"),
                "must target Display");
        assertTrue(src.contains("\"()V\"") && src.contains("\"(Z)V\""),
                "must cover both update overloads");
    }
}
```

- [ ] **Step 2: 运行确认失败**

Run: `bash tools/java/run-agent-tests.sh FrameProbe`
Expected: compile failure (`FrameProbe` / transformer missing).

- [ ] **Step 3: 新建 `src/agent/java/hypernova/agent/FrameProbe.java`**

```java
package hypernova.agent;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Agent-side per-frame timer for the M4 A→B/stutter gate.
 *
 * <p>Injected into {@code org.lwjgl.opengl.Display.update} (both overloads),
 * the per-frame buffer swap used by the title/campaign/combat loops. Enabled
 * only by {@code -Dhypernova.frameProbe=true}; independent of lazy textures,
 * FR and the scripts cache.
 *
 * <p>Gaps &gt; 5 s are counted as {@code longGaps} and excluded from frames,
 * max and the histogram (pause/load/alt-tab). P99 is a 1 ms histogram
 * estimate. A line is logged every 600 valid frames.
 */
public final class FrameProbe {
    public static final String LINE_PREFIX = "HYPERNOVA_FRAME ";
    public static final long STUTTER_NANOS = 200_000_000L;
    public static final long MAX_GAP_NANOS = 5_000_000_000L;
    static final int MAX_BUCKET_MS = 1000;

    private static final int LOG_EVERY_FRAMES = 600;
    private static final State STATE = new State(LOG_EVERY_FRAMES);
    private static final Set<String> FIRST_SOURCES = ConcurrentHashMap.newKeySet();

    private FrameProbe() {
    }

    /** Called from the injected bytecode at the start of a frame. */
    public static void frame(String source) {
        if (FIRST_SOURCES.add(source)) {
            AgentLog.info("frame probe: samples started from " + source);
        }
        String line = STATE.sample(System.nanoTime());
        if (line != null) {
            AgentLog.info(line);
        }
    }

    static final class State {
        private final int logEveryFrames;
        private final long[] buckets = new long[MAX_BUCKET_MS + 1];
        private boolean hasLast;
        private long lastNanos;
        private long frames;
        private long over200;
        private long longGaps;
        private long maxNanos;
        private long lastDeltaNanos;
        private long framesAtLastLine = 0L;

        State(int logEveryFrames) {
            this.logEveryFrames = Math.max(1, logEveryFrames);
        }

        synchronized String sample(long nowNanos) {
            if (!hasLast) {
                hasLast = true;
                lastNanos = nowNanos;
                return null;
            }
            long delta = nowNanos - lastNanos;
            lastNanos = nowNanos;
            if (delta <= 0L) {
                return null;
            }
            if (delta > MAX_GAP_NANOS) {
                longGaps++;
                return null;
            }
            frames++;
            lastDeltaNanos = delta;
            if (delta > maxNanos) {
                maxNanos = delta;
            }
            if (delta > STUTTER_NANOS) {
                over200++;
            }
            long ms = (delta + 999_999L) / 1_000_000L;
            buckets[(int) Math.min(ms, MAX_BUCKET_MS)]++;
            if (frames - framesAtLastLine < logEveryFrames) {
                return null;
            }
            framesAtLastLine = frames;
            return line();
        }

        synchronized String line() {
            return LINE_PREFIX
                    + "frames=" + frames
                    + " over200=" + over200
                    + " maxMs=" + millisCeil(maxNanos)
                    + " p99Ms=" + p99Millis()
                    + " lastMs=" + millisCeil(lastDeltaNanos)
                    + " longGaps=" + longGaps;
        }

        private long p99Millis() {
            if (frames == 0) {
                return 0;
            }
            long need = (frames * 99L + 99L) / 100L;
            long seen = 0;
            for (int i = 0; i < buckets.length; i++) {
                seen += buckets[i];
                if (seen >= need) {
                    return i;
                }
            }
            return MAX_BUCKET_MS;
        }

        private static long millisCeil(long nanos) {
            return (nanos + 999_999L) / 1_000_000L;
        }
    }
}
```

- [ ] **Step 4: 新建 `src/agent/java/hypernova/agent/FrameProbeTransformer.java`**

```java
package hypernova.agent;

import org.objectweb.asm.*;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

/**
 * Injects {@link FrameProbe#frame(String)} at the start of both
 * {@code org.lwjgl.opengl.Display.update} overloads. Display.update is the
 * per-frame buffer swap inside the title/campaign/combat loops; do not use
 * BaseGameState.traverse/CombatState.traverse, which are whole-state loops.
 *
 * <p>A missing overload is logged and left untouched; transform failures are
 * fail-open and visible in the agent log.
 */
public final class FrameProbeTransformer implements ClassFileTransformer {
    static final String TARGET = "org/lwjgl/opengl/Display";
    private static final String METHOD = "update";
    private static final String SOURCE = "Display.update";
    private static final String HOOK = "hypernova/agent/FrameProbe";

    @Override
    public byte[] transform(ClassLoader loader, String className, Class<?> redefined,
                            ProtectionDomain protectionDomain, byte[] bytes) {
        if (className == null || redefined != null || bytes == null) {
            return null;
        }
        if (!TARGET.equals(className)) {
            return null;
        }
        try {
            ClassReader reader = new ClassReader(bytes);
            ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
            boolean[] patched = {false};
            ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
                @Override
                public MethodVisitor visitMethod(int access, String name, String desc,
                                                 String signature, String[] exceptions) {
                    MethodVisitor mv = super.visitMethod(access, name, desc, signature, exceptions);
                    if (!METHOD.equals(name)
                            || !("()V".equals(desc) || "(Z)V".equals(desc))) {
                        return mv;
                    }
                    patched[0] = true;
                    return new MethodVisitor(Opcodes.ASM9, mv) {
                        @Override
                        public void visitCode() {
                            super.visitCode();
                            super.visitLdcInsn(SOURCE);
                            super.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK,
                                    "frame", "(Ljava/lang/String;)V", false);
                        }
                    };
                }
            };
            reader.accept(visitor, 0);
            if (!patched[0]) {
                AgentLog.info("frame probe: Display.update overload missing; no samples");
                return null;
            }
            AgentLog.info("frame probe: hook added to Display.update");
            return writer.toByteArray();
        } catch (Throwable t) {
            AgentLog.fail("frame probe: Display transform failed", t);
            return null;
        }
    }
}
```

- [ ] **Step 5: 接线 `HypernovaAgent.premain`**

在 `AgentLog.init(ctx.logFile());` 之后、`StartupTimeline.start();` 之前插入：

```java
            if (Boolean.getBoolean("hypernova.frameProbe")) {
                instrumentation.addTransformer(new FrameProbeTransformer(), false);
                AgentLog.info("frame probe: enabled (-Dhypernova.frameProbe=true);"
                        + " hook Display.update, log every 600 frames");
            }
```

并在 import 区加 `import hypernova.agent.FrameProbeTransformer;`（同包，可省略 import；若同包则不加）。

- [ ] **Step 6: 运行测试**

Run:
```bash
bash tools/java/run-agent-tests.sh FrameProbe
bash tools/java/run-agent-tests.sh
```
Expected: 新增 3 个测试类全绿；全量 agent 仍 197+ tests / 0 fail（1 个已知 symlink abort）。

- [ ] **Step 7: 提交**

```bash
git add src/agent/java/hypernova/agent/FrameProbe.java \
        src/agent/java/hypernova/agent/FrameProbeTransformer.java \
        src/agent/java/hypernova/agent/HypernovaAgent.java \
        tests/agent/java/hypernova/agent/FrameProbeTest.java \
        tests/agent/java/hypernova/FrameProbeTransformTest.java \
        tests/agent/java/hypernova/FrameProbeWiringTest.java
git commit -m "feat(m4.1): add agent-side frame probe"
```

---

### Task 2: 报告工具解析 agent 日志帧行

**Files:**
- Modify: `tools/m4_session_report.py`
- Test: `tests/tools/test_m4_session_report.py`

**Interfaces:**
- Consumes: Task 1 的 `HYPERNOVA_FRAME` 行与 `hypernova agent premain` anchor。
- Produces:
  - `agent_session_text(text) -> (session, anchor_line, anchor_count)`
  - `find_frame_probe(text, line_base=0) -> dict`（新增 `file_line = line + line_base`）
  - `build_report(...)` 的 `frame_probe.source` 为 `agent|game|none`；agent 优先。

**Dependencies:** Task 1
**Touches:** `tools/m4_session_report.py`, `tests/tools/test_m4_session_report.py`

- [ ] **Step 1: 写失败测试**

在 `tests/tools/test_m4_session_report.py` 追加：

```python
AGENT_FRAME = ("2026-11-03T00:00:00Z INFO frame probe: enabled\n"
               "2026-11-03T00:00:01Z INFO frame probe: samples started from Display.update\n"
               + FRAME + "\n")


def test_agent_frame_probe_is_used_when_game_has_none(tmp_path):
    agent, log = _write_session(
        tmp_path, "Fast Rendering: v0.9.7rc2\nno frame here\n")
    agent.write_text("hypernova agent premain\n" + AGENT_FRAME, encoding="utf-8")
    report = report_mod.build_report(
        agent.read_text(encoding="utf-8"), log.read_text(encoding="utf-8"))
    assert report["frame_probe"]["present"] is True
    assert report["frame_probe"]["source"] == "agent"
    assert report["frame_probe"]["frames"] == 600


def test_agent_frame_probe_is_preferred_when_both_exist(tmp_path):
    agent, log = _write_session(
        tmp_path, "Fast Rendering: v0.9.7rc2\n" + FRAME.replace("frames=600", "frames=700") + "\n")
    agent.write_text("hypernova agent premain\n" + AGENT_FRAME, encoding="utf-8")
    report = report_mod.build_report(
        agent.read_text(encoding="utf-8"), log.read_text(encoding="utf-8"))
    assert report["frame_probe"]["source"] == "agent"
    assert report["frame_probe"]["frames"] == 600


def test_require_frame_accepts_agent_source(tmp_path):
    agent, log = _write_session(
        tmp_path, "Fast Rendering: v0.9.7rc2\nno frame here\n")
    agent.write_text("hypernova agent premain\n" + AGENT_FRAME, encoding="utf-8")
    out = tmp_path / "report.json"
    assert report_mod.main(["--agent-log", str(agent), "--starsector-log", str(log),
                            "--out", str(out), "--require-frame"]) == 0
```

- [ ] **Step 2: 运行确认失败**

Run: `python -I -m pytest tests/tools/test_m4_session_report.py -q`
Expected: 3 new tests fail (`source` missing / no agent parsing).

- [ ] **Step 3: 修改 `tools/m4_session_report.py`**

1. `find_frame_probe(text, line_base=0)`：把 `"line": found_line` 改为
```python
"line": found_line,
"file_line": found_line + line_base,
```
并为 absent 分支保留 `"file_line": 0`。

2. 新增：
```python
def agent_session_text(text: str) -> tuple[str, int | None, int]:
    lines = text.splitlines(keepends=True)
    anchors = [i for i, line in enumerate(lines)
               if AGENT_SESSION_ANCHOR in line]
    if not anchors:
        return text, None, 0
    index = anchors[-1]
    return "".join(lines[index + 1:]), index + 1, len(anchors)
```

3. `build_report` 中替换 frame 查找：
```python
    game_frame = find_frame_probe(
        session, line_base=(anchor_line - 1) if anchor_found else 0)
    agent_session, agent_anchor_line, agent_anchor_count = agent_session_text(agent_text)
    agent_frame = find_frame_probe(
        agent_session, line_base=agent_anchor_line or 0)
    if agent_frame["present"]:
        frame = agent_frame
        frame["source"] = "agent"
    elif game_frame["present"]:
        frame = game_frame
        frame["source"] = "game"
    else:
        frame = game_frame
        frame["source"] = "none"
```
（`health` 与后续逻辑继续用 `frame`。）

4. `human_text` 的 frame 行加来源：
```python
        lines.append("frame: source={} frames={frames} over200={over200} "
                     ...
                     .format(frame.get("source", "none"), **frame))
```
若 `.format(**frame)` 因新增键冲突报错，改用显式 `frame.get(...)`。

- [ ] **Step 4: 运行测试**

Run:
```bash
python -I -m pytest tests/tools/test_m4_session_report.py -q
python -I -m pytest tests/tools -q
```
Expected: 新测试 + 原测试全绿。

- [ ] **Step 5: 提交**

```bash
git add tools/m4_session_report.py tests/tools/test_m4_session_report.py
git commit -m "feat(m4.1): read frame probe from the agent log"
```

---

### Task 3: 文档 + 实机 smoke 证据 + 收口

**Files:**
- Modify: `docs/m4-manual-acceptance.md`
- Modify: `docs/m4-results.md`
- Modify: `技术笔记-纹理按需加载.md` §7
- Modify: `docs/superpowers/plans/2026-11-03-m41-agent-frame-probe.md`（本文件，提交）

**Interfaces:**
- Consumes: Task 1/2 的 agent 日志帧行与报告 `source=agent`。
- Produces: 可执行的 agent-only A→B 协议；M4.1 结果段。

**Dependencies:** Task 1, Task 2
**Touches:** the four files above

- [ ] **Step 1: 更新 `docs/m4-manual-acceptance.md`**

- §1 前置：删掉“启用主 mod / `enabled_mods.json` 备份恢复”的强制步骤；改成“probe 在 agent 里，260mods agent-only 即可”。保留 build-mod/install-manifest/install_agent、日志清理、干净存档。
- §2 启动参数：仍从 `Miko_Lite_m28_treatment.txt` 派生 `Miko_Lite_m4_probe.txt`，但只要求插入 `-Dhypernova.frameProbe=true`（lazy flags 由 treatment 模板自带；若只想测 probe 可关 lazy）；强调 `-D` 在主类之前。
- §3 启动检查：`grep -c "frame probe: enabled"` 与 `grep -c "samples started from Display.update"` 在 `scripts-agent.log`；`Display.update` 覆盖 title/campaign/combat，不再区分状态来源。
- §4/5：`HYPERNOVA_FRAME` 行在 `scripts-agent.log`；报告工具同时读 agent/game 日志；frame 计数从 JVM 启动（含 title/menu/load）累计，B-only = B−A；max/p99 不可相减；GPU 用独立 `gpu-a.csv`/`gpu-b.csv`，B 用同一 PID。**报告工具要求 lazy summary**，所以 A→B 会话保持 lazy 开启（treatment 模板自带）；不要用 probe-only 的懒关闭会话去跑报告。
- 删除/降级 Base 替代为“可选完整产品环境”，不再要求启用主 mod。

- [ ] **Step 2: 更新 `docs/m4-results.md`**

追加 `## M4.1 agent-side frame probe`：
- 说明 probe 现在由 `-javaagent` agent 注入 `org.lwjgl.opengl.Display.update`（两个重载），260mods agent-only 可用；主 mod probe 保留给完整产品。
- 记录 smoke 证据（实际数字）：`frame probe: enabled`、`samples started from Display.update`、`HYPERNOVA_FRAME` 行、report `source=agent`、rc0。
- 明确：`Display.update` 覆盖战斗帧循环，但 A→B/stutter 仍未执行；不要把菜单 smoke 当成战斗验收。
- 更新 I-5 限制：agent-only 配置现在有 probe；仍不能把主 mod/agent 两条来源混用。

- [ ] **Step 3: 更新 spec §7**

在 M4 行后追加 M4.1：
`**M4.1（agent-side frame probe）✔（2026-11-03；agent-only 260mods 可采样；A→B/stutter 用户 gate 仍未执行）**`。

- [ ] **Step 4: 构建/安装/实机 smoke**

Run:
```bash
bash tools/java/run-agent-tests.sh
python -I -m pytest tests/tools -q
bash tools/java/build-mod.sh
bash tools/java/install-manifest.sh Starsector-098-260mods
python tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite
python -I tools/smoke_run.py --profile miko-lite --rounds 1 --linger 20 \
  --jvm-arg=-Dhypernova.frameProbe=true \
  --jvm-arg=-Dhypernova.textures.lazy=true \
  --jvm-arg=-Dhypernova.textures.lazy.dds=true \
  --json-out build/m41/smoke-probe.json
python -I tools/m4_session_report.py \
  --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
  --starsector-log Starsector-098-260mods/starsector-core/starsector.log \
  --out build/m41/smoke-report.json --require-frame --text
```
Expected:
- agent tests 全绿；
- pytest 全绿；
- `scripts-agent.log` 最后会话有 `frame probe: enabled`、`samples started from Display.update`、至少一条 `HYPERNOVA_FRAME`（20 s linger 应 ≥600 帧）；
- report rc0，`frame_probe.source=agent`、`present=true`、`frames>0`；
- 0 纹理错误、lazy summary 健康。**注意**：`m4_session_report.py` 当前在默认与 `--require-frame` 下都要求 lazy summary（M4 的 fail-closed 设计），所以本 smoke 必须带 lazy 开关；不要为了 probe-only 临时放宽这个门禁。

- [ ] **Step 5: 写结果并提交**

把 Step 4 的实际数字填入 `docs/m4-results.md` 的 M4.1 段。提交：
```bash
git add docs/m4-manual-acceptance.md docs/m4-results.md \
        技术笔记-纹理按需加载.md \
        docs/superpowers/plans/2026-11-03-m41-agent-frame-probe.md
git commit -m "docs(m4.1): record agent-side frame probe and smoke evidence"
```

---

## Self-Review

| 需求 | 任务 |
|---|---|
| agent-only 260mods 能采样 | Task 1 + Task 3 smoke |
| campaign/title + combat 覆盖 | Task 1 transformer 两个目标；Task 3 用户战斗确认 |
| 默认 off / lazy/FR/scripts 无关 | Task 1 wiring + property |
| 报告优先 agent、回退 game | Task 2 |
| 不混来源、不冒充 A→B 已通过 | Task 2 `source` + Task 3 文档 |
| 默认值不变 | 无配置改动 |

### Placeholder scan

无 TBD/TODO；Task 3 的 smoke 数字由实际运行填写。

### Type consistency

- `FrameProbe.frame(String)` 与 transformer 的 `INVOKESTATIC ... frame (Ljava/lang/String;)V` 一致。
- `FrameProbe.State.sample(long)` 返回 `String|null`，测试与 `frame()` 使用一致。
- `find_frame_probe(text, line_base=0)` 与 `build_report`/tests 一致。
