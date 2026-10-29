# M-1d 脚本预编译缓存 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 Starsector 0.98a-RC8 + Fast Rendering 0.9.5 增加一个可选的 `-javaagent`，把 Janino 启动期脚本编译结果跨启动缓存，目标把 260mods 首屏从 86.5 s 降到 ~62–66 s。

**Architecture:** 一个独立 agent jar 在 FR 的 `MultiThreadedJaninoClassLoader` 构造函数末尾注入 `preload(this)`，把磁盘缓存 `putAll` 进该 loader 的共享 `bytecodeCache`；类仍由原 loader 的 `findClass`→`defineClass` 定义。另在 `findClass` 入口注入计数钩子，得到真实的命中/未命中（= 实际编译）数。缓存按内容指纹分代，单 pack 顺序读写，原子替换。纯 mod 无法做到（脚本在任何 mod 回调之前编译完），所以本里程碑是 Form B 的 `scripts` 模块。

**Tech Stack:** Java 17（`--release 17`）、ASM 9.1（从 `fr.agent.jar` 内嵌的 `asm-9.1.jar` 提取）、`org.json`（游戏自带 `json.jar`）、Janino 2.7.8（Base）/ 3.0.12（260mods Miko）、JUnit 5、Python 3（安装/解析工具）。

**Spec:** `调研-Java脚本预编译缓存.md` §0/§4.1/§7/§10；`技术笔记-纹理按需加载.md` §4.6/§5.8/§7。规格是权威，本计划是论证；冲突时按规格裁决并记入 ledger。

## Global Constraints

- 编译必须 `--release 17`，产物 class major version 必须是 61（`javap -verbose` 校验）。
- agent 是**可选件**：缺失、配置关闭、FR 缺失、结构探针失败 → 只禁用 `scripts`，游戏必须照常启动。
- **不改 `src/main/java/hypernova/**`**（M1 textures 模块冻结）；只允许改 `data/config/hypernova/hypernova.json`、构建/安装脚本、新增 `src/agent/java/**` 与 `tests/agent/**`。
- agent 代码**禁止在编译期引用 `com.genir.*`**；拦截点用类名字符串 + 反射，保证无 FR 时也能加载。
- ASM 只用从 `Starsector-098-Base/starsector-core/fr.agent.jar` 提取的 `asm-9.1.jar`；不新增网络下载。
- agent 的所有读写必须落在 `<saves>/hypernova/` 下；除安装器复制 agent jar 外，不写游戏安装目录。
- 缓存键必须覆盖：源文件内容（sha256）、jar 内容、游戏/FR/Janino 版本（由 jar 内容体现）、classpath 顺序、`enabled_mods.json`；任何一项变化 → miss。
- 只 preload FR loader 已有的 `bytecodeCache`；**绝不**创建第二个脚本 loader、绝不自己 `defineClass` 到别的 loader。
- 所有钩子必须 `catch (Throwable)`；任何 agent 异常都不能抛回游戏。
- 安装器必须幂等、先备份（`*.bak-hypernova`）、可卸载；agent 行必须在 FR agent 行**之后**。
- 启动参数文件按 LF 写入（M1 已证实 argfile 必须 LF；Windows CRLF 会坏）。
- 遥测 JSONL：UTF-8、一行一事件、append；不修改 M1 的 `telemetry.jsonl.data` schema。
- 测试除非 Task 6 的 runbook，不得启动游戏；不得执行 `taskkill //F //IM node.exe`。
- 现有 `tools/java/run-tests.sh`（M1 测试）不改；agent 用独立的 `tools/java/run-agent-tests.sh`。
- 每个任务一个独立 commit；commit message 以 `feat(m1d):`/`fix(m1d):`/`docs(m1d):` 开头，并附 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。

## Escape Hatch

- 若计划里的断言数字、测试顺序、文件路径或方法描述符与实际实现不符 → **按实际修正并报告**（写进 `task-N-report.md`），无需请示。
- 若需求自相矛盾或无法同时满足 → **停下报告 controller，不许挑一半照做**。把矛盾的两条原文、为什么不能同时成立、你建议的裁决写清楚。
- 本计划按 pipeline 执行：只改本任务 `Touches:` 声明内的文件；需要越界 → 停下报告，等 controller 裁决（不要顺手改 `src/main/java/hypernova/**`）。
- 若 Task 1 的人口门禁不通过 → 停，不要继续 Task 2；报告实测数字与建议。

## Review Focus

1. **缓存键漏输入 → 旧类被加载**：改一个 `.java`/`.jar`/classpath 顺序/`enabled_mods.json` 后必须换 key；Task 2 的 key 测试覆盖。
2. **构造函数注入在真实 FR loader 上不触发**（描述符/版本变了）：Task 1 的 fake loader 测试 + Task 6 的 S3 遥测 `preload` 事件双重覆盖。
3. **坏/截断 pack 导致崩溃或无回退**：Task 2/3 的 corrupt pack 测试；游戏必须继续走 Janino。
4. **安装器重复/错序 `-javaagent`**：Task 4 的 patch 测试断言只插一次且紧跟 FR；卸载可还原。
5. **`findClass` 注入破坏栈帧/验证**：Task 1 的 transformed fake class 必须能定义并实例化；Task 6 的 S3 真实启动是最终证据。

## File Structure

| 路径 | 责任 |
|---|---|
| `src/agent/java/hypernova/agent/HypernovaAgent.java` | `premain`，配置/FR 探针，注册 transformer，shutdown/summary 线程 |
| `src/agent/java/hypernova/agent/ScriptCacheTransformer.java` | ASM 注入：构造函数末尾 `preload(this)`；`findClass` 入口 `onFindClass(this,name)` |
| `src/agent/java/hypernova/agent/ScriptCacheHook.java` | 反射取 `bytecodeCache`；preload/命中计数/shutdown |
| `src/agent/java/hypernova/agent/RuntimeContext.java` | 路径/配置/遥测的运行时上下文（可从环境或测试构造） |
| `src/agent/java/hypernova/agent/ScriptCacheConfig.java` | 读 `hypernova.json` 的 `scripts` 段 |
| `src/agent/java/hypernova/agent/ScriptCacheKey.java` | 收集输入文件、算 fingerprint |
| `src/agent/java/hypernova/agent/KeyManifest.java` | stat/sha256 清单缓存，避免每次全量读 |
| `src/agent/java/hypernova/agent/CachePack.java` | 单 pack 读写（magic/version/count/CRC32） |
| `src/agent/java/hypernova/agent/CacheStore.java` | 按 key 分代、原子替换、LRU/大小清理 |
| `src/agent/java/hypernova/agent/CacheWriter.java` | 冷启动后把新编译条目落盘；shutdown flush |
| `src/agent/java/hypernova/agent/AgentTelemetry.java` | JSONL：preload/write/summary |
| `src/agent/java/hypernova/agent/AgentLog.java` | 独立日志（不依赖 log4j） |
| `src/agent/java/hypernova/agent/tools/CacheTool.java` | `key`/`inspect`/`seed` 诊断工具（S3 用） |
| `tools/java/build-agent.sh` | 构建 agent jar（含 ASM） |
| `tools/java/run-agent-tests.sh` | agent 单测 |
| `tools/java/build-agent-tools.sh` | 构建 `CacheTool` |
| `tools/install_agent.py` | 安装/卸载 Base 与 260mods 的 `-javaagent` |
| `tools/java/parse_script_telemetry.py` | 从 JSONL 汇总 hit/miss/span |
| `tests/agent/fixtures/com/genir/renderer/overrides/loading/MultiThreadedJaninoClassLoader.java` | 与 FR 同形的最小 fake loader |
| `tests/agent/java/hypernova/agent/*Test.java` | transformer/preload/key/pack/store/writer/telemetry 测试 |
| `tests/tools/test_install_agent.py` | 安装器幂等/顺序/卸载测试 |
| `data/config/hypernova/hypernova.json` | 增加 `scripts` 段（向后兼容，M1 忽略未知键） |

---

### Task 1: Agent 骨架 + 注入 + 真实编译人口测量

**Files:**
- Create: `src/agent/java/hypernova/agent/HypernovaAgent.java`
- Create: `src/agent/java/hypernova/agent/ScriptCacheTransformer.java`
- Create: `src/agent/java/hypernova/agent/ScriptCacheHook.java`（本任务只做计数/no-op preload）
- Create: `src/agent/java/hypernova/agent/RuntimeContext.java`
- Create: `src/agent/java/hypernova/agent/ScriptCacheConfig.java`
- Create: `src/agent/java/hypernova/agent/AgentTelemetry.java`
- Create: `src/agent/java/hypernova/agent/AgentLog.java`
- Create: `tools/java/build-agent.sh`
- Create: `tools/java/run-agent-tests.sh`
- Create: `tests/agent/fixtures/com/genir/renderer/overrides/loading/MultiThreadedJaninoClassLoader.java`
- Test: `tests/agent/java/hypernova/agent/ScriptCacheTransformerTest.java`

**Interfaces:**
- Consumes: 无（本任务自包含）。
- Produces:
  - `HypernovaAgent.premain(String, java.lang.instrument.Instrumentation)`
  - `ScriptCacheTransformer.TARGET = "com/genir/renderer/overrides/loading/MultiThreadedJaninoClassLoader"`
  - `ScriptCacheTransformer.HOOK = "hypernova/agent/ScriptCacheHook"`
  - `ScriptCacheHook.preload(Object loader)`
  - `ScriptCacheHook.onFindClass(Object loader, String name)`
  - `ScriptCacheHook.setContext(RuntimeContext)`（package-private）
  - `ScriptCacheHook.preloadCalls()/findCalls()/hits()/misses()/spanMillis()`（package-private）
  - `ScriptCacheHook.resetForTest()`（package-private）
  - `RuntimeContext.fromEnvironment()`；`RuntimeContext(Path gameRoot, Path modsRoot, Path savesRoot, Path cacheRoot, Path logFile, Path telemetryFile, ScriptCacheConfig config)`
  - `ScriptCacheConfig.load(Path)`；`ScriptCacheConfig.disabled()`
  - `AgentTelemetry.event(String kind, String key, long entries, long bytes, long millis)`；`summary(String key, long hits, long misses, long findCalls, long spanMillis, long entries)`；`close()`
- Dependencies: 无
- Touches: `src/agent/java/hypernova/agent/{HypernovaAgent,ScriptCacheTransformer,ScriptCacheHook,RuntimeContext,ScriptCacheConfig,AgentTelemetry,AgentLog}.java`、`tools/java/{build-agent,run-agent-tests}.sh`、`tests/agent/fixtures/**`、`tests/agent/java/hypernova/agent/ScriptCacheTransformerTest.java`

- [ ] **Step 1: 写失败测试（transformer 注入 + 计数）**

`tests/agent/java/hypernova/agent/ScriptCacheTransformerTest.java`:

```java
package hypernova.agent;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.lang.reflect.InvocationTargetException;

import static org.junit.jupiter.api.Assertions.*;

class ScriptCacheTransformerTest {

    @BeforeEach
    void reset() {
        ScriptCacheHook.resetForTest();
    }

    @Test
    void injectsPreloadIntoConstructorAndCountsFindClass() throws Exception {
        byte[] original = readClassBytes();
        byte[] transformed = new ScriptCacheTransformer().transform(
                getClass().getClassLoader(), ScriptCacheTransformer.TARGET, null, null, original);
        assertNotNull(transformed, "transformer must return bytes for the target class");
        assertTrue(new String(transformed, java.nio.charset.StandardCharsets.ISO_8859_1)
                .contains("hypernova/agent/ScriptCacheHook"), "injected hook reference missing");

        ByteArrayClassLoader loader = new ByteArrayClassLoader(getClass().getClassLoader());
        Class<?> cls = loader.define(ScriptCacheTransformer.TARGET.replace('/', '.'),
                transformed);

        long beforePreload = ScriptCacheHook.preloadCalls();
        Object instance = cls.getConstructor(ClassLoader.class).newInstance(getClass().getClassLoader());
        assertEquals(beforePreload + 1, ScriptCacheHook.preloadCalls(),
                "constructor must call ScriptCacheHook.preload(this) exactly once");

        long beforeFind = ScriptCacheHook.findCalls();
        var findClass = cls.getDeclaredMethod("findClass", String.class);
        findClass.setAccessible(true);
        assertThrows(InvocationTargetException.class,
                () -> findClass.invoke(instance, "does.not.Exist"));
        assertEquals(beforeFind + 1, ScriptCacheHook.findCalls(),
                "findClass entry must call ScriptCacheHook.onFindClass");
        assertEquals(1, ScriptCacheHook.misses());
    }

    private static byte[] readClassBytes() throws Exception {
        String resource = "/" + ScriptCacheTransformer.TARGET + ".class";
        try (InputStream in = ScriptCacheTransformerTest.class.getResourceAsStream(resource)) {
            assertNotNull(in, "fixture class not on test classpath: " + resource);
            return in.readAllBytes();
        }
    }

    static final class ByteArrayClassLoader extends ClassLoader {
        ByteArrayClassLoader(ClassLoader parent) { super(parent); }
        Class<?> define(String name, byte[] bytes) { return defineClass(name, bytes, 0, bytes.length); }
    }
}
```

`tests/agent/fixtures/com/genir/renderer/overrides/loading/MultiThreadedJaninoClassLoader.java`:

```java
package com.genir.renderer.overrides.loading;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/** 与 FR 0.9.5 同形的最小 fake：字段名、构造器描述符、findClass 语义一致。 */
public class MultiThreadedJaninoClassLoader extends ClassLoader {
    private final Map<String, byte[]> bytecodeCache = new ConcurrentHashMap<>();

    public MultiThreadedJaninoClassLoader(ClassLoader parent) {
        super(parent);
    }

    @Override
    protected Class<?> findClass(String name) throws ClassNotFoundException {
        byte[] b = bytecodeCache.get(name);
        if (b == null) throw new ClassNotFoundException(name);
        return defineClass(name, b, 0, b.length);
    }

    public Map<String, byte[]> bytecodeCache() {
        return bytecodeCache;
    }
}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash tools/java/run-agent-tests.sh ScriptCacheTransformerTest`
Expected: 编译失败或 FAIL（`HypernovaAgent`/`ScriptCacheTransformer`/`ScriptCacheHook` 不存在）。若 `run-agent-tests.sh` 也不存在，先用 Step 3 的脚本内容创建它；但本步必须先看到“实现缺失”的失败，而不是脚本缺失的 `command not found`。

- [ ] **Step 3: 实现 agent 骨架与注入**

`src/agent/java/hypernova/agent/AgentLog.java`:

```java
package hypernova.agent;

import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;

public final class AgentLog {
    private static volatile Path file;

    private AgentLog() {
    }

    public static void init(Path path) {
        file = path;
        try {
            if (path != null && path.getParent() != null) Files.createDirectories(path.getParent());
        } catch (IOException e) {
            System.err.println("hypernova-agent: cannot create log dir: " + e);
        }
    }

    public static void info(String msg) {
        write("INFO", msg, null);
    }

    public static void fail(String msg, Throwable t) {
        write("ERROR", msg, t);
    }

    private static synchronized void write(String level, String msg, Throwable t) {
        StringBuilder sb = new StringBuilder();
        sb.append(Instant.now()).append(' ').append(level).append(' ').append(msg);
        if (t != null) {
            StringWriter sw = new StringWriter();
            t.printStackTrace(new PrintWriter(sw));
            sb.append('\n').append(sw);
        }
        sb.append('\n');
        System.err.print(sb);
        Path f = file;
        if (f == null) return;
        try {
            Files.writeString(f, sb.toString(), StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        } catch (IOException ignored) {
            // agent 日志失败不能影响游戏
        }
    }
}
```

`src/agent/java/hypernova/agent/ScriptCacheConfig.java`:

```java
package hypernova.agent;

import org.json.JSONObject;

import java.nio.file.Files;
import java.nio.file.Path;

public record ScriptCacheConfig(boolean scriptsEnabled, long cacheMaxBytes, int cacheGenerations,
                                long preloadMaxMillis, boolean verbose) {

    public static ScriptCacheConfig load(Path file) {
        if (file == null || !Files.isRegularFile(file)) return disabled();
        try {
            JSONObject root = new JSONObject(Files.readString(file));
            JSONObject s = root.optJSONObject("scripts");
            if (s == null) {
                // agent 已安装但配置没有 scripts 段：默认开启；显式 enabled=false 才关闭
                return new ScriptCacheConfig(true, 2L << 30, 2, 3000, false);
            }
            return new ScriptCacheConfig(
                    s.optBoolean("enabled", true),
                    Math.max(0, s.optLong("cache_max_bytes", 2L << 30)),
                    Math.max(1, s.optInt("cache_generations", 2)),
                    Math.max(250, s.optLong("preload_max_millis", 3000)),
                    s.optBoolean("verbose", false));
        } catch (Throwable t) {
            AgentLog.fail("scripts config parse failed: " + file, t);
            return disabled();
        }
    }

    public static ScriptCacheConfig disabled() {
        return new ScriptCacheConfig(false, 0, 1, 250, false);
    }
}
```

`src/agent/java/hypernova/agent/AgentTelemetry.java`:

```java
package hypernova.agent;

import org.json.JSONObject;

import java.io.BufferedWriter;
import java.io.Closeable;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class AgentTelemetry implements Closeable {
    private final BufferedWriter out;

    public AgentTelemetry(Path file) {
        BufferedWriter w = null;
        try {
            Files.createDirectories(file.getParent());
            w = Files.newBufferedWriter(file, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        } catch (IOException e) {
            AgentLog.fail("telemetry open failed: " + file, e);
        }
        this.out = w;
    }

    public synchronized void event(String kind, String key, long entries, long bytes, long millis) {
        JSONObject o = new JSONObject();
        o.put("t", System.currentTimeMillis());
        o.put("kind", kind);
        o.put("key", key);
        o.put("entries", entries);
        o.put("bytes", bytes);
        o.put("millis", millis);
        write(o);
    }

    public synchronized void summary(String key, long hits, long misses, long findCalls,
                                     long spanMillis, long entries) {
        JSONObject o = new JSONObject();
        o.put("t", System.currentTimeMillis());
        o.put("kind", "summary");
        o.put("key", key);
        o.put("hits", hits);
        o.put("misses", misses);
        o.put("find_calls", findCalls);
        o.put("span_millis", spanMillis);
        o.put("entries", entries);
        o.put("hit_rate", findCalls == 0 ? 0.0 : (double) hits / findCalls);
        write(o);
    }

    private void write(JSONObject o) {
        if (out == null) return;
        try {
            out.write(o.toString());
            out.write('\n');
            out.flush();
        } catch (IOException e) {
            AgentLog.fail("telemetry write failed", e);
        }
    }

    @Override
    public synchronized void close() {
        if (out == null) return;
        try {
            out.close();
        } catch (IOException ignored) {
        }
    }
}
```

`src/agent/java/hypernova/agent/RuntimeContext.java`:

```java
package hypernova.agent;

import java.nio.file.Files;
import java.nio.file.Path;

public final class RuntimeContext {
    private final Path gameRoot;
    private final Path modsRoot;
    private final Path savesRoot;
    private final Path cacheRoot;
    private final Path logFile;
    private final Path telemetryFile;
    private final ScriptCacheConfig config;
    private final AgentTelemetry telemetry;

    public RuntimeContext(Path gameRoot, Path modsRoot, Path savesRoot, Path cacheRoot,
                          Path logFile, Path telemetryFile, ScriptCacheConfig config) {
        this.gameRoot = gameRoot;
        this.modsRoot = modsRoot;
        this.savesRoot = savesRoot;
        this.cacheRoot = cacheRoot;
        this.logFile = logFile;
        this.telemetryFile = telemetryFile;
        this.config = config;
        this.telemetry = new AgentTelemetry(telemetryFile);
    }

    public static RuntimeContext fromEnvironment() {
        Path cwd = Path.of(System.getProperty("user.dir", ".")).toAbsolutePath().normalize();
        Path gameRoot = cwd.getFileName() != null
                && cwd.getFileName().toString().equals("starsector-core")
                ? cwd.getParent() : cwd;
        Path mods = resolve("com.fs.starfarer.settings.paths.mods", cwd, gameRoot.resolve("mods"));
        Path saves = resolve("com.fs.starfarer.settings.paths.saves", cwd, gameRoot.resolve("saves"));
        ScriptCacheConfig config = ScriptCacheConfig.load(locateConfig(gameRoot));
        Path hypernova = saves.resolve("hypernova");
        return new RuntimeContext(gameRoot, mods, saves,
                hypernova.resolve("scripts-cache"),
                hypernova.resolve("scripts-agent.log"),
                hypernova.resolve("scripts-telemetry.jsonl"),
                config);
    }

    private static Path resolve(String prop, Path cwd, Path fallback) {
        String v = System.getProperty(prop);
        Path p = (v == null || v.isBlank()) ? fallback : Path.of(v);
        if (!p.isAbsolute()) p = cwd.resolve(p);
        return p.normalize();
    }

    private static Path locateConfig(Path gameRoot) {
        try {
            var src = HypernovaAgent.class.getProtectionDomain().getCodeSource();
            if (src != null && src.getLocation() != null) {
                Path jar = Path.of(src.getLocation().toURI());
                Path modRoot = jar.getParent() == null ? null : jar.getParent().getParent();
                if (modRoot != null) {
                    Path f = modRoot.resolve("data/config/hypernova/hypernova.json");
                    if (Files.isRegularFile(f)) return f;
                }
            }
        } catch (Throwable ignored) {
        }
        Path f = gameRoot.resolve("mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json");
        return Files.isRegularFile(f) ? f : null;
    }

    public Path gameRoot() { return gameRoot; }
    public Path modsRoot() { return modsRoot; }
    public Path savesRoot() { return savesRoot; }
    public Path cacheRoot() { return cacheRoot; }
    public Path logFile() { return logFile; }
    public Path telemetryFile() { return telemetryFile; }
    public ScriptCacheConfig config() { return config; }
    public AgentTelemetry telemetry() { return telemetry; }
}
```

`src/agent/java/hypernova/agent/ScriptCacheTransformer.java`:

```java
package hypernova.agent;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class ScriptCacheTransformer implements ClassFileTransformer {
    public static final String TARGET =
            "com/genir/renderer/overrides/loading/MultiThreadedJaninoClassLoader";
    public static final String HOOK = "hypernova/agent/ScriptCacheHook";
    static final String CTOR_DESC = "(Ljava/lang/ClassLoader;)V";
    static final String FIND_DESC = "(Ljava/lang/String;)Ljava/lang/Class;";

    @Override
    public byte[] transform(ClassLoader loader, String className, Class<?> redefined,
                            ProtectionDomain protectionDomain, byte[] bytes) {
        if (className == null || !TARGET.equals(className) || redefined != null) return null;
        try {
            ClassReader reader = new ClassReader(bytes);
            ClassWriter writer = new ClassWriter(reader, 0);
            ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
                @Override
                public MethodVisitor visitMethod(int access, String name, String descriptor,
                                                 String signature, String[] exceptions) {
                    MethodVisitor mv = super.visitMethod(access, name, descriptor, signature, exceptions);
                    if ("<init>".equals(name) && CTOR_DESC.equals(descriptor)) {
                        return new MethodVisitor(Opcodes.ASM9, mv) {
                            @Override
                            public void visitInsn(int opcode) {
                                if (opcode == Opcodes.RETURN) {
                                    super.visitVarInsn(Opcodes.ALOAD, 0);
                                    super.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK, "preload",
                                            "(Ljava/lang/Object;)V", false);
                                }
                                super.visitInsn(opcode);
                            }
                        };
                    }
                    if ("findClass".equals(name) && FIND_DESC.equals(descriptor)) {
                        return new MethodVisitor(Opcodes.ASM9, mv) {
                            @Override
                            public void visitCode() {
                                super.visitCode();
                                super.visitVarInsn(Opcodes.ALOAD, 0);
                                super.visitVarInsn(Opcodes.ALOAD, 1);
                                super.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK, "onFindClass",
                                        "(Ljava/lang/Object;Ljava/lang/String;)V", false);
                            }
                        };
                    }
                    return mv;
                }
            };
            reader.accept(visitor, 0);
            return writer.toByteArray();
        } catch (Throwable t) {
            AgentLog.fail("transform failed for " + className, t);
            return null;
        }
    }
}
```

`src/agent/java/hypernova/agent/ScriptCacheHook.java`（Task 1 版本；Task 3 会整体替换）:

```java
package hypernova.agent;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

public final class ScriptCacheHook {
    private static final AtomicInteger PRELOAD_CALLS = new AtomicInteger();
    private static final LongAdder FINDS = new LongAdder();
    private static final LongAdder HITS = new LongAdder();
    private static final LongAdder MISSES = new LongAdder();
    private static final AtomicLong FIRST = new AtomicLong(0);
    private static final AtomicLong LAST = new AtomicLong(0);
    private static volatile RuntimeContext context;
    private static volatile String currentKey = "";

    private ScriptCacheHook() {
    }

    public static void preload(Object loader) {
        PRELOAD_CALLS.incrementAndGet();
        AgentLog.info("preload hook fired: "
                + (loader == null ? "null" : loader.getClass().getName()));
    }

    public static void onFindClass(Object loader, String name) {
        long now = System.nanoTime();
        FIRST.compareAndSet(0, now);
        LAST.set(now);
        FINDS.increment();
        MISSES.increment();
    }

    public static void shutdown() {
        summaryTick();
    }

    public static void summaryTick() {
        RuntimeContext ctx = context;
        if (ctx != null) {
            ctx.telemetry().summary(currentKey, HITS.sum(), MISSES.sum(), FINDS.sum(),
                    spanMillis(), 0);
        }
    }

    static void setContext(RuntimeContext ctx) { context = ctx; }
    static long preloadCalls() { return PRELOAD_CALLS.get(); }
    static long findCalls() { return FINDS.sum(); }
    static long hits() { return HITS.sum(); }
    static long misses() { return MISSES.sum(); }

    static long spanMillis() {
        long first = FIRST.get();
        long last = LAST.get();
        return first == 0 || last < first ? 0 : (last - first) / 1_000_000;
    }

    static void resetForTest() {
        PRELOAD_CALLS.set(0);
        FINDS.reset();
        HITS.reset();
        MISSES.reset();
        FIRST.set(0);
        LAST.set(0);
        context = null;
        currentKey = "";
    }
}
```

`src/agent/java/hypernova/agent/HypernovaAgent.java`:

```java
package hypernova.agent;

import java.lang.instrument.Instrumentation;

public final class HypernovaAgent {
    private HypernovaAgent() {
    }

    public static void premain(String args, Instrumentation instrumentation) {
        try {
            RuntimeContext ctx = RuntimeContext.fromEnvironment();
            AgentLog.init(ctx.logFile());
            AgentLog.info("hypernova agent premain; config=" + ctx.config()
                    + ", cacheRoot=" + ctx.cacheRoot());
            ScriptCacheHook.setContext(ctx);
            if (!ctx.config().scriptsEnabled()) {
                AgentLog.info("scripts cache disabled by config");
                return;
            }
            if (!frPresent()) {
                AgentLog.info("FR missing; scripts cache disabled");
                return;
            }
            instrumentation.addTransformer(new ScriptCacheTransformer(), false);
            Runtime.getRuntime().addShutdownHook(new Thread(ScriptCacheHook::shutdown,
                    "Hypernova-ScriptCache-Shutdown"));
            Thread summary = new Thread(() -> {
                while (true) {
                    try {
                        Thread.sleep(30_000);
                    } catch (InterruptedException e) {
                        return;
                    }
                    ScriptCacheHook.summaryTick();
                }
            }, "Hypernova-ScriptCache-Summary");
            summary.setDaemon(true);
            summary.start();
            AgentLog.info("scripts cache transformer registered");
        } catch (Throwable t) {
            AgentLog.fail("agent init failed; scripts cache disabled", t);
        }
    }

    private static boolean frPresent() {
        try {
            Class.forName("com.genir.renderer.Version", false, ClassLoader.getSystemClassLoader());
            return true;
        } catch (Throwable t) {
            return false;
        }
    }
}
```

`tools/java/build-agent.sh`:

```bash
#!/usr/bin/env bash
# 用法: bash tools/java/build-agent.sh
# 产出 build/agent/hypernova.agent.jar（含 ASM 9.1）。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
ROOT_W="$(winpath "$ROOT")"
GAME="$ROOT_W/Starsector-098-Base/starsector-core"
OUT="$ROOT_W/build/agent"
mkdir -p "$OUT/lib" "$OUT/classes" "$OUT/asm"
if [ ! -f "$OUT/lib/asm-9.1.jar" ]; then
  unzip -p "$GAME/fr.agent.jar" asm-9.1.jar > "$OUT/lib/asm-9.1.jar"
fi
if [ ! -d "$OUT/asm/org" ]; then
  (cd "$OUT/asm" && unzip -oq "$OUT/lib/asm-9.1.jar" 'org/*')
fi
rm -rf "$OUT/classes"
mkdir -p "$OUT/classes"
find "$ROOT_W/src/agent/java" -name '*.java' ! -path '*/tools/*' > "$OUT/sources.txt"
javac --release 17 -encoding UTF-8 \
  -cp "$GAME/json.jar;$OUT/lib/asm-9.1.jar" \
  -d "$OUT/classes" @"$OUT/sources.txt"
bad=$(javap -verbose -cp "$OUT/classes" hypernova.agent.HypernovaAgent 2>/dev/null \
  | grep -c "major version: 61" || true)
if [ "$bad" -ne 1 ]; then echo "FATAL: agent class major version != 61" >&2; exit 1; fi
printf '%s\n' \
  'Manifest-Version: 1.0' \
  'Premain-Class: hypernova.agent.HypernovaAgent' \
  'Can-Retransform-Classes: false' > "$OUT/MANIFEST.MF"
jar --create --file "$OUT/hypernova.agent.jar" --manifest "$OUT/MANIFEST.MF" \
  -C "$OUT/classes" . -C "$OUT/asm" .
echo "OK: $OUT/hypernova.agent.jar"
```

`tools/java/run-agent-tests.sh`:

```bash
#!/usr/bin/env bash
# 用法: bash tools/java/run-agent-tests.sh [TestClassFilter]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
ROOT_W="$(winpath "$ROOT")"
GAME="$ROOT_W/Starsector-098-Base/starsector-core"
LIB="$ROOT_W/lib"
bash "$ROOT_W/tools/java/build-agent.sh"
ASM="$ROOT_W/build/agent/lib/asm-9.1.jar"
OUT="$ROOT_W/build/agent/run-$$-$(date +%s%N)"
mkdir -p "$OUT/classes" "$OUT/tests"
if [ ! -f "$LIB/junit-platform-console-standalone.jar" ]; then
  echo "missing $LIB/junit-platform-console-standalone.jar" >&2
  exit 2
fi
javac --release 17 -encoding UTF-8 -cp "$GAME/json.jar;$ASM" \
  -d "$OUT/classes" $(find "$ROOT_W/src/agent/java" -name '*.java' ! -path '*/tools/*')
find "$ROOT_W/tests/agent/java" -name '*.java' > "$OUT/test-sources.txt"
if [ -d "$ROOT_W/tests/agent/fixtures" ]; then
  find "$ROOT_W/tests/agent/fixtures" -name '*.java' >> "$OUT/test-sources.txt"
fi
javac --release 17 -encoding UTF-8 \
  -cp "$GAME/json.jar;$ASM;$OUT/classes;$LIB/junit-platform-console-standalone.jar" \
  -d "$OUT/tests" @"$OUT/test-sources.txt"
FILTER=".*"
if [ -n "${1:-}" ]; then FILTER=".*${1}.*"; fi
java -jar "$LIB/junit-platform-console-standalone.jar" \
  --class-path "$OUT/classes;$OUT/tests;$GAME/json.jar;$ASM" \
  --scan-class-path "$OUT/tests" \
  --include-classname="$FILTER" \
  --fail-if-no-tests
rm -rf "$OUT"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `bash tools/java/run-agent-tests.sh ScriptCacheTransformerTest`
Expected: `1 tests successful`（或 console 的 `tests succeeded`），且 `build/agent/hypernova.agent.jar` 已生成。

- [ ] **Step 5: 真实测量（Base 验机制，260mods 验人口）**

先做 Base（快，验证 hook 真的被调用）：

```bash
cp build/agent/hypernova.agent.jar Starsector-098-Base/mods/hypernova_infinite_engine/jars/
cd Starsector-098-Base/starsector-core
cp fr.vmparams fr.vmparams.bak-m1d
printf '%s\n' '-javaagent:../mods/hypernova_infinite_engine/jars/hypernova.agent.jar' >> fr.vmparams
cd ../..
```

启动 `Starsector-098-Base/启动-高性能.bat`，**人工点一次「开始游戏」**，进主菜单后等 40 s，读：

```bash
tail -5 Starsector-098-Base/saves/hypernova/scripts-telemetry.jsonl
```

确认 `Starsector-098-Base/saves/hypernova/scripts-agent.log` 出现 `preload hook fired`，且 telemetry 的 `summary.find_calls > 0`。关闭游戏，还原：

```bash
cp Starsector-098-Base/starsector-core/fr.vmparams.bak-m1d Starsector-098-Base/starsector-core/fr.vmparams
```

再做 260mods（真实人口；Task 4 之前手工装）：

```bash
mkdir -p Starsector-098-260mods/mods/hypernova_infinite_engine/jars
mkdir -p Starsector-098-260mods/mods/hypernova_infinite_engine/data/config/hypernova
cp build/agent/hypernova.agent.jar Starsector-098-260mods/mods/hypernova_infinite_engine/jars/
cp data/config/hypernova/hypernova.json \
  Starsector-098-260mods/mods/hypernova_infinite_engine/data/config/hypernova/
cd Starsector-098-260mods
cp Miko_Lite.txt Miko_Lite.txt.bak-m1d
printf '%s\n' '-javaagent:../mods/hypernova_infinite_engine/jars/hypernova.agent.jar' >> Miko_Lite.txt
cd ..
```

启动 `Starsector-098-260mods/启动-Miko省内存.bat`，人工点「开始游戏」，进主菜单后等 40 s，读：

```bash
tail -5 Starsector-098-260mods/saves/hypernova/scripts-telemetry.jsonl
```

记录 `find_calls`、`misses`、`span_millis`、`preload` 事件。**这是真实编译人口**：`find_calls` 是进入脚本 loader 的类数，不是日志里 “Compiling script” 的行数（后者是队列日志，包含 jar 命中）。关闭游戏，还原：

```bash
cp Starsector-098-260mods/Miko_Lite.txt.bak-m1d Starsector-098-260mods/Miko_Lite.txt
```

**门禁（以 260mods 的数字为准）**：若 `span_millis < 10_000` 或 `find_calls < 500`，停止本计划并报告——缓存能省的上限不足 10 s，M-1d 的收益假设不成立，需要回到 spec 重新裁决（可能转向 M-1b 或修订 G-01）。把 Base 与 260mods 的两组数字写进 `task-1-report.md`。Base 的数字只用于证明机制，不参与门禁。

- [ ] **Step 6: Commit**

```bash
git add src/agent/java tools/java/build-agent.sh tools/java/run-agent-tests.sh \
  tests/agent
git commit -m "feat(m1d): add agent skeleton, FR loader hooks and compile-population telemetry

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: 指纹 + pack + 分代存储

**Files:**
- Create: `src/agent/java/hypernova/agent/ScriptCacheKey.java`
- Create: `src/agent/java/hypernova/agent/KeyManifest.java`
- Create: `src/agent/java/hypernova/agent/CachePack.java`
- Create: `src/agent/java/hypernova/agent/CacheStore.java`
- Test: `tests/agent/java/hypernova/agent/ScriptCacheKeyTest.java`
- Test: `tests/agent/java/hypernova/agent/CachePackTest.java`
- Test: `tests/agent/java/hypernova/agent/CacheStoreTest.java`

**Interfaces:**
- Consumes: `RuntimeContext`、`AgentLog`（Task 1）。
- Produces:
  - `ScriptCacheKey.compute(RuntimeContext) -> ScriptCacheKey.Result`
  - `ScriptCacheKey.Result(String id, String canonical, int fileCount, long bytes, long elapsedMillis)`
  - `KeyManifest.load(Path) -> KeyManifest`
  - `KeyManifest.refresh(List<Path>) -> List<KeyManifest.Entry>`
  - `KeyManifest.Entry(String path, long size, long mtime, String sha256)`
  - `KeyManifest.save(Path)`
  - `CachePack.read(Path) -> CachePack.Pack`（坏文件返回 `null`）
  - `CachePack.write(Path, Map<String, byte[]>)`
  - `CachePack.Pack(Map<String, byte[]> entries, long bytes)`
  - `CacheStore(Path root, int maxGenerations, long maxBytes)`
  - `CacheStore.load(String key) -> CachePack.Pack`（无/坏返回 `null`）
  - `CacheStore.save(String key, Map<String, byte[]>)`
- Dependencies: Task 1
- Touches: `src/agent/java/hypernova/agent/{ScriptCacheKey,KeyManifest,CachePack,CacheStore}.java`、`tests/agent/java/hypernova/agent/{ScriptCacheKeyTest,CachePackTest,CacheStoreTest}.java`

- [ ] **Step 1: 写失败测试**

`tests/agent/java/hypernova/agent/ScriptCacheKeyTest.java`:

```java
package hypernova.agent;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;

import static org.junit.jupiter.api.Assertions.*;

class ScriptCacheKeyTest {
    @TempDir Path tmp;

    @Test
    void keyIsStableAndChangesWithSourceAndModList() throws Exception {
        Path game = tmp.resolve("game");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("foo");
        Files.createDirectories(mod.resolve("src/a"));
        Files.createDirectories(game.resolve("starsector-core/data/scripts"));
        Files.writeString(mod.resolve("mod_info.json"), "{\"id\":\"foo\"}");
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[\"foo\"]}");
        Path src = mod.resolve("src/a/A.java");
        Files.writeString(src, "package a; public class A {}");
        RuntimeContext ctx = ctx(game, mods);

        String k1 = ScriptCacheKey.compute(ctx).id();
        String k2 = ScriptCacheKey.compute(ctx).id();
        assertEquals(k1, k2, "same inputs must produce the same key");

        Files.writeString(src, "package a; public class A { int x; }");
        Files.setLastModifiedTime(src,
                FileTime.fromMillis(System.currentTimeMillis() + 1000));
        String k3 = ScriptCacheKey.compute(ctx).id();
        assertNotEquals(k1, k3, "source change must change the key");

        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[]}");
        String k4 = ScriptCacheKey.compute(ctx).id();
        assertNotEquals(k3, k4, "mod list change must change the key");
    }

    @Test
    void keyIncludesModJar() throws Exception {
        Path game = tmp.resolve("game2");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("bar");
        Files.createDirectories(mod.resolve("jars"));
        Files.createDirectories(mod.resolve("src"));
        Files.writeString(mod.resolve("mod_info.json"), "{\"id\":\"bar\"}");
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[\"bar\"]}");
        Path jar = mod.resolve("jars/bar.jar");
        Files.write(jar, new byte[]{1, 2, 3});
        RuntimeContext ctx = ctx(game, mods);
        String k1 = ScriptCacheKey.compute(ctx).id();

        Files.write(jar, new byte[]{1, 2, 4});
        Files.setLastModifiedTime(jar,
                FileTime.fromMillis(System.currentTimeMillis() + 1000));
        assertNotEquals(k1, ScriptCacheKey.compute(ctx).id());
    }

    private RuntimeContext ctx(Path game, Path mods) {
        Path saves = tmp.resolve("saves-" + Math.abs(game.hashCode()));
        ScriptCacheConfig cfg = new ScriptCacheConfig(true, 1L << 20, 2, 3000, false);
        return new RuntimeContext(game, mods, saves, saves.resolve("cache"),
                saves.resolve("agent.log"), saves.resolve("telemetry.jsonl"), cfg);
    }
}
```

`tests/agent/java/hypernova/agent/CachePackTest.java`:

```java
package hypernova.agent;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class CachePackTest {
    @TempDir Path tmp;

    @Test
    void roundTrip() throws Exception {
        Map<String, byte[]> in = new LinkedHashMap<>();
        in.put("a.B", new byte[]{1, 2, 3});
        in.put("a.C$1", new byte[]{4});
        Path p = tmp.resolve("x/classes.pack");
        CachePack.write(p, in);
        CachePack.Pack out = CachePack.read(p);
        assertNotNull(out);
        assertEquals(2, out.entries().size());
        assertArrayEquals(new byte[]{1, 2, 3}, out.entries().get("a.B"));
        assertEquals(4, out.bytes());
    }

    @Test
    void corruptTrailingCrcReturnsNull() throws Exception {
        Path p = tmp.resolve("y/classes.pack");
        CachePack.write(p, Map.of("a.B", new byte[]{1, 2, 3}));
        byte[] bytes = Files.readAllBytes(p);
        bytes[bytes.length - 1] ^= 0x7F;
        Files.write(p, bytes);
        assertNull(CachePack.read(p));
    }

    @Test
    void truncatedReturnsNull() throws Exception {
        Path p = tmp.resolve("z/classes.pack");
        CachePack.write(p, Map.of("a.B", new byte[]{1, 2, 3}));
        byte[] bytes = Files.readAllBytes(p);
        Files.write(p, Arrays.copyOf(bytes, bytes.length - 4));
        assertNull(CachePack.read(p));
    }
}
```

`tests/agent/java/hypernova/agent/CacheStoreTest.java`:

```java
package hypernova.agent;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class CacheStoreTest {
    @TempDir Path tmp;

    @Test
    void saveLoadAndCleanupOlderGenerations() throws Exception {
        CacheStore store = new CacheStore(tmp, 2, 1L << 30);
        Map<String, byte[]> m1 = Map.of("a.B", new byte[]{1});
        Map<String, byte[]> m2 = Map.of("a.C", new byte[]{2});
        store.save("k1", m1);
        Thread.sleep(20);
        store.save("k2", m2);
        Thread.sleep(20);
        store.save("k3", m2);
        assertNotNull(store.load("k3"));
        assertFalse(Files.exists(tmp.resolve("k1")), "oldest generation must be deleted");
        assertTrue(Files.exists(tmp.resolve("k2")));
        assertTrue(Files.exists(tmp.resolve("k3")));
    }

    @Test
    void corruptPackLoadsNull() throws Exception {
        CacheStore store = new CacheStore(tmp, 2, 1L << 30);
        store.save("k", Map.of("a.B", new byte[]{1, 2, 3}));
        Path pack = tmp.resolve("k/classes.pack");
        byte[] bytes = Files.readAllBytes(pack);
        bytes[bytes.length - 1] ^= 1;
        Files.write(pack, bytes);
        assertNull(store.load("k"));
    }
}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash tools/java/run-agent-tests.sh ScriptCacheKeyTest`
Expected: 编译失败（`ScriptCacheKey` 不存在）。

- [ ] **Step 3: 实现**

`src/agent/java/hypernova/agent/ScriptCacheKey.java`:

```java
package hypernova.agent;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.stream.Stream;

public final class ScriptCacheKey {
    public record Result(String id, String canonical, int fileCount, long bytes,
                         long elapsedMillis) {
    }

    private ScriptCacheKey() {
    }

    public static Result compute(RuntimeContext ctx) {
        long t0 = System.nanoTime();
        List<Path> files = collectFiles(ctx);
        Path manifestFile = ctx.cacheRoot().resolve("key-manifest.json");
        KeyManifest manifest = KeyManifest.load(manifestFile);
        List<KeyManifest.Entry> entries = manifest.refresh(files);

        List<String> classpathOrder = classpathOrder(ctx);
        StringBuilder sb = new StringBuilder(1 << 20);
        sb.append("java=").append(System.getProperty("java.version", "")).append('\n');
        sb.append("classpath=").append(String.join(File.pathSeparator, classpathOrder)).append('\n');
        List<KeyManifest.Entry> sorted = new ArrayList<>(entries);
        sorted.sort(Comparator.comparing(KeyManifest.Entry::path));
        for (KeyManifest.Entry e : sorted) {
            sb.append(e.path()).append('|').append(e.size()).append('|')
                    .append(e.mtime()).append('|').append(e.sha256()).append('\n');
        }
        String canonical = sb.toString();
        String id = sha256(canonical.getBytes(StandardCharsets.UTF_8)).substring(0, 32);
        try {
            manifest.save(manifestFile);
        } catch (IOException e) {
            AgentLog.fail("key manifest save failed", e);
        }
        long bytes = entries.stream().mapToLong(KeyManifest.Entry::size).sum();
        return new Result(id, canonical, entries.size(), bytes,
                (System.nanoTime() - t0) / 1_000_000);
    }

    static List<Path> collectFiles(RuntimeContext ctx) {
        TreeSet<Path> files = new TreeSet<>();
        Path mods = ctx.modsRoot();
        Set<String> enabled = readEnabledIds(mods.resolve("enabled_mods.json"));
        Map<String, Path> folders = scanModFolders(mods);
        if (enabled == null) enabled = folders.keySet();
        for (String id : enabled) {
            Path folder = folders.get(id);
            if (folder == null) continue;
            addTree(folder.resolve("src"), files);
            addTree(folder.resolve("jars"), files);
            addTree(folder.resolve("data/scripts"), files);
            addFile(folder.resolve("mod_info.json"), files);
            try (Stream<Path> s = Files.list(folder)) {
                s.filter(p -> p.getFileName().toString().toLowerCase(Locale.ROOT)
                                .endsWith(".jar"))
                        .forEach(p -> addFile(p, files));
            } catch (IOException ignored) {
            }
        }
        addFile(mods.resolve("enabled_mods.json"), files);
        addTree(ctx.gameRoot().resolve("starsector-core/data/scripts"), files);
        addFile(ctx.gameRoot().resolve("starsector-core/fr.agent.jar"), files);
        addFile(ctx.gameRoot().resolve("starsector-core/fr.jar"), files);
        for (String cp : classpathOrder(ctx)) addFile(Path.of(cp), files);
        return new ArrayList<>(files);
    }

    private static List<String> classpathOrder(RuntimeContext ctx) {
        Path root = ctx.gameRoot().toAbsolutePath().normalize();
        List<String> out = new ArrayList<>();
        for (String cp : System.getProperty("java.class.path", "").split(File.pathSeparator)) {
            if (cp.isBlank()) continue;
            Path p = Path.of(cp).toAbsolutePath().normalize();
            if (Files.isRegularFile(p) && p.startsWith(root)
                    && !p.getFileName().toString().equals("hypernova.agent.jar")) {
                out.add(p.toString());
            }
        }
        return out;
    }

    private static void addTree(Path root, Set<Path> out) {
        if (!Files.isDirectory(root)) return;
        try (Stream<Path> s = Files.walk(root)) {
            s.filter(Files::isRegularFile)
                    .filter(p -> {
                        String n = p.getFileName().toString().toLowerCase(Locale.ROOT);
                        return n.endsWith(".java") || n.endsWith(".jar")
                                || n.equals("mod_info.json");
                    })
                    .forEach(p -> addFile(p, out));
        } catch (IOException e) {
            AgentLog.fail("walk failed: " + root, e);
        }
    }

    private static void addFile(Path p, Set<Path> out) {
        if (p != null && Files.isRegularFile(p)) out.add(p.toAbsolutePath().normalize());
    }

    private static Set<String> readEnabledIds(Path file) {
        if (!Files.isRegularFile(file)) return null;
        Set<String> ids = new TreeSet<>();
        try {
            JSONObject o = new JSONObject(Files.readString(file));
            JSONArray a = o.optJSONArray("enabledMods");
            if (a != null) {
                for (int i = 0; i < a.length(); i++) ids.add(a.getString(i));
            }
        } catch (Throwable t) {
            AgentLog.fail("enabled_mods parse failed: " + file, t);
            return null;
        }
        return ids;
    }

    private static Map<String, Path> scanModFolders(Path mods) {
        Map<String, Path> map = new TreeMap<>();
        if (!Files.isDirectory(mods)) return map;
        try (Stream<Path> s = Files.list(mods)) {
            s.filter(Files::isDirectory).forEach(dir -> {
                Path info = dir.resolve("mod_info.json");
                if (!Files.isRegularFile(info)) return;
                try {
                    JSONObject o = new JSONObject(Files.readString(info));
                    String id = o.optString("id", "");
                    if (!id.isBlank()) map.put(id, dir);
                } catch (Throwable ignored) {
                }
            });
        } catch (IOException e) {
            AgentLog.fail("mod scan failed", e);
        }
        return map;
    }

    private static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }
}
```

`src/agent/java/hypernova/agent/KeyManifest.java`:

```java
package hypernova.agent;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;

public final class KeyManifest {
    public record Entry(String path, long size, long mtime, String sha256) {
    }

    private final Map<String, Entry> byPath = new HashMap<>();

    public static KeyManifest load(Path file) {
        KeyManifest manifest = new KeyManifest();
        if (!Files.isRegularFile(file)) return manifest;
        try {
            JSONArray array = new JSONArray(Files.readString(file));
            for (int i = 0; i < array.length(); i++) {
                JSONObject o = array.getJSONObject(i);
                Entry e = new Entry(o.getString("path"), o.getLong("size"),
                        o.getLong("mtime"), o.getString("sha256"));
                manifest.byPath.put(e.path(), e);
            }
        } catch (Throwable t) {
            AgentLog.fail("key manifest load failed; rebuilding", t);
        }
        return manifest;
    }

    public List<Entry> refresh(List<Path> files) {
        List<Entry> out = new ArrayList<>(files.size());
        for (Path p : files) {
            try {
                String path = p.toString();
                long size = Files.size(p);
                long mtime = Files.getLastModifiedTime(p).toMillis();
                Entry prev = byPath.get(path);
                String hash = (prev != null && prev.size() == size && prev.mtime() == mtime)
                        ? prev.sha256() : sha256(p);
                out.add(new Entry(path, size, mtime, hash));
            } catch (IOException e) {
                AgentLog.fail("stat failed: " + p, e);
            }
        }
        byPath.clear();
        for (Entry e : out) byPath.put(e.path(), e);
        return out;
    }

    public void save(Path file) throws IOException {
        JSONArray array = new JSONArray();
        for (Entry e : byPath.values()) {
            JSONObject o = new JSONObject();
            o.put("path", e.path());
            o.put("size", e.size());
            o.put("mtime", e.mtime());
            o.put("sha256", e.sha256());
            array.put(o);
        }
        Files.createDirectories(file.getParent());
        Path tmp = file.resolveSibling(file.getFileName() + ".tmp");
        Files.writeString(tmp, array.toString(), StandardCharsets.UTF_8);
        Files.move(tmp, file, StandardCopyOption.REPLACE_EXISTING,
                StandardCopyOption.ATOMIC_MOVE);
    }

    private static String sha256(Path path) throws IOException {
        try (InputStream in = Files.newInputStream(path)) {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) > 0) md.update(buf, 0, n);
            return HexFormat.of().formatHex(md.digest());
        } catch (NoSuchAlgorithmException e) {
            throw new IOException(e);
        }
    }
}
```

`src/agent/java/hypernova/agent/CachePack.java`:

```java
package hypernova.agent;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.HashMap;
import java.util.Map;
import java.util.zip.CRC32;

public final class CachePack {
    public record Pack(Map<String, byte[]> entries, long bytes) {
    }

    static final int MAGIC = 0x484E5031; // "HNP1"
    static final int VERSION = 1;
    static final int MAX_NAME = 4096;
    static final int MAX_DATA = 50 * 1024 * 1024;
    static final int MAX_COUNT = 200_000;

    private CachePack() {
    }

    public static Pack read(Path file) {
        try (DataInputStream in = new DataInputStream(
                new BufferedInputStream(Files.newInputStream(file), 1 << 16))) {
            if (in.readInt() != MAGIC || in.readInt() != VERSION) return null;
            int count = in.readInt();
            if (count < 0 || count > MAX_COUNT) return null;
            Map<String, byte[]> map = new HashMap<>(Math.max(16, count * 2));
            CRC32 crc = new CRC32();
            long bytes = 0;
            for (int i = 0; i < count; i++) {
                int nameLen = in.readInt();
                if (nameLen < 1 || nameLen > MAX_NAME) return null;
                byte[] name = in.readNBytes(nameLen);
                if (name.length != nameLen) return null;
                int dataLen = in.readInt();
                if (dataLen < 0 || dataLen > MAX_DATA) return null;
                byte[] data = in.readNBytes(dataLen);
                if (data.length != dataLen) return null;
                crc.update(name);
                crc.update(data);
                map.put(new String(name, StandardCharsets.UTF_8), data);
                bytes += dataLen;
            }
            long expected = in.readLong();
            return expected == crc.getValue() ? new Pack(map, bytes) : null;
        } catch (Throwable t) {
            AgentLog.fail("cache pack read failed: " + file, t);
            return null;
        }
    }

    public static void write(Path file, Map<String, byte[]> entries) throws IOException {
        Files.createDirectories(file.getParent());
        Path tmp = file.resolveSibling(file.getFileName() + ".tmp");
        CRC32 crc = new CRC32();
        try (OutputStream fos = Files.newOutputStream(tmp);
             BufferedOutputStream bos = new BufferedOutputStream(fos, 1 << 16);
             DataOutputStream out = new DataOutputStream(bos)) {
            out.writeInt(MAGIC);
            out.writeInt(VERSION);
            out.writeInt(entries.size());
            for (Map.Entry<String, byte[]> e : entries.entrySet()) {
                byte[] name = e.getKey().getBytes(StandardCharsets.UTF_8);
                byte[] data = e.getValue();
                out.writeInt(name.length);
                out.write(name);
                out.writeInt(data.length);
                out.write(data);
                crc.update(name);
                crc.update(data);
            }
            out.flush();
            bos.flush();
            fos.write(ByteBuffer.allocate(8).putLong(crc.getValue()).array());
            fos.flush();
        }
        Files.move(tmp, file, StandardCopyOption.REPLACE_EXISTING,
                StandardCopyOption.ATOMIC_MOVE);
    }
}
```

`src/agent/java/hypernova/agent/CacheStore.java`:

```java
package hypernova.agent;

import java.io.IOException;
import java.nio.file.attribute.FileTime;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

public final class CacheStore {
    private final Path root;
    private final int maxGenerations;
    private final long maxBytes;

    public CacheStore(Path root, int maxGenerations, long maxBytes) {
        this.root = root;
        this.maxGenerations = Math.max(1, maxGenerations);
        this.maxBytes = Math.max(0, maxBytes);
    }

    public CachePack.Pack load(String key) {
        Path pack = root.resolve(key).resolve("classes.pack");
        if (!Files.isRegularFile(pack)) return null;
        CachePack.Pack p = CachePack.read(pack);
        if (p == null) {
            AgentLog.info("corrupt scripts cache ignored: " + pack);
            return null;
        }
        touch(key);
        return p;
    }

    public void save(String key, Map<String, byte[]> entries) throws IOException {
        Path dir = root.resolve(key);
        Files.createDirectories(dir);
        CachePack.write(dir.resolve("classes.pack"), entries);
        long bytes = entries.values().stream().mapToLong(a -> a.length).sum();
        String json = "{\"key\":\"" + key + "\",\"saved_at\":" + System.currentTimeMillis()
                + ",\"entries\":" + entries.size() + ",\"bytes\":" + bytes + "}\n";
        Files.writeString(dir.resolve("generation.json"), json);
        cleanup(key);
    }

    public List<String> generations() {
        List<String> out = new ArrayList<>();
        if (!Files.isDirectory(root)) return out;
        try (Stream<Path> s = Files.list(root)) {
            s.filter(Files::isDirectory).forEach(p -> out.add(p.getFileName().toString()));
        } catch (IOException e) {
            AgentLog.fail("cache list failed", e);
        }
        Collections.sort(out);
        return out;
    }

    private void touch(String key) {
        try {
            Path g = root.resolve(key).resolve("generation.json");
            if (Files.isRegularFile(g)) {
                Files.setLastModifiedTime(g, FileTime.fromMillis(System.currentTimeMillis()));
            }
        } catch (IOException ignored) {
        }
    }

    private void cleanup(String current) {
        try (Stream<Path> s = Files.list(root)) {
            List<Path> gens = s.filter(Files::isDirectory)
                    .filter(p -> !p.getFileName().toString().equals(current))
                    .sorted(Comparator.comparingLong(this::lastUsed).reversed())
                    .toList();
            int keep = maxGenerations - 1;
            for (int i = keep; i < gens.size(); i++) deleteTree(gens.get(i));
        } catch (IOException e) {
            AgentLog.fail("cache cleanup failed", e);
        }
        enforceSize(current);
    }

    private void enforceSize(String current) {
        if (maxBytes <= 0) return;
        try (Stream<Path> s = Files.list(root)) {
            List<Path> gens = s.filter(Files::isDirectory)
                    .filter(p -> !p.getFileName().toString().equals(current))
                    .sorted(Comparator.comparingLong(this::lastUsed))
                    .toList();
            long total = sizeOf(root);
            for (Path gen : gens) {
                if (total <= maxBytes) break;
                total -= sizeOf(gen);
                deleteTree(gen);
            }
        } catch (IOException e) {
            AgentLog.fail("cache size cleanup failed", e);
        }
    }

    private long lastUsed(Path dir) {
        try {
            return Files.getLastModifiedTime(dir.resolve("generation.json")).toMillis();
        } catch (IOException e) {
            return 0L;
        }
    }

    private static long sizeOf(Path dir) {
        try (Stream<Path> s = Files.walk(dir)) {
            return s.filter(Files::isRegularFile).mapToLong(p -> {
                try {
                    return Files.size(p);
                } catch (IOException e) {
                    return 0L;
                }
            }).sum();
        } catch (IOException e) {
            return 0L;
        }
    }

    private static void deleteTree(Path dir) {
        try (Stream<Path> s = Files.walk(dir)) {
            s.sorted(Comparator.reverseOrder()).forEach(p -> {
                try {
                    Files.deleteIfExists(p);
                } catch (IOException ignored) {
                }
            });
        } catch (IOException ignored) {
        }
    }
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `bash tools/java/run-agent-tests.sh ScriptCache`
Expected: `ScriptCacheKeyTest`、`CachePackTest`、`CacheStoreTest` 全部通过。

- [ ] **Step 5: Commit**

```bash
git add src/agent/java/hypernova/agent/ScriptCacheKey.java \
  src/agent/java/hypernova/agent/KeyManifest.java \
  src/agent/java/hypernova/agent/CachePack.java \
  src/agent/java/hypernova/agent/CacheStore.java \
  tests/agent/java/hypernova/agent
git commit -m "feat(m1d): add content-addressed key, pack format and generation store

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: Preload + 命中计数 + 落盘

**Files:**
- Modify: `src/agent/java/hypernova/agent/ScriptCacheHook.java`（整体替换 Task 1 版本）
- Create: `src/agent/java/hypernova/agent/CacheWriter.java`
- Test: `tests/agent/java/hypernova/agent/ScriptCacheHookPreloadTest.java`
- Test: `tests/agent/java/hypernova/agent/CacheWriterTest.java`
- Modify: `tests/agent/fixtures/com/genir/renderer/overrides/loading/MultiThreadedJaninoClassLoader.java`（加 `public Class<?> find(String)`）

**Interfaces:**
- Consumes: Task 1 的 `ScriptCacheTransformer`/`RuntimeContext`/`AgentTelemetry`；Task 2 的 `ScriptCacheKey`/`CachePack`/`CacheStore`。
- Produces:
  - `ScriptCacheHook.preload(Object)`：真实加载 pack 并 `putAll` 到 `bytecodeCache`
  - `ScriptCacheHook.onFindClass(Object, String)`：命中/未命中计数
  - `ScriptCacheHook.shutdown()`：flush + summary
  - `CacheWriter(RuntimeContext, String, Map<String,byte[]>, int preloadedCount, long stableMillis)`；`start()`；`flushNow()`；`stop()`
  - `ScriptCacheHook.missSample()`（package-private，诊断用）
- Dependencies: Task 1, Task 2
- Touches: `src/agent/java/hypernova/agent/{ScriptCacheHook,CacheWriter}.java`、`tests/agent/java/hypernova/agent/{ScriptCacheHookPreloadTest,CacheWriterTest}.java`、`tests/agent/fixtures/com/genir/renderer/overrides/loading/MultiThreadedJaninoClassLoader.java`

- [ ] **Step 1: 写失败测试**

`tests/agent/java/hypernova/agent/ScriptCacheHookPreloadTest.java`:

```java
package hypernova.agent;

import com.genir.renderer.overrides.loading.MultiThreadedJaninoClassLoader;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class ScriptCacheHookPreloadTest {
    @TempDir Path tmp;

    @AfterEach
    void reset() {
        ScriptCacheHook.resetForTest();
    }

    @Test
    void preloadPopulatesBytecodeCacheAndFindClassHits() throws Exception {
        Path game = tmp.resolve("game");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("foo");
        Files.createDirectories(mod.resolve("src"));
        Files.createDirectories(game.resolve("starsector-core/data/scripts"));
        Files.writeString(mod.resolve("mod_info.json"), "{\"id\":\"foo\"}");
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[\"foo\"]}");
        Path saves = tmp.resolve("saves");
        ScriptCacheConfig cfg = new ScriptCacheConfig(true, 1L << 30, 2, 3000, false);
        RuntimeContext ctx = new RuntimeContext(game, mods, saves, saves.resolve("cache"),
                saves.resolve("agent.log"), saves.resolve("telemetry.jsonl"), cfg);

        String key = ScriptCacheKey.compute(ctx).id();
        Map<String, byte[]> entries = Map.of("hypernova.cache.Generated", generatedClass());
        new CacheStore(ctx.cacheRoot(), 2, 1L << 30).save(key, entries);

        MultiThreadedJaninoClassLoader loader =
                new MultiThreadedJaninoClassLoader(getClass().getClassLoader());
        ScriptCacheHook.preload(loader, ctx);

        assertTrue(loader.bytecodeCache().containsKey("hypernova.cache.Generated"));
        Class<?> clazz = loader.find("hypernova.cache.Generated");
        assertEquals("hypernova.cache.Generated", clazz.getName());
        assertEquals(1, ScriptCacheHook.hits());
        assertEquals(0, ScriptCacheHook.misses());
    }

    @Test
    void coldPreloadCountsMissingAsMiss() throws Exception {
        Path game = tmp.resolve("game2");
        Path mods = game.resolve("mods");
        Files.createDirectories(game.resolve("starsector-core/data/scripts"));
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[]}");
        Path saves = tmp.resolve("saves2");
        ScriptCacheConfig cfg = new ScriptCacheConfig(true, 1L << 30, 2, 3000, false);
        RuntimeContext ctx = new RuntimeContext(game, mods, saves, saves.resolve("cache"),
                saves.resolve("agent.log"), saves.resolve("telemetry.jsonl"), cfg);

        MultiThreadedJaninoClassLoader loader =
                new MultiThreadedJaninoClassLoader(getClass().getClassLoader());
        ScriptCacheHook.preload(loader, ctx);
        assertTrue(loader.bytecodeCache().isEmpty());
        assertThrows(ClassNotFoundException.class, () -> loader.find("missing.Class"));
        assertEquals(1, ScriptCacheHook.misses());
    }

    private static byte[] generatedClass() {
        ClassWriter cw = new ClassWriter(0);
        cw.visit(Opcodes.V17, Opcodes.ACC_PUBLIC, "hypernova/cache/Generated", null,
                "java/lang/Object", null);
        MethodVisitor mv = cw.visitMethod(Opcodes.ACC_PUBLIC, "<init>", "()V", null, null);
        mv.visitCode();
        mv.visitVarInsn(Opcodes.ALOAD, 0);
        mv.visitMethodInsn(Opcodes.INVOKESPECIAL, "java/lang/Object", "<init>", "()V", false);
        mv.visitInsn(Opcodes.RETURN);
        mv.visitMaxs(1, 1);
        mv.visitEnd();
        cw.visitEnd();
        return cw.toByteArray();
    }
}
```

`tests/agent/java/hypernova/agent/CacheWriterTest.java`:

```java
package hypernova.agent;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import static org.junit.jupiter.api.Assertions.*;

class CacheWriterTest {
    @TempDir Path tmp;

    @Test
    void flushWritesNewEntries() throws Exception {
        Path saves = tmp.resolve("saves");
        ScriptCacheConfig cfg = new ScriptCacheConfig(true, 1L << 30, 2, 3000, false);
        RuntimeContext ctx = new RuntimeContext(tmp.resolve("game"), tmp.resolve("mods"),
                saves, saves.resolve("cache"), saves.resolve("agent.log"),
                saves.resolve("telemetry.jsonl"), cfg);
        Map<String, byte[]> map = new ConcurrentHashMap<>();
        map.put("a.B", new byte[]{1, 2, 3});
        CacheWriter writer = new CacheWriter(ctx, "testkey", map, 0, 0);
        writer.flushNow();
        CachePack.Pack p = new CacheStore(ctx.cacheRoot(), 2, 1L << 30).load("testkey");
        assertNotNull(p);
        assertArrayEquals(new byte[]{1, 2, 3}, p.entries().get("a.B"));
    }
}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash tools/java/run-agent-tests.sh ScriptCacheHookPreloadTest`
Expected: 编译失败（`ScriptCacheHook.preload(Object, RuntimeContext)` / `CacheWriter` 不存在，fixture 的 `find` 不存在）。

- [ ] **Step 3: 实现**

**先给 fixture 加 `find`**（`tests/agent/fixtures/.../MultiThreadedJaninoClassLoader.java` 末尾、`bytecodeCache()` 之后）：

```java
    public Class<?> find(String name) throws ClassNotFoundException {
        return findClass(name);
    }
```

`src/agent/java/hypernova/agent/ScriptCacheHook.java`（整体替换）：

```java
package hypernova.agent;

import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

public final class ScriptCacheHook {
    private static final AtomicInteger PRELOAD_CALLS = new AtomicInteger();
    private static final LongAdder FINDS = new LongAdder();
    private static final LongAdder HITS = new LongAdder();
    private static final LongAdder MISSES = new LongAdder();
    private static final AtomicLong FIRST = new AtomicLong(0);
    private static final AtomicLong LAST = new AtomicLong(0);
    private static final Set<Object> PRELOADED = ConcurrentHashMap.newKeySet();
    private static final List<String> MISS_SAMPLE =
            Collections.synchronizedList(new ArrayList<>());
    private static volatile RuntimeContext context;
    private static volatile Map<String, byte[]> currentMap;
    private static volatile String currentKey = "";
    private static volatile CacheWriter writer;

    private ScriptCacheHook() {
    }

    public static void preload(Object loader) {
        PRELOAD_CALLS.incrementAndGet();
        try {
            RuntimeContext ctx = context;
            if (ctx == null) {
                AgentLog.info("no runtime context; preload skipped");
                return;
            }
            preload(loader, ctx);
        } catch (Throwable t) {
            AgentLog.fail("preload failed", t);
        }
    }

    static void preload(Object loader, RuntimeContext ctx) {
        if (loader == null || ctx == null || !ctx.config().scriptsEnabled()) return;
        if (!PRELOADED.add(loader)) return;
        Map<String, byte[]> map = bytecodeCache(loader);
        if (map == null) {
            AgentLog.info("bytecodeCache field not found; scripts cache disabled");
            return;
        }
        currentMap = map;
        context = ctx;
        long t0 = System.nanoTime();
        String key = ScriptCacheKey.compute(ctx).id();
        currentKey = key;
        CacheStore store = new CacheStore(ctx.cacheRoot(), ctx.config().cacheGenerations(),
                ctx.config().cacheMaxBytes());
        CachePack.Pack pack = store.load(key);
        long ms = (System.nanoTime() - t0) / 1_000_000;
        if (pack != null) {
            map.putAll(pack.entries());
            AgentLog.info("scripts cache preloaded: key=" + key + ", entries="
                    + pack.entries().size() + ", bytes=" + pack.bytes() + ", in " + ms + " ms");
            ctx.telemetry().event("preload", key, pack.entries().size(), pack.bytes(), ms);
        } else {
            AgentLog.info("scripts cache cold: key=" + key + ", preloaded=0, in " + ms + " ms");
            ctx.telemetry().event("preload-miss", key, 0, 0, ms);
        }
        writer = new CacheWriter(ctx, key, map, map.size(), 5_000);
        writer.start();
    }

    public static void onFindClass(Object loader, String name) {
        long now = System.nanoTime();
        FIRST.compareAndSet(0, now);
        LAST.set(now);
        FINDS.increment();
        Map<String, byte[]> map = currentMap;
        if (map != null && map.containsKey(name)) {
            HITS.increment();
        } else {
            MISSES.increment();
            if (MISS_SAMPLE.size() < 50) MISS_SAMPLE.add(name);
        }
    }

    public static void shutdown() {
        CacheWriter w = writer;
        if (w != null) w.flushNow();
        RuntimeContext ctx = context;
        if (ctx != null) {
            ctx.telemetry().summary(currentKey, HITS.sum(), MISSES.sum(), FINDS.sum(),
                    spanMillis(), currentMap == null ? 0 : currentMap.size());
            ctx.telemetry().close();
        }
    }

    public static void summaryTick() {
        RuntimeContext ctx = context;
        if (ctx == null) return;
        ctx.telemetry().summary(currentKey, HITS.sum(), MISSES.sum(), FINDS.sum(),
                spanMillis(), currentMap == null ? 0 : currentMap.size());
    }

    private static Map<String, byte[]> bytecodeCache(Object loader) {
        try {
            Field f = loader.getClass().getDeclaredField("bytecodeCache");
            f.setAccessible(true);
            Object value = f.get(loader);
            if (value instanceof Map<?, ?> m) {
                @SuppressWarnings("unchecked")
                Map<String, byte[]> typed = (Map<String, byte[]>) m;
                return typed;
            }
        } catch (Throwable t) {
            AgentLog.fail("cannot access bytecodeCache", t);
        }
        return null;
    }

    static void setContext(RuntimeContext ctx) { context = ctx; }
    static long preloadCalls() { return PRELOAD_CALLS.get(); }
    static long findCalls() { return FINDS.sum(); }
    static long hits() { return HITS.sum(); }
    static long misses() { return MISSES.sum(); }
    static String currentKey() { return currentKey; }
    static List<String> missSample() { return new ArrayList<>(MISS_SAMPLE); }

    static long spanMillis() {
        long first = FIRST.get();
        long last = LAST.get();
        return first == 0 || last < first ? 0 : (last - first) / 1_000_000;
    }

    static void resetForTest() {
        PRELOAD_CALLS.set(0);
        FINDS.reset();
        HITS.reset();
        MISSES.reset();
        FIRST.set(0);
        LAST.set(0);
        PRELOADED.clear();
        MISS_SAMPLE.clear();
        context = null;
        currentMap = null;
        currentKey = "";
        writer = null;
    }
}
```

`src/agent/java/hypernova/agent/CacheWriter.java`:

```java
package hypernova.agent;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

public final class CacheWriter {
    private final RuntimeContext ctx;
    private final String key;
    private final Map<String, byte[]> map;
    private final long stableMillis;
    private final AtomicBoolean started = new AtomicBoolean();
    private volatile int lastWrittenSize;
    private volatile boolean stopped;

    public CacheWriter(RuntimeContext ctx, String key, Map<String, byte[]> map,
                       int preloadedCount, long stableMillis) {
        this.ctx = ctx;
        this.key = key;
        this.map = map;
        this.lastWrittenSize = preloadedCount;
        this.stableMillis = stableMillis;
    }

    public void start() {
        if (!started.compareAndSet(false, true)) return;
        Thread t = new Thread(this::run, "Hypernova-ScriptCache-Writer");
        t.setDaemon(true);
        t.start();
    }

    private void run() {
        int lastSize = map.size();
        long changedAt = System.currentTimeMillis();
        while (!stopped) {
            try {
                Thread.sleep(500);
            } catch (InterruptedException e) {
                return;
            }
            int size = map.size();
            if (size != lastSize) {
                lastSize = size;
                changedAt = System.currentTimeMillis();
                continue;
            }
            if (System.currentTimeMillis() - changedAt >= stableMillis) {
                if (size > lastWrittenSize) flushNow();
                return;
            }
        }
    }

    public synchronized void flushNow() {
        if (map.size() == lastWrittenSize) return;
        Map<String, byte[]> snapshot = new HashMap<>(map);
        long t0 = System.nanoTime();
        try {
            new CacheStore(ctx.cacheRoot(), ctx.config().cacheGenerations(),
                    ctx.config().cacheMaxBytes()).save(key, snapshot);
            lastWrittenSize = snapshot.size();
            long ms = (System.nanoTime() - t0) / 1_000_000;
            long bytes = snapshot.values().stream().mapToLong(a -> a.length).sum();
            AgentLog.info("scripts cache written: key=" + key + ", entries="
                    + snapshot.size() + ", bytes=" + bytes + ", in " + ms + " ms");
            ctx.telemetry().event("write", key, snapshot.size(), bytes, ms);
        } catch (Throwable t) {
            AgentLog.fail("scripts cache write failed", t);
            ctx.telemetry().event("write-error", key, 0, 0, 0);
        }
    }

    public void stop() {
        stopped = true;
    }
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `bash tools/java/run-agent-tests.sh ScriptCache`
Expected: Task 1/2/3 的测试全部通过（`ScriptCacheTransformerTest`、`ScriptCacheKeyTest`、`CachePackTest`、`CacheStoreTest`、`ScriptCacheHookPreloadTest`、`CacheWriterTest`）。

- [ ] **Step 5: Commit**

```bash
git add src/agent/java/hypernova/agent/ScriptCacheHook.java \
  src/agent/java/hypernova/agent/CacheWriter.java \
  tests/agent/java/hypernova/agent tests/agent/fixtures
git commit -m "feat(m1d): preload FR bytecode cache, count real hits and persist warm cache

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: 配置、安装/卸载与打包

**Files:**
- Modify: `data/config/hypernova/hypernova.json`
- Create: `tools/install_agent.py`
- Create: `tests/tools/test_install_agent.py`
- Modify: `tools/java/build-mod.sh`（把 agent jar 放进 mod 包）

**Interfaces:**
- Consumes: Task 1 的 `ScriptCacheConfig`（读 `scripts` 段）；`build/agent/hypernova.agent.jar`。
- Produces:
  - `install_agent.AGENT_LINE = "-javaagent:../mods/hypernova_infinite_engine/jars/hypernova.agent.jar"`
  - `install_agent.patch_lines(list[str]) -> list[str]`
  - `install_agent.unpatch_lines(list[str]) -> list[str]`
  - CLI：`python tools/install_agent.py --game <root> --env base|260mods --action install|uninstall [--dry-run] [--jar build/agent/hypernova.agent.jar]`
- Dependencies: Task 1（agent jar 产物）
- Touches: `data/config/hypernova/hypernova.json`、`tools/install_agent.py`、`tests/tools/test_install_agent.py`、`tools/java/build-mod.sh`

- [ ] **Step 1: 写失败测试**

`tests/tools/test_install_agent.py`:

```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import install_agent as ia

FR = "-javaagent:fr.agent.jar\n"


def test_patch_inserts_after_fr_and_is_idempotent():
    lines = ["-Xmx10g\n", FR, "-classpath\n"]
    out = ia.patch_lines(lines)
    assert out[2] == ia.AGENT_LINE + "\n"
    assert out[0] == "-Xmx10g\n" and out[1] == FR and out[3] == "-classpath\n"
    assert ia.patch_lines(out) == out


def test_patch_without_fr_fails():
    with pytest.raises(SystemExit):
        ia.patch_lines(["-Xmx10g\n", "-classpath\n"])


def test_unpatch_removes_only_agent():
    lines = ["-Xmx10g\n", FR, ia.AGENT_LINE + "\n", "-classpath\n"]
    assert ia.unpatch_lines(lines) == ["-Xmx10g\n", FR, "-classpath\n"]


def test_toggle_is_reversible():
    lines = ["-Xmx10g\n", FR, "-classpath\n"]
    assert ia.unpatch_lines(ia.patch_lines(lines)) == lines
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -I -m pytest tests/tools/test_install_agent.py -v`
Expected: `ModuleNotFoundError: No module named 'install_agent'`（或导入失败）。

- [ ] **Step 3: 实现安装器与配置**

`tools/install_agent.py`:

```python
#!/usr/bin/env python3
"""Install/uninstall the optional Hypernova scripts-cache agent.

The agent line is inserted immediately after the Fast Rendering agent line, so
the transformer chain order is FR -> scripts. Writes LF line endings (argfiles
must be LF) and is idempotent. A backup is kept as *.bak-hypernova.
"""
import argparse
import shutil
import sys
from pathlib import Path

AGENT_LINE = "-javaagent:../mods/hypernova_infinite_engine/jars/hypernova.agent.jar"
FR_LINE = "-javaagent:fr.agent.jar"


def launch_file(game: Path, env: str) -> Path:
    return (game / "starsector-core" / "fr.vmparams"
            if env == "base" else game / "Miko_Lite.txt")


def patch_lines(lines: list[str]) -> list[str]:
    if any(line.strip() == AGENT_LINE for line in lines):
        return lines
    out: list[str] = []
    inserted = False
    for line in lines:
        out.append(line)
        if not inserted and line.strip() == FR_LINE:
            out.append(AGENT_LINE + "\n")
            inserted = True
    if not inserted:
        raise SystemExit(f"FR agent line not found; expected: {FR_LINE}")
    return out


def unpatch_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if line.strip() != AGENT_LINE]


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def write_lf(path: Path, lines: list[str]) -> None:
    text = "".join(line.replace("\r\n", "\n").replace("\r", "\n") for line in lines)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", required=True)
    parser.add_argument("--env", choices=["base", "260mods"], required=True)
    parser.add_argument("--action", choices=["install", "uninstall"], default="install")
    parser.add_argument("--jar", default="build/agent/hypernova.agent.jar")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    game = Path(args.game)
    launch = launch_file(game, args.env)
    if not launch.is_file():
        print(f"launch file not found: {launch}", file=sys.stderr)
        return 2

    lines = read_lines(launch)
    new = patch_lines(lines) if args.action == "install" else unpatch_lines(lines)
    if new == lines:
        print(f"no change: {launch}")
        return 0
    if args.dry_run:
        print("".join(new), end="")
        return 0

    if args.action == "install":
        jar = Path(args.jar)
        if not jar.is_file():
            print(f"agent jar not found: {jar}", file=sys.stderr)
            return 2
        dst = game / "mods/hypernova_infinite_engine/jars/hypernova.agent.jar"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(jar, dst)
        print(f"installed: {dst}")

    backup = launch.with_name(launch.name + ".bak-hypernova")
    if not backup.exists():
        shutil.copy2(launch, backup)
    write_lf(launch, new)
    print(f"{args.action}: {launch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`data/config/hypernova/hypernova.json`（完整替换；M1 的 `HypernovaConfig.fromJson` 会忽略 `scripts`）：

```json
{
  "enabled": true,
  "eviction": false,
  "frame_budget_micros": 2000,
  "telemetry_buffer_lines": 4096,
  "heartbeat_frames": 3000,
  "startup_probe_paths": 0,
  "scripts": {
    "enabled": true,
    "cache_max_bytes": 2147483648,
    "cache_generations": 2,
    "preload_max_millis": 3000
  }
}
```

`tools/java/build-mod.sh`（在 `cp "$ROOT_W/mod_info.json" "$MODDIR/mod_info.json"` 之后、zip 生成之前插入）：

```bash
# 可选 agent：构建过就放进 mod 包；是否启用由 install_agent.py 决定。
if [ -f "$ROOT_W/build/agent/hypernova.agent.jar" ]; then
  cp "$ROOT_W/build/agent/hypernova.agent.jar" "$MODDIR/jars/hypernova.agent.jar"
fi
```

并在 zip 断言段追加一条：

```bash
if [ -f "$MODDIR/jars/hypernova.agent.jar" ]; then
  (cd "$OUT" && jar --list --file hypernova-0.1.0.zip) \
    | grep -qx 'jars/hypernova.agent.jar' \
    || { echo "FATAL: zip 缺少 jars/hypernova.agent.jar" >&2; exit 1; }
fi
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -I -m pytest tests/tools/test_install_agent.py -v`
Expected: `4 passed`。

- [ ] **Step 5: 用临时文件做一次安装/卸载演练（不碰真游戏）**

```bash
TMP=$(mktemp -d)
mkdir -p "$TMP/starsector-core" "$TMP/mods/hypernova_infinite_engine/jars"
printf '%s\n' '-Xmx10g' '-javaagent:fr.agent.jar' '-classpath' > "$TMP/starsector-core/fr.vmparams"
printf '' > "$TMP/mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json" 2>/dev/null || true
mkdir -p "$TMP/mods/hypernova_infinite_engine/data/config/hypernova"
cp build/agent/hypernova.agent.jar "$TMP/agent.jar"
python -I tools/install_agent.py --game "$TMP" --env base --jar "$TMP/agent.jar"
grep -n 'javaagent' "$TMP/starsector-core/fr.vmparams"
python -I tools/install_agent.py --game "$TMP" --env base --action uninstall
grep -n 'javaagent' "$TMP/starsector-core/fr.vmparams"
rm -rf "$TMP"
```

Expected: 安装后两行 agent，FR 在前、hypernova 在后；卸载后只剩 FR。

- [ ] **Step 6: Commit**

```bash
git add data/config/hypernova/hypernova.json tools/install_agent.py \
  tests/tools/test_install_agent.py tools/java/build-mod.sh
git commit -m "feat(m1d): add scripts config block and idempotent agent installer

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: CacheTool + 遥测解析

**Files:**
- Create: `src/agent/java/hypernova/agent/tools/CacheTool.java`
- Create: `tools/java/build-agent-tools.sh`
- Create: `tools/java/cache-tool.sh`
- Create: `tools/java/parse_script_telemetry.py`
- Test: `tests/tools/test_parse_script_telemetry.py`

**Interfaces:**
- Consumes: Task 2 的 `ScriptCacheKey`/`CachePack`/`CacheStore`；Task 1 的 `RuntimeContext`。
- Produces:
  - `CacheTool` 子命令：`key`、`inspect [key]`、`seed --class C --key K --source-root DIR --out-root DIR`
  - `tools/java/cache-tool.sh key|inspect|seed ...`（Base 环境；必须从 `starsector-core` 的等价 classpath 运行，保证 key 与 agent 一致）
  - `parse_script_telemetry.summaries(Path) -> list[dict]`
- Dependencies: Task 1, Task 2
- Touches: `src/agent/java/hypernova/agent/tools/CacheTool.java`、`tools/java/{build-agent-tools,cache-tool}.sh`、`tools/java/parse_script_telemetry.py`、`tests/tools/test_parse_script_telemetry.py`

- [ ] **Step 1: 写失败测试**

`tests/tools/test_parse_script_telemetry.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/java"))
import parse_script_telemetry as p


def test_no_summary_returns_empty(tmp_path):
    f = tmp_path / "t.jsonl"
    f.write_text('{"kind":"preload","entries":1}\n', encoding="utf-8")
    assert p.summaries(f) == []


def test_last_summary_wins(tmp_path):
    f = tmp_path / "t.jsonl"
    f.write_text('{"kind":"summary","hits":1}\n'
                 '{"kind":"summary","hits":2}\n', encoding="utf-8")
    assert p.summaries(f)[-1]["hits"] == 2


def test_malformed_lines_are_skipped(tmp_path):
    f = tmp_path / "t.jsonl"
    f.write_text('not json\n{"kind":"summary","hits":3}\n', encoding="utf-8")
    assert p.summaries(f)[-1]["hits"] == 3
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -I -m pytest tests/tools/test_parse_script_telemetry.py -v`
Expected: `ModuleNotFoundError`（`parse_script_telemetry` 不存在）。

- [ ] **Step 3: 实现**

`src/agent/java/hypernova/agent/tools/CacheTool.java`:

```java
package hypernova.agent.tools;

import hypernova.agent.CachePack;
import hypernova.agent.CacheStore;
import hypernova.agent.RuntimeContext;
import hypernova.agent.ScriptCacheKey;
import org.codehaus.janino.JavaSourceClassLoader;
import org.codehaus.janino.util.resource.DirectoryResourceFinder;

import java.io.File;
import java.nio.file.Path;
import java.util.Map;

public final class CacheTool {
    private CacheTool() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            usage();
            return;
        }
        switch (args[0]) {
            case "key" -> key();
            case "inspect" -> inspect(args);
            case "seed" -> seed(args);
            default -> usage();
        }
    }

    private static void key() {
        RuntimeContext ctx = RuntimeContext.fromEnvironment();
        ScriptCacheKey.Result r = ScriptCacheKey.compute(ctx);
        System.out.println(r.id());
        System.out.println("files=" + r.fileCount() + " bytes=" + r.bytes()
                + " elapsed_ms=" + r.elapsedMillis());
        System.out.println("cache_root=" + ctx.cacheRoot());
    }

    private static void inspect(String[] args) {
        RuntimeContext ctx = RuntimeContext.fromEnvironment();
        String key = args.length > 1 ? args[1] : ScriptCacheKey.compute(ctx).id();
        CachePack.Pack p = new CacheStore(ctx.cacheRoot(), ctx.config().cacheGenerations(),
                ctx.config().cacheMaxBytes()).load(key);
        if (p == null) {
            System.out.println("no pack for key=" + key);
            return;
        }
        System.out.println("key=" + key + " entries=" + p.entries().size()
                + " bytes=" + p.bytes());
        p.entries().keySet().stream().sorted().limit(20)
                .forEach(k -> System.out.println("  " + k));
    }

    private static void seed(String[] args) throws Exception {
        String className = null, key = null, sourceRoot = null, outRoot = null;
        for (int i = 1; i < args.length; i += 2) {
            if (i + 1 >= args.length) throw new IllegalArgumentException("missing value for " + args[i]);
            switch (args[i]) {
                case "--class" -> className = args[i + 1];
                case "--key" -> key = args[i + 1];
                case "--source-root" -> sourceRoot = args[i + 1];
                case "--out-root" -> outRoot = args[i + 1];
                default -> throw new IllegalArgumentException("unknown: " + args[i]);
            }
        }
        if (className == null || key == null || sourceRoot == null || outRoot == null) {
            throw new IllegalArgumentException(
                    "seed needs --class --key --source-root --out-root");
        }
        Exposed loader = new Exposed(ClassLoader.getSystemClassLoader(), new File(sourceRoot));
        Map<String, byte[]> map = loader.generate(className);
        if (map == null || map.isEmpty()) {
            throw new IllegalStateException("no bytecode generated for " + className);
        }
        new CacheStore(Path.of(outRoot), 2, 1L << 30).save(key, map);
        System.out.println("seeded " + map.size() + " classes into "
                + Path.of(outRoot, key) + " (key=" + key + ")");
    }

    private static void usage() {
        System.err.println("usage: CacheTool key | inspect [key] | "
                + "seed --class C --key K --source-root DIR --out-root DIR");
        System.exit(2);
    }

    static final class Exposed extends JavaSourceClassLoader {
        Exposed(ClassLoader parent, File root) {
            super(parent, new DirectoryResourceFinder(root), "UTF-8");
            setDebuggingInfo(true, true, true);
        }

        Map<String, byte[]> generate(String name) throws ClassNotFoundException {
            return generateBytecodes(name);
        }
    }
}
```

`tools/java/build-agent-tools.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
ROOT_W="$(winpath "$ROOT")"
CORE="$ROOT_W/Starsector-098-Base/starsector-core"
OUT="$ROOT_W/build/agent/tools-classes"
bash "$ROOT_W/tools/java/build-agent.sh"
rm -rf "$OUT"
mkdir -p "$OUT"
javac --release 17 -encoding UTF-8 \
  -cp "$ROOT_W/build/agent/classes;$CORE/json.jar;$CORE/janino.jar;$CORE/commons-compiler.jar;$CORE/commons-compiler-jdk.jar" \
  -d "$OUT" $(find "$ROOT_W/src/agent/java" -path '*tools*' -name '*.java')
echo "OK: $OUT"
```

`tools/java/cache-tool.sh`（Base only；classpath 顺序必须与 `fr.vmparams` 一致，保证 key 与 agent 相同）:

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
ROOT_W="$(winpath "$ROOT")"
CORE="$ROOT_W/Starsector-098-Base/starsector-core"
cd "$CORE"
CP="$CORE/fr.jar;$CORE/janino.jar;$CORE/commons-compiler.jar;$CORE/commons-compiler-jdk.jar;$CORE/starfarer.api.jar;$CORE/starfarer_obf.jar;$CORE/jogg-0.0.7.jar;$CORE/jorbis-0.0.15.jar;$CORE/json.jar;$CORE/lwjgl.jar;$CORE/jinput.jar;$CORE/log4j-1.2.9.jar;$CORE/lwjgl_util.jar;$CORE/fs.sound_obf.jar;$CORE/fs.common_obf.jar;$CORE/xstream-1.4.10.jar;$CORE/txw2-3.0.2.jar;$CORE/jaxb-api-2.4.0-b180830.0359.jar;$CORE/webp-imageio-0.1.6.jar;$ROOT_W/build/agent/classes;$ROOT_W/build/agent/tools-classes"
JAVA="$ROOT_W/Starsector-098-Base/jre/bin/java.exe"
if [ ! -x "$JAVA" ]; then JAVA=java; fi
"$JAVA" -cp "$CP" \
  -Dcom.fs.starfarer.settings.paths.mods=../mods \
  -Dcom.fs.starfarer.settings.paths.saves=../saves \
  hypernova.agent.tools.CacheTool "$@"
```

`tools/java/parse_script_telemetry.py`:

```python
#!/usr/bin/env python3
"""Summarize Hypernova scripts-cache JSONL telemetry."""
import json
import sys
from pathlib import Path


def summaries(path: Path) -> list[dict]:
    out = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("kind") == "summary":
                out.append(event)
    return out


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: parse_script_telemetry.py <jsonl>", file=sys.stderr)
        return 2
    found = summaries(Path(sys.argv[1]))
    if not found:
        print("no summary event", file=sys.stderr)
        return 1
    print(json.dumps(found[-1], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -I -m pytest tests/tools/test_parse_script_telemetry.py -v`
Expected: `3 passed`。

Run: `bash tools/java/build-agent-tools.sh`
Expected: `OK: .../build/agent/tools-classes`。

Run（Base，先不启动游戏）：`bash tools/java/cache-tool.sh key`
Expected: 打印 32 hex key + `files=... elapsed_ms=...`；与 Task 1 的 agent 日志 `scripts cache cold: key=...` 相同（同一环境、同一文件集）。

- [ ] **Step 5: Commit**

```bash
git add src/agent/java/hypernova/agent/tools/CacheTool.java \
  tools/java/build-agent-tools.sh tools/java/cache-tool.sh \
  tools/java/parse_script_telemetry.py \
  tests/tools/test_parse_script_telemetry.py
git commit -m "feat(m1d): add cache key/seed/inspect tool and telemetry parser

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: 真实冒烟（S3 → S4 → S5）+ 文档

**Files:**
- Create: `docs/m1d/acceptance-runbook.md`
- Create: `docs/m1d/` 冒烟输出（日志/摘要，按实际运行落盘）
- Modify: `调研-Java脚本预编译缓存.md`（§1 加“Compiling script 是队列日志，不是编译数”的说明）
- Modify: `技术笔记-纹理按需加载.md`（F-12 / §7 M-1d 同一说明）
- Test: 真实进程（Base、260mods），无 JUnit

**Interfaces:**
- Consumes: Task 1–5 的全部产物。
- Produces: S3/S4/S5 证据、REQ-S-01..09 的通过/失败记录、最终报告。
- Dependencies: Task 1, Task 2, Task 3, Task 4, Task 5
- Touches: `docs/m1d/**`、两份 spec 文档

> **Ruling（计划的主动收缩）**：规格的 S4 写的是“单内容 mod（CRSIDtest 1,196 目标）”。为不破坏 260mods 的 `enabled_mods.json`，本计划把 **Base（11 mod，含 shaderLib/BoxUtil）作为 S4 中间档**，260mods 全量作为 S5。若 S4 的 `find_calls` 与 S5 的命中率差距异常，再单独做 CRSIDtest-only profile。此收缩记入 ledger，执行时若用户不同意则按规格原文执行。

- [ ] **Step 1: 文档更正（先做，避免冒烟用错口径）**

在 `调研-Java脚本预编译缓存.md` §1 的表格后加：

```markdown
> **口径更正（2026-10-29）**：`Compiling script [X]` 是 FR `ScriptStore.loadScript`
> 在 `loadClass` **之前**打的队列日志，不是 Janino 编译数。类若在 mod jar 里被
> 父 loader 找到，也会打这一行。真实编译人口 = agent 在 `findClass` 入口计到的
> `find_calls`（miss 数），由 Task 1 的遥测给出。引用“15,070 个编译目标”时必须
> 注明这是队列数，不是编译数。
```

在 `技术笔记-纹理按需加载.md` F-12 的“15,070 个唯一 `Compiling script` 目标”后加同一句的缩写，并在 §7 M-1d 出口注明“命中率分母是 `findClass` 调用数，不是日志行数”。

- [ ] **Step 2: S3（Base 单类命中）**

```bash
# 构建三件套
bash tools/java/build-agent.sh
bash tools/java/build-agent-tools.sh
bash tools/java/build-mod.sh

# 安装 manifest + agent
bash tools/java/install-manifest.sh Starsector-098-Base
python -I tools/install_agent.py --game Starsector-098-Base --env base --action install

# 取 key（classpath 顺序与 fr.vmparams 一致）
KEY=$(bash tools/java/cache-tool.sh key | head -1)
echo "KEY=$KEY"

# 只 seed 一个真实源码类（core data/scripts，确定会编译）
bash tools/java/cache-tool.sh seed \
  --class data.scripts.plugins.LevelupPluginImpl \
  --key "$KEY" \
  --source-root . \
  --out-root ../saves/hypernova/scripts-cache
```

启动 `Starsector-098-Base/启动-高性能.bat`，人工点「开始游戏」，进主菜单后等 40 s，然后正常退出（让 shutdown hook 落盘）。检查：

```bash
python -I tools/java/parse_script_telemetry.py \
  Starsector-098-Base/saves/hypernova/scripts-telemetry.jsonl
```

**S3 通过判据**：`preload.entries >= 1`；`summary.hits >= 1`；`summary.find_calls > 0`；游戏到主菜单无崩溃。因为缓存里只有 seed 的 1 个类，任何 hit 都只能来自它。

- [ ] **Step 3: S4（Base 11 mod 全量冷/热）**

先删缓存代，保留 agent：

```bash
rm -rf Starsector-098-Base/saves/hypernova/scripts-cache
```

启动 Base → 主菜单 → 等 40 s → 正常退出。检查：

- `preload-miss`（冷）；
- `summary.find_calls` = 真实编译人口（记录，与 Task 1 的数字对比）；
- `write` 事件（落盘条目数/字节）。

再启动两次（热），每次等 40 s 后退出，记录 `preload.entries`、`summary.hits/misses`、`span_millis`。**S4 通过判据**：热跑 `hits / find_calls >= 0.95`（以最后一次热跑为准；第一次热跑允许补齐冷跑漏掉的条目）；冷跑不崩；游戏到主菜单。

- [ ] **Step 4: S5（260mods 全量，出口证据）**

```bash
mkdir -p Starsector-098-260mods/mods/hypernova_infinite_engine/data/config/hypernova
cp data/config/hypernova/hypernova.json \
  Starsector-098-260mods/mods/hypernova_infinite_engine/data/config/hypernova/
python -I tools/install_agent.py --game Starsector-098-260mods --env 260mods --action install
```

按 M-1 的测量纪律（附录 A：人工点一次「开始游戏」；先热缓存 DDS；启动三次取中位数）：

1. 删 `Starsector-098-260mods/saves/hypernova/scripts-cache`；
2. 冷跑一次到主菜单，记录冷耗时与 `preload-miss`/`write`；正常退出；
3. 热跑三次到主菜单，记录 `t_main_menu`（`tools/m1_measure.py` 或 `CodexTextEntryLoader` 锚点）与 telemetry 的 `summary`；
4. 计算三次中位数，与基线 **86.5 s** 比较。

**S5 通过判据**（REQ-S-01/02/03/08）：
- 热跑命中率 ≥ 95%；
- 热跑 `preload.millis <= 3000`（超过则记 Important；下一轮把 key/读 pack 移到后台预读，不在本计划内顺手改）；
- 三次中位数 ≤ **66 s**（目标 62 s；相对 86.5 s 下降 ≥ 20.5 s；最低可接受 ≥ 15 s = 71.5 s，但低于 66 s 才算达标）；
- 冷跑不慢于基线 +5 s；
- 游戏到主菜单、进入一场战斗、打开 codex 各一次不崩。

若 S5 不达标，附 `find_calls`、`span_millis`、命中率与日志，**不要**开始 M-1b/M3 的改动，先回报 controller 重新裁决。

- [ ] **Step 5: 回退矩阵**

| 场景 | 操作 | 期望 |
|---|---|---|
| 禁用开关 | `hypernova.json` 的 `scripts.enabled=false`，启动 Base | 无 `preload` 事件；无新缓存写入；游戏正常 |
| 坏缓存 | 把 `classes.pack` 截断 4 字节，启动 Base | 日志 `corrupt scripts cache ignored`；走 Janino；游戏到主菜单 |
| 无 FR | 用 `启动-高性能-无FR.bat`（不加载 agent）启动 Base | 游戏正常；无 agent 日志新增 |
| 卸载 | `python -I tools/install_agent.py --game <root> --env <env> --action uninstall` | `grep javaagent` 只剩 FR；游戏正常 |

- [ ] **Step 6: 写 acceptance-runbook 与最终报告**

`docs/m1d/acceptance-runbook.md` 记录：命令、环境、日期、每次运行的 `t_main_menu`、`find_calls`、`hits/misses`、`preload.entries`、`span_millis`、冷/热区分、失败回退。最终报告附在 SDD ledger 的 Task 6 条目。

- [ ] **Step 7: Commit**

```bash
git add docs/m1d 调研-Java脚本预编译缓存.md 技术笔记-纹理按需加载.md
git commit -m "docs(m1d): record acceptance runbook and correct compile-count metric

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Self-Review

### 1. Spec coverage

| 规格条目 | 覆盖任务 |
|---|---|
| REQ-S-01 命中率 ≥95% | Task 3（计数）/ Task 6（S4/S5） |
| REQ-S-02 首屏下降 ≥15 s | Task 6（S5） |
| REQ-S-03 冷跑不慢于 +5 s | Task 6（S4/S5） |
| REQ-S-04 坏缓存/版本/无 FR/探针失败回退 | Task 2（坏 pack）/ Task 3（preload 失败）/ Task 6（矩阵） |
| REQ-S-05 `scripts.enabled=false` no-op | Task 1（配置）/ Task 4（配置块）/ Task 6（矩阵） |
| REQ-S-06 键覆盖全部输入 | Task 2（key 测试） |
| REQ-S-07 类由原 loader 定义 | Task 3（preload 只 putAll）/ Task 6（S3） |
| REQ-S-08 缓存 ≤2 GB、预读 ≤3 s | Task 2（LRU/大小）/ Task 3（同步 preload、日志 ms）/ Task 6（实测） |
| REQ-S-09 hit/miss/compile/fallback/首屏 JSONL | Task 1（summary）/ Task 3（preload/write）/ Task 5（解析） |
| ADR-02 `scripts` 不改 `textures` | Global Constraints / Touches |
| S3/S4/S5 门禁 | Task 1（人口测量）/ Task 6（三级冒烟） |
| 实际编译人口 ≠ 日志行数 | Task 1 Step 5 / Task 6 Step 1 文档更正 |

### 2. Placeholder scan

- 无 `TBD`/`TODO`/“适当处理”。
- 每个类、每个测试、每个脚本都有完整代码或完整命令。
- `preload_max_millis` 字段保留但未用于同步 preload；规格允许“≤3 s 或移出主线程”，Task 6 实测；若超 3 s，后续里程碑再做后台预读（不在本计划内）。
- `ScriptCacheHook.currentKey()` / `missSample()` 是诊断接口，未被生产路径调用；保留给 Task 6 的报告与后续调试，不属于悬空 stub（有测试/诊断用途）。

### 3. Type consistency

- `ScriptCacheKey.Result(id, canonical, fileCount, bytes, elapsedMillis)`：Task 2 定义，Task 5 `key()` 使用 `id()/fileCount()/bytes()/elapsedMillis()`。
- `CachePack.Pack(entries, bytes)`：Task 2 定义，Task 3/5 使用 `entries()/bytes()`。
- `CacheStore(Path, int, long)`：Task 2 定义，Task 3/5 使用。
- `CacheWriter(RuntimeContext, String, Map, int, long)`：Task 3 定义，Task 3 测试使用。
- `ScriptCacheHook.preload(Object, RuntimeContext)`：Task 1 定义（no-op），Task 3 替换为真实实现；签名不变。
- `ScriptCacheHook.preloadCalls/findCalls/hits/misses/spanMillis/resetForTest`：Task 1 定义，Task 3 保留，测试使用。
- `AgentTelemetry.event(kind,key,entries,bytes,millis)` / `summary(key,hits,misses,findCalls,spanMillis,entries)`：Task 1 定义，Task 3 使用；Task 5 解析 `kind/hits/misses/find_calls/span_millis`。
- `install_agent.AGENT_LINE` / `patch_lines` / `unpatch_lines`：Task 4 定义与测试一致。

### 4. Review Focus tests

| Review Focus | 测试 |
|---|---|
| 键漏输入 → 旧类 | `ScriptCacheKeyTest.keyIsStableAndChangesWithSourceAndModList` / `keyIncludesModJar` |
| 构造注入不触发 | `ScriptCacheTransformerTest`（fake）+ Task 6 S3（真实） |
| 坏 pack → 崩溃 | `CachePackTest.corruptTrailingCrcReturnsNull` / `CacheStoreTest.corruptPackLoadsNull` |
| 安装器重复/错序 | `tests/tools/test_install_agent.py` 四条 |
| `findClass` 注入破坏验证 | `ScriptCacheTransformerTest`（定义+实例化）+ Task 6 S3 |

### 5. Proportion

本计划约 2,650 行（规格 884 行），其中大部分是 SDD 要求的“可照抄代码/测试”。没有为每个 getter 写教程；没有重复 Task 1 的类文件。计划比规格长是预期内的：SDD 要求 implementer 变转录工，判断留给审查层。若 reviewer 认为某段代码属于“签名+测试已决定的转录”，可以在 review finding 里指出，由 controller 裁决是否压缩。

---

## Execution Handoff

计划已保存。**建议执行模式：pipeline**——六个任务共享 `ScriptCacheHook`/`RuntimeContext` 等核心类，wave 的写者表会冲突；worktree 的 merge 开销也不划算。pipeline 下 Task 2/3/4/5 的审查与下一任务实现可流水重叠。

请先审阅计划，尤其是：

1. **Task 1 Step 5 的门禁**：如果 `find_calls`/`span_millis` 证明真实编译人口太小，M-1d 应在写缓存前停下——这是本计划唯一可能推翻任务书的点。
2. **Task 6 的 S4 Ruling**：用 Base 11 mod 代替 CRSIDtest-only profile；若不同意，按规格原文执行。
3. **`cache-tool.sh` 的 classpath 顺序**：key 必须与 agent 完全一致；任何顺序差异都会让 S3 seed 失效。

确认后回复 `/SDD pipeline` 开始执行。
