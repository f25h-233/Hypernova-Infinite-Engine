# M-1b 法线缓存 + M-1d 诊断回归 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `GraphicsLib/cache/*_normal.png` 的 30,378 次启动期解码/上传从首屏路径拿掉（agent 懒加载补丁），顺带修掉 M-1d 的 `SourceOracle.hasSource` stat 风暴；DDS 烘焙作为可选、不进门禁的第二条路线。

**Architecture:** M-1b 主路线是在现有 `hypernova.agent` 里增加一个 `textures` transformer：按 SHA-256 锁定 GraphicsLib 1.12.1 的 `TextureData.class`，把它替换成一份编译好的补丁类。补丁只在「缓存文件存在、未失效、未强制预载」时创建一个 `loaded=false` 的 `TextureEntry`，不再 `loadTexture`；战斗前 `unloadAndPreloadTextures()` / `getTextureDataWithAutoGen()` 仍按原逻辑加载。DDS 路线不动 shaderLib，利用现成 `DDSCreator` 离线烘焙，再由 Python 工具改写 metadata/layout，作为可选项。

**Tech Stack:** Java 17（`--release 17`，class major 61）、Java Instrumentation（`ClassFileTransformer`）、ASM 9.1（已有，仅 scripts 用）、`org.json`（游戏自带 `json.jar`）、JUnit 5、Python 3.14（`pytest`）、Bash（Git Bash）、GraphicsLib 1.12.1（CC BY 4.0）、Fast Rendering 0.9.5。

**Spec:** `技术笔记-纹理按需加载.md` §7（M-1b 法线缓存桶、出口标准）、§10.1 ADR-01/02/03；本计划是论证，冲突时按规格裁决并记入 ledger。M-1d 的原始计划是 `docs/superpowers/plans/2026-10-29-m1d-scripts-cache.md`；本计划 Task 1 是它的 addendum，**addendum 优先**。

## 开工前实测（2026-10-30，controller 亲测，写进 ledger）

| 场景 | 主菜单 | 法线行数 | 法线窗口 | 说明 |
|---|---|---|---|---|
| 旧 run2（2026-10-25，无 agent） | 92.7 s | 30,401 | 49.5–78.9 s（29.4 s） | 规格的 29.6 s 桶 |
| 当前（M-1d `scripts.enabled=true`） | **187.5 s** | 30,378 | 132.0–170.4 s（38.4 s） | 脚本阶段 34.5→122.4 s |
| 当前（`scripts.enabled=false`） | **107.2 s** | 30,378 | 54.3–88.6 s（34.3 s） | 脚本阶段 29.3→45.8 s |
| `hasSource` 微基准 | — | — | — | 389 roots × 11,264 probes ≈ 4.38M stat，**45–53 s** |

> 口径注（2026-10-30 终审）：表中 30,401 / 29.4 s 来自 `m1_measure` 的**全会话**计数；用 `m1b_measure` 重测同一 `run2` 日志为 **30,378 行 / 27.9 s**（`run4` 29.6 s）。两个工具不能混用，M-1b 门禁只认 `m1b_measure`。

**结论：**
- DDS 没有失效：当前日志 30,427 条 `Loading image`，30,390 条是法线缓存，仅 37 条非缓存；`VramOptimizer` 仍启用，`mods/DDSCache` 存在。
- M-1d 的 `SourceOracle.hasSource()` 对每次 miss 做 O(roots) 次 `Files.isRegularFile`；11,264 次 rulecmd 探测 = 4.38M stat，是 187.5 s 相对 107.2 s 的主因（~80 s）。**Task 1 必须先修。**
- 法线桶在冷/热文件缓存下为 34–64 s；即使全部消掉，首屏也到不了 40 s（规格上限 ~56 s），M-1b 必要但不充分。

## Global Constraints

- Java 编译必须 `--release 17`，产物 class major version 必须是 61（`javap -verbose` 校验）。
- agent 是**可选件**：缺失、配置关闭、FR 缺失、补丁资源缺失、hash 不匹配 → 只禁用对应模块，游戏必须照常启动。
- **M-1d 边界**：Task 1 只允许改 `SourceOracle` 与 `ScriptCacheHook` 的 oracle 日志；**不得**改缓存 key/pack/store/writer/preload 语义。Tasks 2–4 只允许改 agent 引导段（注册 textures transformer）、新增 `src/agent/java/hypernova/agent/textures/**`、构建/测量工具；**不得**改 `src/main/java/hypernova/**`（M1 textures 模块冻结）。
- 补丁类**绝不能**以 `org/dark/shaders/util/TextureData.class` 的形式进入 agent jar 的 classpath 根——否则父加载器会先加载它，绕过 transformer 并改变类加载器身份。资源名固定为 `hypernova/agent/textures/TextureData.class.bin`。
- 补丁只对 SHA-256 精确匹配的 GraphicsLib 1.12.1 `TextureData.class` 生效；不匹配 → no-op + 日志。**不尝试兼容其它版本。**
- 补丁后的行为必须与原件等价，除「启动期不 load 已缓存的法线图」这一条：`preloadAllMaps=true`、`invalidateCache=true`、`isAlwaysPreload` 命中、缓存文件不存在/损坏 → 全部走原路径。
  - **实现口径注记（2026-10-30 终审）**：`CacheProbe` 只能廉价验证「文件存在 + 长度 ≥8 B」，不校验 PNG 内容。内容损坏（不可解码）的 `*_normal.png` 会被注册为懒条目，该 key 的法线图在本次及后续会话缺失，直到缓存文件被修复或删除；PNG 头校验/自愈列为 M-1d-2 之后的后续项，不在本计划内实现。
- 所有 agent 钩子必须 `catch (Throwable)`；任何异常都不能抛回游戏。
- 所有 agent 读写落在 `<saves>/hypernova/` 下；不写游戏安装目录（安装器复制 jar 除外）。
- 不新增网络下载依赖；DDS 可选路线只调用用户已有的 `DDSCreator.exe`。
- 测试除非明确标注「冒烟」，不得启动游戏；不得执行 `taskkill //F //IM node.exe`。
- 每个任务一个独立 commit；消息以 `fix(m1d):`/`feat(m1b):`/`test(m1b):`/`docs(m1b):` 开头，并附 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。
- 现有 `tools/java/run-tests.sh` 不改；agent 用 `tools/java/run-agent-tests.sh`。
- 本计划按 **pipeline** 执行（ledger 首部记录 `Mode: pipeline`）。

## Escape Hatch

- 若计划里的断言数字、测试顺序、文件路径或方法描述符与实际实现不符 → **按实际修正并报告**（写进 `task-N-report.md`），无需请示。
- 若需求自相矛盾或无法同时满足 → **停下报告 controller，不许挑一半照做**。写清矛盾原文、为什么不能同时成立、建议裁决。
- Pipeline 下只改本任务 `Touches:` 声明内的文件；需要越界 → 停下报告，等 controller 裁决。
- 若 Task 1 的 A/B 冒烟没有把菜单时间拉回 ≤130 s、脚本阶段没有回到 ≤30 s → 停，不要继续 Task 2；报告实测与诊断。

## Review Focus

1. **补丁类被父加载器提前加载**：agent jar 里若出现 `org/dark/shaders/util/TextureData.class`，mod loader 的 parent-first 会拿到错的类。Task 3 的 jar 资源断言必须变红。
2. **hash 不匹配时仍替换**：GraphicsLib 升级/换版本后必须 no-op，不能把 1.12.1 的字节塞进 1.12.2。Task 3 的 mismatch 测试 + 日志。
3. **懒条目永远不被加载**：`TextureEntry(null,...)` 必须保留 `validToLoad=true`、`spriteName=缓存路径`，战斗前 `unloadAndPreloadTextures()` 才能加载。Task 3 的 smoke（战斗内法线）与代码审查共同覆盖。
4. **`hasSource` 仍然逐次 stat**：Task 1 的「删除源文件后仍判 true」测试必须守住索引快照；否则回归会静默复活。
5. **DDS metadata 路径/尺寸错**：法线图会用错图或花屏。Task 5 的路径改写与 DX10/尺寸校验测试。

## File Structure

| 路径 | 责任 | 任务 |
|---|---|---|
| `src/agent/java/hypernova/agent/SourceOracle.java` | 后台索引 `.java` 相对路径；`hasSource` O(1) | 1 |
| `src/agent/java/hypernova/agent/ScriptCacheHook.java` | 只在 oracle ready 日志里加 `sources=` 计数 | 1 |
| `tests/agent/java/hypernova/agent/SourceOracleTest.java` | 快照/性能/顶层包回归测试 | 1 |
| `tools/java/texture_patch.py` | 把 `TextureData.java` 的 normal 分支替换成懒加载版本 | 2 |
| `tools/java/build-texture-patch.sh` | 提取/校验/编译/产出资源 | 2 |
| `tools/java/texture-patch/expected-sha256.txt` | 原 `TextureData.class` 的 SHA-256 | 2 |
| `tools/java/build-agent.sh` | 调用 patch 构建 + 打包 `hypernova/agent/textures/**` | 2/3 |
| `tests/tools/test_texture_patch.py` | patch 脚本的 pytest | 2 |
| `src/agent/java/hypernova/agent/textures/TexturePatchConfig.java` | 读 `textures.enabled` / 系统属性 | 3 |
| `src/agent/java/hypernova/agent/textures/TextureCacheTransformer.java` | hash 守卫 + 返回补丁字节 | 3 |
| `src/agent/java/hypernova/agent/HypernovaAgent.java` | 在 scripts 早退前注册 textures transformer | 3 |
| `tests/agent/java/hypernova/agent/textures/TextureCacheTransformerTest.java` | 替换/拒绝/容错/版本 | 3 |
| `tests/agent/java/hypernova/agent/textures/TexturesWiringTest.java` | agent jar 资源与注册顺序 | 3 |
| `data/config/hypernova/hypernova.json` | 增加 `textures.enabled` | 3 |
| `tools/m1b_measure.py` | 解析会话日志/agent 日志，出门禁 JSON | 4 |
| `tests/tools/test_m1b_measure.py` | 合成日志测试 | 4 |
| `tools/dds_normal_cache.py` | 可选 DDS：staging 准备 + DDSCreator 产物采纳 | 5 |
| `tests/tools/test_dds_normal_cache.py` | 路径/metadata/头部校验 | 5 |
| `docs/m1b-dds-optional.md` | DDSCreator 手工步骤 + A/B 运行手册 | 5 |
| `技术笔记-纹理按需加载.md` | §7 M-1b 状态/实测/出口 | 6 |

---

### Task 1: M-1d 热修 — SourceOracle 改成 O(1) 索引

**Files:**
- Modify: `src/agent/java/hypernova/agent/SourceOracle.java`（全文替换）
- Modify: `src/agent/java/hypernova/agent/ScriptCacheHook.java`（只改 `source oracle ready` 日志一行）
- Test: `tests/agent/java/hypernova/agent/SourceOracleTest.java`（追加 3 个测试）

**Interfaces:**
- Consumes: `RuntimeContext.gameRoot()`、`RuntimeContext.modsRoot()`（M-1d 已有）。
- Produces:
  - `SourceOracle.from(RuntimeContext) -> SourceOracle`
  - `SourceOracle.hasSource(String) -> boolean`（O(1)，只读构造时快照）
  - `SourceOracle.roots() -> List<Path>`
  - `SourceOracle.sourceCount() -> int`
  - `SourceOracle.empty() -> SourceOracle`

- [ ] **Step 1: 追加失败测试**

在 `tests/agent/java/hypernova/agent/SourceOracleTest.java` 末尾追加：

```java
    @Test
    void hasSourceUsesSnapshotNotFilesystem() throws Exception {
        Path game = tmp.resolve("g4");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("m");
        Files.createDirectories(mod.resolve("src/a"));
        Path source = mod.resolve("src/a/ModClass.java");
        Files.writeString(source, "package a; class ModClass {}");

        SourceOracle oracle = SourceOracle.from(ctx(game, mods));

        // 删除源文件后仍然必须判 true：hasSource 只能读 from() 时建立的索引。
        // 旧实现每次调用都 Files.isRegularFile，删除后会变 false，导致
        // 11,264 次 rulecmd 探测 × 389 roots ≈ 4.38M stat 的启动回归。
        Files.delete(source);
        assertTrue(oracle.hasSource("a.ModClass"),
                "hasSource 必须使用构造期快照，不能在每次调用时访问文件系统");
    }

    @Test
    void hasSourceIsCheapWithManyRoots() throws Exception {
        Path game = tmp.resolve("g5");
        Path mods = game.resolve("mods");
        Files.createDirectories(mods);
        for (int i = 0; i < 300; i++) {
            Files.createDirectories(mods.resolve("m" + i + "/src"));
        }

        SourceOracle oracle = SourceOracle.from(ctx(game, mods));
        assertTimeoutPreemptively(java.time.Duration.ofSeconds(5), () -> {
            for (int i = 0; i < 11_264; i++) {
                oracle.hasSource("com.fs.starfarer.api.impl.campaign.rulecmd.T" + i + "CMD");
            }
        }, "11,264 次 hasSource 在 300 个 roots 下必须远低于 5 s（旧实现约 30–50 s）");
    }

    @Test
    void findsSourceInTopLevelPackageDir() throws Exception {
        Path game = tmp.resolve("g6");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("m");
        Files.createDirectories(mod.resolve("org/example"));
        Files.writeString(mod.resolve("org/example/TopLevel.java"),
                "package org.example; class TopLevel {}");

        SourceOracle oracle = SourceOracle.from(ctx(game, mods));

        assertTrue(oracle.hasSource("org.example.TopLevel"),
                "mod 根下的顶层包目录（不在 src/ 下）也必须被索引");
    }
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash tools/java/run-agent-tests.sh SourceOracle`

Expected: `hasSourceUsesSnapshotNotFilesystem` FAIL（删除后返回 false）；`hasSourceIsCheapWithManyRoots` FAIL（`assertTimeoutPreemptively` 超时，旧实现约 30–50 s）。若第二个测试跑得太久，JUnit 的 preemptive timeout 会在 5 s 抛 `TimeoutException`，进程继续。

- [ ] **Step 3: 全文替换 `SourceOracle.java`**

```java
package hypernova.agent;

import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Stream;

/**
 * 判定某个点分类名在本次加载环境里是否存在对应的 {@code .java} 源。
 *
 * <p>用途：区分「真正的缓存 miss（本可以命中，但缓存里没有）」和「探测性查询
 * （游戏 jar 里的类，根本没有源码，永远不可能命中）」。前者才是命中率的分母。
 *
 * <p><b>M-1d 热修（2026-10-30）：</b>旧实现在每次 {@link #hasSource(String)} 时
 * 对每个 root 做一次 {@code Files.isRegularFile}。260mods 的 FR rulecmd 探测有
 * 11,264 次 miss、389 个 root，合计约 4.38M 次 stat；实测给首屏加了 45–53 s。
 * 现在 {@link #from(RuntimeContext)} 在后台线程一次性遍历 root，建立
 * 「相对路径 -> .java」集合；{@code hasSource} 只做 O(1) set lookup。
 *
 * <p>没有 roots 或索引为空时保守返回 true（与旧行为一致：不把真实缺陷掩盖成
 * 「本来就不该命中」）。
 */
public final class SourceOracle {
    /** 这些目录不可能包含 .java 源码；遍历时整棵子树跳过，避免扫 125k 张图。 */
    private static final Set<String> SKIP_DIRS = Set.of(
            "graphics", "sounds", "sound", "images", "music", "jars", "cache",
            "saves", "screenshots", "javadoc", ".git", "build", "dist", "logs", "common");

    /** 源根列表（absolute）。 */
    private final List<Path> roots;
    /** root.relativize(file) 的 POSIX 形式，例如 "src/a/ModClass.java"。 */
    private final Set<String> sourcePaths;

    private SourceOracle(List<Path> roots, Set<String> sourcePaths) {
        this.roots = roots;
        this.sourcePaths = sourcePaths;
    }

    /** 从运行时上下文收集搜索根，并在后台线程一次性建立源码索引。 */
    public static SourceOracle from(RuntimeContext ctx) {
        List<Path> roots = collectRoots(ctx);
        return new SourceOracle(roots, indexSources(roots));
    }

    /** 空判定器：没有根时一切按「有源码」处理（保守，不虚报命中率）。 */
    public static SourceOracle empty() {
        return new SourceOracle(List.of(), Set.of());
    }

    public List<Path> roots() {
        return roots;
    }

    /** 索引里的 .java 文件数；用于 agent 日志诊断。 */
    public int sourceCount() {
        return sourcePaths.size();
    }

    /**
     * 点分类名是否有对应源码。
     *
     * <p>内嵌类（{@code Outer$Inner}）由同一份源编译产出，按外部类判定。
     * 本方法只读构造期索引，**绝不访问文件系统**。
     */
    public boolean hasSource(String binaryName) {
        if (binaryName == null || binaryName.isEmpty()) return false;
        // 没有根 / 索引为空：无法判断，返回 true 保守，不把真实缺陷掩盖成「不该命中」。
        if (roots.isEmpty() || sourcePaths.isEmpty()) return true;
        String base = binaryName;
        int dollar = base.indexOf('$');
        if (dollar > 0) base = base.substring(0, dollar);
        String rel = base.replace('.', '/') + ".java";
        return sourcePaths.contains(rel);
    }

    @Override
    public String toString() {
        return "SourceOracle" + roots.stream().map(Path::toString)
                .map(s -> s.toLowerCase(Locale.ROOT)).toList();
    }

    // ------------------------------------------------------------------ roots

    private static List<Path> collectRoots(RuntimeContext ctx) {
        List<Path> roots = new ArrayList<>();
        try {
            Path game = ctx.gameRoot();
            if (game != null) {
                // 根必须是 starsector-core 本身，不是 starsector-core/data/scripts。
                // 包名相对 starsector-core 组织：data.hullmods.X -> starsector-core/data/hullmods/X.java。
                // 只收 data/scripts 会漏掉基座 116 个 .java 里的 88 个（实测：116 个全部误判为无源码）。
                Path core = game.resolve("starsector-core");
                if (Files.isDirectory(core)) roots.add(core.toAbsolutePath().normalize());
            }
            Path mods = ctx.modsRoot();
            if (mods != null && Files.isDirectory(mods)) {
                try (Stream<Path> s = Files.list(mods)) {
                    s.filter(Files::isDirectory).forEach(dir -> {
                        // mod 根本身：包名是按 mod 目录的相对路径组织的，
                        // 例如 data/scripts/AvaliModPlugin.java 对应类 data.scripts.AvaliModPlugin。
                        roots.add(dir.toAbsolutePath().normalize());
                        Path src = dir.resolve("src");
                        if (Files.isDirectory(src)) roots.add(src.toAbsolutePath().normalize());
                        Path ds = dir.resolve("data/scripts");
                        if (Files.isDirectory(ds)) roots.add(ds.toAbsolutePath().normalize());
                    });
                } catch (Throwable ignored) {
                    // 扫描失败：保留已收集的根
                }
            }
        } catch (Throwable ignored) {
            // 任何失败都退化为「全部视为有源码」
        }
        return roots;
    }

    // ----------------------------------------------------------------- index

    private static Set<String> indexSources(List<Path> roots) {
        Set<String> out = new HashSet<>(16_384);
        // 每个 root 是独立的命名空间：同一个文件在 mod 根下是 src/a/X.java，
        // 在 src 根下是 a/X.java；两者都必须进集合，否则 hasSource("a.X") 会漏。
        // 嵌套 root 重复遍历 source 目录的代价很小（相对 4.38M 次 stat），必须保留。
        for (Path root : roots) walk(root, out);
        return out;
    }

    private static void walk(Path root, Set<String> out) {
        try {
            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs) {
                    if (!dir.equals(root)) {
                        String name = dir.getFileName() == null
                                ? "" : dir.getFileName().toString().toLowerCase(Locale.ROOT);
                        if (SKIP_DIRS.contains(name)) return FileVisitResult.SKIP_SUBTREE;
                    }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                    String name = file.getFileName() == null ? "" : file.getFileName().toString();
                    if (name.toLowerCase(Locale.ROOT).endsWith(".java")) {
                        out.add(root.relativize(file).toString().replace('\\', '/'));
                    }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFileFailed(Path file, IOException exc) {
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException | RuntimeException ignored) {
            // 单个 root 失败不影响其它 root；索引为空时 hasSource 保守返回 true。
        }
    }
}
```

- [ ] **Step 4: 更新 oracle 日志（只改一行）**

在 `src/agent/java/hypernova/agent/ScriptCacheHook.java` 的 `initSourceOracleAsync` 里，把：

```java
                AgentLog.info("source oracle ready: roots=" + o.roots().size()
                        + ", took " + (System.nanoTime() - t0) / 1_000_000 + " ms");
```

改成：

```java
                AgentLog.info("source oracle ready: roots=" + o.roots().size()
                        + ", sources=" + o.sourceCount()
                        + ", took " + (System.nanoTime() - t0) / 1_000_000 + " ms");
```

- [ ] **Step 5: 跑 agent 测试**

Run: `bash tools/java/run-agent-tests.sh SourceOracle`

Expected: 全部 PASS（含原有 5 个 + 新增 3 个）。`hasSourceIsCheapWithManyRoots` 应在 < 1 s 内完成。

- [ ] **Step 6: 跑全量 agent 测试**

Run: `bash tools/java/run-agent-tests.sh`

Expected: 36/36 原有测试 + 新增 3 个，全部 PASS。若 `ScriptCacheHookPreloadTest` 依赖 oracle 日志文本，按 Escape Hatch 修正并报告。

- [ ] **Step 7: Commit**

```bash
git add src/agent/java/hypernova/agent/SourceOracle.java \
        src/agent/java/hypernova/agent/ScriptCacheHook.java \
        tests/agent/java/hypernova/agent/SourceOracleTest.java
git commit -m "fix(m1d): index source paths so hasSource is O(1) instead of O(roots) stats

The FR rulecmd probe path calls findClass 11,264 times; the old oracle did
Files.isRegularFile for each of 389 roots per miss (~4.38M stats) and added
45-53 s to first screen. Build a relative .java path set once in from() and
make hasSource a set lookup.

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

- [ ] **Step 8: Controller A/B 冒烟（不由 implementer 执行）**

Controller 运行：

```bash
# A: scripts 开（修复后）
python tools/smoke_run.py --profile miko-lite --rounds 1 --linger 8 --json-out build/m1b-oracle-fix-on.json

# B: 临时把安装目录的 scripts.enabled 改 false，再跑
#   Starsector-098-260mods/mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json
# 跑完必须恢复
python tools/smoke_run.py --profile miko-lite --rounds 1 --linger 8 --json-out build/m1b-oracle-fix-off.json
```

Expected:
- A（修复后 scripts on）：主菜单 **≤ 150 s**（相对 187.5 s 回收 ≥ 35 s），脚本阶段 ≤ 45 s，法线窗口 ~34–40 s。
- A 与 B 的差**不设硬门禁**：B（scripts off）是 107.2 s，A 里可能还有 cache/hook 的残余开销；把差值写进报告即可，不阻塞 M-1b。
- agent 日志出现 `source oracle ready: roots=..., sources=...`，`sources` 在 12,000–30,000 量级（同一文件在不同 root 下会以不同相对路径重复计数，量级正确即可）。

若 A 仍 > 150 s：停，记录 agent 日志/会话日志，按 Escape Hatch 报告，不进入 Task 2。

---

### Task 2: TextureData 懒加载补丁的构建管线

**Files:**
- Create: `tools/java/texture_patch.py`
- Create: `tools/java/build-texture-patch.sh`
- Create: `tools/java/texture-patch/expected-sha256.txt`
- Modify: `tools/java/build-agent.sh`（调用 patch 构建 + 打包资源）
- Test: `tests/tools/test_texture_patch.py`

**Interfaces:**
- Consumes: `Starsector-098-260mods/mods/GraphicsLib/jars/Graphics.jar` 里的 `org/dark/shaders/util/TextureData.java` / `.class`（GraphicsLib 1.12.1）。
- Produces:
  - `python tools/java/texture_patch.py --source <in.java> --out <out.java>`：成功 exit 0；hash/版本不符 exit 2。
  - `bash tools/java/build-texture-patch.sh [game-dir]` → `build/agent/textures/hypernova/agent/textures/TextureData.class.bin`、`build/agent/textures/hypernova/agent/textures/patch.properties`、`build/agent/texture-original.class`（测试用，不打包）。
  - `patch.properties` 至少含 `target`、`sourceSha256`、`patchedSha256`、`graphicsLibVersion`。

- [ ] **Step 1: 写失败测试**

`tests/tools/test_texture_patch.py`：

```python
import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JAR = ROOT / "Starsector-098-260mods/mods/GraphicsLib/jars/Graphics.jar"
EXPECTED_CLASS_SHA = "6a4302bcacd2dd90f6637c815d1443ddfdb3d28ff59095d48c875358de4e8594"


def extract_source(tmp_path):
    if not JAR.is_file():
        pytest.skip("GraphicsLib jar not installed")
    with zipfile.ZipFile(JAR) as z:
        return z.read("org/dark/shaders/util/TextureData.java")


def test_patch_adds_lazy_entry_without_loading(tmp_path):
    src = extract_source(tmp_path)
    inp = tmp_path / "TextureData.java"
    out = tmp_path / "TextureData.patched.java"
    inp.write_bytes(src)
    r = subprocess.run([sys.executable, str(ROOT / "tools/java/texture_patch.py"),
                        "--source", str(inp), "--out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    text = out.read_text(encoding="utf-8")
    assert "hasCachedNormalMap(cachePath)" in text
    assert "new TextureEntry(null, cachePath" in text
    assert "!invalidateCache && !GraphicsLibSettings.preloadAllMaps()" in text
    # 原路径必须还在（回退时仍走 autoGenNormalMap）
    assert "autoGenNormalMap(spriteName, key, type, frame)" in text


def test_patch_rejects_wrong_source_hash(tmp_path):
    src = bytearray(extract_source(tmp_path))
    src[100] ^= 0xFF
    inp = tmp_path / "TextureData.java"
    out = tmp_path / "out.java"
    inp.write_bytes(src)
    r = subprocess.run([sys.executable, str(ROOT / "tools/java/texture_patch.py"),
                        "--source", str(inp), "--out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert "sha256 mismatch" in (r.stderr + r.stdout)


def test_patch_is_idempotence_guarded(tmp_path):
    src = extract_source(tmp_path)
    inp = tmp_path / "TextureData.java"
    out1 = tmp_path / "out1.java"
    out2 = tmp_path / "out2.java"
    inp.write_bytes(src)
    cmd = [sys.executable, str(ROOT / "tools/java/texture_patch.py"),
           "--source", str(inp), "--out", str(out1)]
    assert subprocess.run(cmd, capture_output=True).returncode == 0
    cmd2 = [sys.executable, str(ROOT / "tools/java/texture_patch.py"),
            "--source", str(out1), "--out", str(out2)]
    r = subprocess.run(cmd2, capture_output=True, text=True)
    assert r.returncode != 0
    assert "already patched" in (r.stderr + r.stdout)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/tools/test_texture_patch.py -q`

Expected: FAIL（`tools/java/texture_patch.py` 不存在 / import 失败）。

- [ ] **Step 3: 实现 `tools/java/texture_patch.py`**

```python
#!/usr/bin/env python3
"""Apply the Hypernova lazy-normal-cache patch to GraphicsLib 1.12.1 TextureData.java.

The patch is intentionally exact-version: the source SHA-256 is pinned, and the
method we rewrite is located structurally. Any other GraphicsLib version fails
closed (exit 2) instead of producing a half-patched class.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

EXPECTED_SOURCE_SHA = "db95f036a87276685ee3c7ae5b57671866d6c68542cdf3f9c3adf8cae4bacaa4"
METHOD_ANCHOR = "    public static void mapSpriteToMNSWithAutoGen("
HELPER_ANCHOR = "    private static String filePathForCache(String key, ObjectType type, int frame) {"
PATCHED_MARKER = "Hypernova: startup registers the cached normal map"
METHOD_GUARDS = (
    "autoGenNormalMap(spriteName, key, type, frame)",
    'isAlwaysPreload(key, "ship")',
    "normalSpriteNameToEntry.put(spriteName, entry);",
)


NEW_METHOD = r'''    public static void mapSpriteToMNSWithAutoGen(String key, String spriteName, ObjectType type, int frame, boolean autoGen, boolean autoGenOverride) {
        if ((spriteName != null) && !spriteName.isEmpty() && (key != null) && !key.isEmpty()) {
            if (frame > 0) {
                spriteName = getAnimNameForFrame(spriteName, frame);
            }
            if (CHECK_INEFFICIENT) {
                alertInefficientSprite(spriteName, type);
            }
            if (isLoadMaterial()) {
                TextureEntry entry = getTextureDataWithAutoGen(key, TextureDataType.MATERIAL_MAP, type, frame, null, true);
                if (entry == null) {
                    entry = materialSpriteNameToEntry.get(spriteName);
                    if (entry != null) {
                        materialKeyToEntry.put(getTextureDataKey(key, type, frame), entry);
                        if ((entry.spriteName != null) && !spriteName.isEmpty()) {
                            mnsSpritePathSet.add(entry.spriteName);
                        }
                    }
                } else {
                    materialSpriteNameToEntry.put(spriteName, entry);
                }
            }
            if (isLoadNormal()) {
                TextureEntry entry = getTextureDataWithAutoGen(key, TextureDataType.NORMAL_MAP, type, frame, null, true);
                if (entry == null) {
                    entry = normalSpriteNameToEntry.get(spriteName);
                    if (entry == null) {
                        if (autoGen) {
                            final boolean forceLoad = isAlwaysPreloadFor(type, key);
                            final String cachePath = filePathForCache(key, type, frame);
                            /* Hypernova: startup registers the cached normal map without loading it.
                             * The original implementation decoded and uploaded every cached normal map
                             * just to obtain its dimensions, then unloaded it again when
                             * preloadAllMaps=false. On 260mods those 30,378 load/unload cycles cost
                             * 29-64 s of first-screen time. The lazy entry below is loaded on demand by
                             * unloadAndPreloadTextures() / getTextureDataWithAutoGen() exactly as before.
                             */
                            if (!invalidateCache && !GraphicsLibSettings.preloadAllMaps()
                                    && !forceLoad && hasCachedNormalMap(cachePath)) {
                                entry = new TextureEntry(null, cachePath, 1f, !autoGenOverride, true, false, false);
                                normalKeyToEntry.put(getTextureDataKey(key, type, frame), entry);
                                if ((entry.spriteName != null) && !spriteName.isEmpty()) {
                                    mnsSpritePathSet.add(entry.spriteName);
                                }
                                normalSpriteNameToEntry.put(spriteName, entry);
                            } else {
                                final SpriteAPI sprite = autoGenNormalMap(spriteName, key, type, frame);
                                if (sprite != null) {
                                    /* Even if we're not preloading, we do need to load the sprite when establishing the
                                     * cache of auto-generated normal maps.  However, once we have that sprite and have
                                     * made its texture entry, it's safe to just unload it to save memory.
                                     */
                                    entry = new TextureEntry(sprite, cachePath, 1f, !autoGenOverride, true, true, forceLoad);
                                    if (!GraphicsLibSettings.preloadAllMaps()) {
                                        final int texId = entry.sprite.getTextureId();
                                        Global.getSettings().unloadTexture(entry.spriteName);
                                        GL11.glDeleteTextures(texId);
                                        entry.sprite = null;
                                        entry.loaded = false;
                                        vramUsageBytes -= entry.vramSize;
                                    }
                                    normalKeyToEntry.put(getTextureDataKey(key, type, frame), entry);
                                    if ((entry.spriteName != null) && !spriteName.isEmpty()) {
                                        mnsSpritePathSet.add(entry.spriteName);
                                    }
                                    normalSpriteNameToEntry.put(spriteName, entry);
                                }
                            }
                        }
                    } else {
                        normalKeyToEntry.put(getTextureDataKey(key, type, frame), entry);
                        if ((entry.spriteName != null) && !spriteName.isEmpty()) {
                            mnsSpritePathSet.add(entry.spriteName);
                        }
                    }
                } else {
                    normalSpriteNameToEntry.put(spriteName, entry);
                }
            }
            if (isLoadSurface()) {
                TextureEntry entry = getTextureDataWithAutoGen(key, TextureDataType.SURFACE_MAP, type, frame, null, true);
                if (entry == null) {
                    entry = surfaceSpriteNameToEntry.get(spriteName);
                    if (entry != null) {
                        surfaceKeyToEntry.put(getTextureDataKey(key, type, frame), entry);
                        if ((entry.spriteName != null) && !spriteName.isEmpty()) {
                            mnsSpritePathSet.add(entry.spriteName);
                        }
                    }
                } else {
                    surfaceSpriteNameToEntry.put(spriteName, entry);
                }
            }
        }
    }'''


HELPERS = r'''    private static boolean isAlwaysPreloadFor(ObjectType type, String key) {
        switch (type) {
            case SHIP:
                return isAlwaysPreload(key, "ship");
            case TURRET:
                return isAlwaysPreload(key, "turret");
            case TURRET_BARREL:
                return isAlwaysPreload(key, "turretbarrel");
            case TURRET_UNDER:
                return isAlwaysPreload(key, "turretunder");
            case HARDPOINT:
                return isAlwaysPreload(key, "hardpoint");
            case HARDPOINT_BARREL:
                return isAlwaysPreload(key, "hardpointbarrel");
            case HARDPOINT_UNDER:
                return isAlwaysPreload(key, "hardpointunder");
            case MISSILE:
                return isAlwaysPreload(key, "missile");
            default:
                return false;
        }
    }

    private static boolean hasCachedNormalMap(String cachePath) {
        try {
            final String modPath = Global.getSettings().getModManager().getModSpec("shaderLib").getPath();
            final java.io.File file = new java.io.File(modPath, cachePath);
            return file.isFile() && (file.length() >= 8L);
        } catch (Throwable t) {
            return false;
        }
    }

'''


def find_method(text: str) -> tuple[int, int]:
    start = text.index(METHOD_ANCHOR)
    i = text.index("{", start)
    depth = 0
    j = i
    while j < len(text):
        c = text[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return start, j + 1
        j += 1
    raise SystemExit("unterminated mapSpriteToMNSWithAutoGen method")


def patch_text(text: str) -> str:
    if PATCHED_MARKER in text:
        raise SystemExit("already patched")
    start, end = find_method(text)
    old = text[start:end]
    for guard in METHOD_GUARDS:
        if guard not in old:
            raise SystemExit(f"unexpected TextureData version: missing guard {guard!r}")
    text = text[:start] + NEW_METHOD + text[end:]
    if HELPER_ANCHOR not in text:
        raise SystemExit("helper anchor missing")
    text = text.replace(HELPER_ANCHOR, HELPERS + HELPER_ANCHOR, 1)
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    raw = Path(args.source).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != EXPECTED_SOURCE_SHA:
        print(f"sha256 mismatch: {sha} != {EXPECTED_SOURCE_SHA}", file=sys.stderr)
        return 2
    text = raw.decode("utf-8")
    out = patch_text(text)
    Path(args.out).write_text(out, encoding="utf-8", newline="\n")
    print(f"patched {args.source} -> {args.out} ({len(out)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/tools/test_texture_patch.py -q`

Expected: 3 passed（若 GraphicsLib jar 不存在则 skip）。

- [ ] **Step 5: 写 `tools/java/texture-patch/expected-sha256.txt`**

内容（一行）：

```text
6a4302bcacd2dd90f6637c815d1443ddfdb3d28ff59095d48c875358de4e8594
```

- [ ] **Step 6: 实现 `tools/java/build-texture-patch.sh`**

```bash
#!/usr/bin/env bash
# 用法: bash tools/java/build-texture-patch.sh [game-dir]
# 产出: build/agent/textures/hypernova/agent/textures/{TextureData.class.bin,patch.properties}
#       build/agent/textures/original.class (测试用，不打包)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
ROOT_W="$(winpath "$ROOT")"
GAME="${1:-$ROOT_W/Starsector-098-260mods}"
GLIB="$GAME/mods/GraphicsLib/jars/Graphics.jar"
CORE="$GAME/starsector-core"
OUT="$ROOT_W/build/agent/textures"
WORK="$ROOT_W/build/texture-patch"
RES="$OUT/hypernova/agent/textures"
EXPECTED_CLASS="$(tr -d '[:space:]' < "$ROOT_W/tools/java/texture-patch/expected-sha256.txt")"

if [ ! -f "$GLIB" ]; then echo "FATAL: missing $GLIB" >&2; exit 2; fi
if [ ! -f "$CORE/starfarer.api.jar" ]; then echo "FATAL: missing game jars under $CORE" >&2; exit 2; fi

rm -rf "$WORK" "$RES"
mkdir -p "$WORK/orig" "$WORK/src/org/dark/shaders/util" "$WORK/classes" "$RES"

unzip -p "$GLIB" org/dark/shaders/util/TextureData.java  > "$WORK/orig/TextureData.java"
unzip -p "$GLIB" org/dark/shaders/util/TextureData.class > "$WORK/orig/TextureData.class"
actual_class="$(sha256sum "$WORK/orig/TextureData.class" | cut -d' ' -f1)"
if [ "$actual_class" != "$EXPECTED_CLASS" ]; then
  echo "FATAL: TextureData.class sha256 mismatch: $actual_class != $EXPECTED_CLASS" >&2
  exit 2
fi

python "$ROOT_W/tools/java/texture_patch.py" \
  --source "$WORK/orig/TextureData.java" \
  --out    "$WORK/src/org/dark/shaders/util/TextureData.java"

CP="$CORE/starfarer_obf.jar;$CORE/starfarer.api.jar;$CORE/lwjgl.jar;$CORE/lwjgl_util.jar;$CORE/json.jar;$CORE/log4j-1.2.9.jar;$GLIB"
javac --release 17 -encoding UTF-8 -nowarn -cp "$CP" \
  -d "$WORK/classes" "$WORK/src/org/dark/shaders/util/TextureData.java"

javap -verbose -cp "$WORK/classes" org.dark.shaders.util.TextureData 2>/dev/null \
  | grep -q "major version: 61" || { echo "FATAL: patched class major != 61" >&2; exit 2; }

cp "$WORK/classes/org/dark/shaders/util/TextureData.class" "$RES/TextureData.class.bin"
cp "$WORK/orig/TextureData.class" "$ROOT_W/build/agent/texture-original.class"
patched_sha="$(sha256sum "$RES/TextureData.class.bin" | cut -d' ' -f1)"
printf '%s\n' \
  'target=org/dark/shaders/util/TextureData' \
  "sourceSha256=$actual_class" \
  "patchedSha256=$patched_sha" \
  'graphicsLibVersion=1.12.1' > "$RES/patch.properties"

echo "OK: $RES/TextureData.class.bin (patched=$patched_sha)"
```

- [ ] **Step 7: 接入 `tools/java/build-agent.sh`**

在 `build-agent.sh` 的 `rm -rf "$OUT/classes"` **之前**插入：

```bash
# M-1b: 编译并产出 TextureData 懒加载补丁资源。缺 jar 时失败关闭，不生成半成品。
bash "$ROOT_W/tools/java/build-texture-patch.sh" >/dev/null
```

在 `jar --create` 那一行追加 `-C "$OUT/textures" .`：

```bash
jar --create --file "$OUT/hypernova.agent.jar" --manifest "$OUT/MANIFEST.MF" \
  -C "$OUT/classes" . -C "$OUT/asm" . -C "$OUT/textures" .
```

并在现有 ASM 断言之后追加两条产物断言：

```bash
if ! printf '%s\n' "$jar_listing" | grep -q 'hypernova/agent/textures/TextureData.class.bin'; then
  echo "FATAL: agent jar 不含 textures patch resource" >&2
  exit 1
fi
if printf '%s\n' "$jar_listing" | grep -q '^org/dark/shaders/util/TextureData.class$'; then
  echo "FATAL: patched TextureData.class must not be on the agent classpath" >&2
  exit 1
fi
```

- [ ] **Step 8: 构建并校验**

Run:

```bash
bash tools/java/build-texture-patch.sh
bash tools/java/build-agent.sh
jar --list --file build/agent/hypernova.agent.jar | grep 'hypernova/agent/textures'
```

Expected:
- `OK: .../TextureData.class.bin (patched=...)`
- agent jar 含 `hypernova/agent/textures/TextureData.class.bin` + `patch.properties`
- agent jar **不含** `org/dark/shaders/util/TextureData.class`

- [ ] **Step 9: Commit**

```bash
git add tools/java/texture_patch.py tools/java/build-texture-patch.sh \
        tools/java/texture-patch/expected-sha256.txt \
        tools/java/build-agent.sh tests/tools/test_texture_patch.py
git commit -m "feat(m1b): build a hash-pinned lazy-normal-cache TextureData patch

Extract GraphicsLib 1.12.1 TextureData.java from the installed jar, verify its
source/class SHA-256, rewrite the normal-map branch to register a lazy entry
instead of loading every cached PNG, compile with --release 17, and embed the
class bytes under a non-class resource path so the parent loader cannot see it.

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: Agent textures transformer + 配置 + 接线

**Files:**
- Create: `src/agent/java/hypernova/agent/textures/TexturePatchConfig.java`
- Create: `src/agent/java/hypernova/agent/textures/TextureCacheTransformer.java`
- Modify: `src/agent/java/hypernova/agent/HypernovaAgent.java`
- Modify: `data/config/hypernova/hypernova.json`（增加 `textures` 段）
- Test: `tests/agent/java/hypernova/agent/textures/TextureCacheTransformerTest.java`
- Test: `tests/agent/java/hypernova/agent/textures/TexturesWiringTest.java`

**Interfaces:**
- Consumes: Task 2 的 `build/agent/textures/hypernova/agent/textures/{TextureData.class.bin,patch.properties}`；`hypernova.agent.AgentLog`（M-1d 已有）。
- Produces:
  - `TexturePatchConfig.load() -> TexturePatchConfig`；`TexturePatchConfig.enabled() -> boolean`
  - `TextureCacheTransformer.create() -> TextureCacheTransformer | null`
  - `TextureCacheTransformer.transform(ClassLoader, String, Class<?>, ProtectionDomain, byte[]) -> byte[]`
  - `TextureCacheTransformer.TARGET = "org/dark/shaders/util/TextureData"`
  - `TextureCacheTransformer.sha256(byte[]) -> String`（package-private，测试用）

- [ ] **Step 1: 写失败测试**

`tests/agent/java/hypernova/agent/textures/TextureCacheTransformerTest.java`：

```java
package hypernova.agent.textures;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class TextureCacheTransformerTest {
    private static final Path ORIG = Path.of("build/agent/texture-original.class");
    private static final Path PATCHED =
            Path.of("build/agent/textures/hypernova/agent/textures/TextureData.class.bin");

    private static TextureCacheTransformer transformer() throws Exception {
        byte[] orig = Files.readAllBytes(ORIG);
        byte[] patched = Files.readAllBytes(PATCHED);
        return new TextureCacheTransformer(patched, TextureCacheTransformer.sha256(orig));
    }

    @Test
    void replacesTheExactKnownOriginal() throws Exception {
        byte[] orig = Files.readAllBytes(ORIG);
        byte[] patched = Files.readAllBytes(PATCHED);
        byte[] out = transformer().transform(null, TextureCacheTransformer.TARGET, null, null, orig);
        assertNotNull(out, "hash 匹配时必须返回补丁字节");
        assertArrayEquals(patched, out);
    }

    @Test
    void rejectsDifferentBytes() throws Exception {
        byte[] orig = Files.readAllBytes(ORIG);
        byte[] mutated = orig.clone();
        mutated[mutated.length - 1] ^= 0x01;
        assertNull(transformer().transform(null, TextureCacheTransformer.TARGET, null, null, mutated),
                "hash 不匹配必须 no-op，不能把 1.12.1 的字节塞进别的版本");
    }

    @Test
    void ignoresUnrelatedClassesAndNullInputs() throws Exception {
        TextureCacheTransformer t = transformer();
        assertNull(t.transform(null, "com/example/Other", null, null, new byte[]{1, 2, 3}));
        assertNull(t.transform(null, TextureCacheTransformer.TARGET, null, null, null));
        assertNull(t.transform(null, TextureCacheTransformer.TARGET, String.class, null,
                new byte[]{1, 2, 3}));
    }

    @Test
    void neverThrowsOnGarbage() throws Exception {
        TextureCacheTransformer t = transformer();
        assertDoesNotThrow(() -> t.transform(null, TextureCacheTransformer.TARGET, null, null,
                new byte[]{(byte) 0xCA, (byte) 0xFE}));
    }

    @Test
    void patchedClassIsJava17() throws Exception {
        byte[] p = Files.readAllBytes(PATCHED);
        int major = ((p[6] & 0xFF) << 8) | (p[7] & 0xFF);
        assertEquals(61, major, "补丁类必须是 --release 17（major 61）");
    }
}
```

`tests/agent/java/hypernova/agent/textures/TexturesWiringTest.java`：

```java
package hypernova.agent.textures;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.jar.JarFile;

import static org.junit.jupiter.api.Assertions.*;

class TexturesWiringTest {
    @Test
    void agentJarCarriesPatchResourceButNotTheClass() throws Exception {
        try (JarFile jar = new JarFile("build/agent/hypernova.agent.jar")) {
            assertNotNull(jar.getEntry("hypernova/agent/textures/TextureData.class.bin"),
                    "补丁字节必须以非 class 资源打包");
            assertNotNull(jar.getEntry("hypernova/agent/textures/patch.properties"));
            assertNull(jar.getEntry("org/dark/shaders/util/TextureData.class"),
                    "补丁类不能出现在 agent classpath 根，否则父加载器会先加载它");
        }
    }

    @Test
    void premainRegistersTexturesBeforeTheScriptsEarlyReturn() throws Exception {
        String src = Files.readString(Path.of("src/agent/java/hypernova/agent/HypernovaAgent.java"));
        int textures = src.indexOf("addTransformer(transformer, false)");
        int scriptsGate = src.indexOf("scripts cache disabled by config");
        assertTrue(textures > 0, "premain 必须注册 textures transformer");
        assertTrue(scriptsGate > 0, "scripts 早退必须还在");
        assertTrue(textures < scriptsGate,
                "textures 注册必须在 scripts 早退之前，否则 scripts 关闭时纹理补丁也失效");
    }
}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash tools/java/run-agent-tests.sh textures`

Expected: 编译失败/测试失败（类不存在）。

- [ ] **Step 3: 实现 `TexturePatchConfig.java`**

```java
package hypernova.agent.textures;

import org.json.JSONObject;

import java.nio.file.Files;
import java.nio.file.Path;

/** 读取 hypernova.json 的 textures 段；系统属性 hypernova.textures 优先。 */
public record TexturePatchConfig(boolean enabled) {

    public static TexturePatchConfig load() {
        String prop = System.getProperty("hypernova.textures");
        if (prop != null && !prop.isBlank()) {
            return new TexturePatchConfig(Boolean.parseBoolean(prop));
        }
        Path file = locateConfig();
        if (file == null || !Files.isRegularFile(file)) {
            // agent 已安装但没有配置文件：默认开启（补丁就是本模块的功能），
            // 显式 enabled=false 才关闭。
            return new TexturePatchConfig(true);
        }
        try {
            JSONObject root = new JSONObject(Files.readString(file));
            JSONObject textures = root.optJSONObject("textures");
            if (textures == null) return new TexturePatchConfig(true);
            return new TexturePatchConfig(textures.optBoolean("enabled", true));
        } catch (Throwable t) {
            // 配置坏了不能阻止游戏启动；默认开启，日志在 transformer 创建处记录。
            return new TexturePatchConfig(true);
        }
    }

    private static Path locateConfig() {
        try {
            var src = TexturePatchConfig.class.getProtectionDomain().getCodeSource();
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
        return null;
    }
}
```

- [ ] **Step 4: 实现 `TextureCacheTransformer.java`**

```java
package hypernova.agent.textures;

import hypernova.agent.AgentLog;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.lang.instrument.ClassFileTransformer;
import java.security.MessageDigest;
import java.security.ProtectionDomain;
import java.util.HexFormat;
import java.util.Properties;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 把 GraphicsLib 1.12.1 的 TextureData 替换成「缓存法线图只登记、不加载」的补丁类。
 *
 * <p>只对 SHA-256 精确匹配的原类生效；其它版本一律 no-op，绝不猜测。
 */
public final class TextureCacheTransformer implements ClassFileTransformer {
    public static final String TARGET = "org/dark/shaders/util/TextureData";

    private static final String RES =
            "/hypernova/agent/textures/TextureData.class.bin";
    private static final String PROPS =
            "/hypernova/agent/textures/patch.properties";

    private final byte[] patched;
    private final String expectedSha;
    private final AtomicBoolean applied = new AtomicBoolean();
    private final AtomicBoolean mismatch = new AtomicBoolean();

    TextureCacheTransformer(byte[] patched, String expectedSha) {
        this.patched = patched;
        this.expectedSha = expectedSha;
    }

    /** 读取打包资源；缺失/损坏返回 null，agent 继续启动。 */
    public static TextureCacheTransformer create() {
        try {
            byte[] bytes = readAll(TextureCacheTransformer.class.getResourceAsStream(RES));
            Properties props = new Properties();
            try (InputStream in = TextureCacheTransformer.class.getResourceAsStream(PROPS)) {
                if (in == null) {
                    AgentLog.info("textures: patch.properties missing; texture patch disabled");
                    return null;
                }
                props.load(in);
            }
            String sha = props.getProperty("sourceSha256", "");
            if (bytes == null || bytes.length == 0 || sha.isEmpty()) {
                AgentLog.info("textures: patch resource incomplete; texture patch disabled");
                return null;
            }
            AgentLog.info("textures: patch resource loaded, sourceSha256=" + sha
                    + ", bytes=" + bytes.length);
            return new TextureCacheTransformer(bytes, sha);
        } catch (Throwable t) {
            AgentLog.fail("textures: cannot load patch resource", t);
            return null;
        }
    }

    @Override
    public byte[] transform(ClassLoader loader, String className, Class<?> redefined,
                            ProtectionDomain protectionDomain, byte[] bytes) {
        if (!TARGET.equals(className) || bytes == null || redefined != null) return null;
        try {
            String actual = sha256(bytes);
            if (!expectedSha.equals(actual)) {
                if (mismatch.compareAndSet(false, true)) {
                    AgentLog.info("textures: TextureData sha mismatch, not patching (expected="
                            + expectedSha + ", actual=" + actual + ")");
                }
                return null;
            }
            if (applied.compareAndSet(false, true)) {
                AgentLog.info("textures: patched " + className
                        + " (shaderLib 1.12.1 lazy normal cache)");
            }
            return patched.clone();
        } catch (Throwable t) {
            AgentLog.fail("textures: transform failed", t);
            return null;
        }
    }

    static String sha256(byte[] data) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(data));
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    private static byte[] readAll(InputStream in) throws Exception {
        if (in == null) return null;
        try (InputStream src = in; ByteArrayOutputStream out = new ByteArrayOutputStream(96 * 1024)) {
            byte[] buf = new byte[8192];
            int n;
            while ((n = src.read(buf)) > 0) out.write(buf, 0, n);
            return out.toByteArray();
        }
    }
}
```

- [ ] **Step 5: 接线 `HypernovaAgent.java`**

在 `premain` 里 `AgentLog.info("hypernova agent premain...")` 之后、`ScriptCacheHook.setContext(ctx);` 之前插入：

```java
            try {
                TexturePatchConfig textures = TexturePatchConfig.load();
                if (textures.enabled()) {
                    TextureCacheTransformer transformer = TextureCacheTransformer.create();
                    if (transformer != null) {
                        instrumentation.addTransformer(transformer, false);
                        AgentLog.info("textures normal-cache transformer registered");
                    }
                } else {
                    AgentLog.info("textures normal-cache disabled by config");
                }
            } catch (Throwable t) {
                AgentLog.fail("textures normal-cache init failed; continuing", t);
            }
```

并在文件顶部加 import：

```java
import hypernova.agent.textures.TextureCacheTransformer;
import hypernova.agent.textures.TexturePatchConfig;
```

- [ ] **Step 6: 更新配置**

`data/config/hypernova/hypernova.json` 增加：

```json
  "textures": {
    "enabled": true
  }
```

放在 `"scripts"` 段之后（保持 JSON 合法）。同时把同一片段复制到**已安装**的
`Starsector-098-260mods/mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json`（controller 执行安装器或手工同步；实现者只改仓库源文件）。

- [ ] **Step 7: 跑 agent 测试**

Run: `bash tools/java/run-agent-tests.sh`

Expected: 36 原有 + Task 1 的 3 个 + 新增 7 个，全部 PASS。若 `TexturesWiringTest` 读 agent jar 时构建产物还没生成，先 `bash tools/java/build-agent.sh`（测试脚本已调用）。

- [ ] **Step 8: Commit**

```bash
git add src/agent/java/hypernova/agent/textures/TexturePatchConfig.java \
        src/agent/java/hypernova/agent/textures/TextureCacheTransformer.java \
        src/agent/java/hypernova/agent/HypernovaAgent.java \
        data/config/hypernova/hypernova.json \
        tests/agent/java/hypernova/agent/textures/TextureCacheTransformerTest.java \
        tests/agent/java/hypernova/agent/textures/TexturesWiringTest.java
git commit -m "feat(m1b): register a hash-guarded TextureData lazy-normal-cache transformer

The agent returns the precompiled patched class only when the loaded
TextureData class matches the pinned 1.12.1 SHA-256; otherwise it logs a
mismatch and leaves GraphicsLib untouched. Registration happens before the
scripts early-return so textures work even with scripts disabled.

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: M-1b 测量工具 + A/B 门禁

**Files:**
- Create: `tools/m1b_measure.py`
- Test: `tests/tools/test_m1b_measure.py`

**Interfaces:**
- Consumes: `starsector.log`、`<saves>/hypernova/scripts-agent.log`（agent 日志路径由 `smoke_run.py`/安装决定）。
- Produces:
  - `measure(log_path, agent_log=None, baseline=30378, threshold=0.2) -> dict`
  - CLI：`python tools/m1b_measure.py --log <log> [--agent-log <log>] [--baseline 30378] [--json-out <file>]`；门禁失败 exit 1。

- [ ] **Step 1: 写失败测试**

`tests/tools/test_m1b_measure.py`：

```python
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def write_log(path, normals_before, normals_after):
    lines = []
    t = 1000
    lines.append(f"{t} [main] INFO  com.genir.renderer.agent.Agent  - Fast Rendering: v0.9.5")
    for i in range(normals_before):
        t += 10
        lines.append(f"{t} [Thread-3] INFO  com.fs.graphics.TextureLoader  - Loading image [cache/x{i}_normal.png]")
    t += 1000
    lines.append(f"{t} [Thread-21] INFO  sound.H  - Playing music with id [miscallenous_main_menu.ogg]")
    for i in range(normals_after):
        t += 10
        lines.append(f"{t} [Thread-3] INFO  com.fs.graphics.TextureLoader  - Loading image [cache/y{i}_normal.png]")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_counts_only_before_menu_and_requires_patch(tmp_path):
    log = tmp_path / "starsector.log"
    agent = tmp_path / "agent.log"
    write_log(log, 10, 2)
    agent.write_text("2026-01-01T00:00:00Z INFO textures: patched org/dark/shaders/util/TextureData\n",
                     encoding="utf-8")
    out = tmp_path / "out.json"
    r = subprocess.run([sys.executable, str(ROOT / "tools/m1b_measure.py"),
                        "--log", str(log), "--agent-log", str(agent),
                        "--baseline", "100", "--json-out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["normal_before_menu"] == 10
    assert d["normal_after_menu"] == 2
    assert d["patched"] is True
    assert d["gate_ok"] is True


def test_gate_fails_without_patch(tmp_path):
    log = tmp_path / "starsector.log"
    write_log(log, 0, 0)
    r = subprocess.run([sys.executable, str(ROOT / "tools/m1b_measure.py"),
                        "--log", str(log), "--baseline", "100"],
                       capture_output=True, text=True)
    assert r.returncode == 1


def test_gate_fails_when_too_many_normals_before_menu(tmp_path):
    log = tmp_path / "starsector.log"
    agent = tmp_path / "agent.log"
    write_log(log, 60, 0)
    agent.write_text("textures: patched org/dark/shaders/util/TextureData\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "tools/m1b_measure.py"),
                        "--log", str(log), "--agent-log", str(agent),
                        "--baseline", "100"],
                       capture_output=True, text=True)
    assert r.returncode == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/tools/test_m1b_measure.py -q`

Expected: FAIL（脚本不存在）。

- [ ] **Step 3: 实现 `tools/m1b_measure.py`**

```python
#!/usr/bin/env python3
"""M-1b 门禁：统计主菜单前的 cache/*_normal.png 加载行，并验证 agent 补丁已生效。

门禁（出口标准）：主菜单前法线行数相对 baseline 下降 >= 80%，且 agent 日志出现
`textures: patched ...`。用法见文件末尾 argparse。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SESSION_ANCHOR = "Fast Rendering: v0.9.5"
MENU_ANCHOR = "Playing music with id [miscallenous_main_menu.ogg]"
TS = re.compile(r"^(\d+) ")
NORMAL = re.compile(
    r"^\d+ \[[^\]]+\] INFO  com\.fs\.graphics\.TextureLoader  - "
    r"Loading image \[cache/[^\]]*_normal\.png\]"
)


def _last_session(lines: list[str]) -> list[str]:
    starts = [i for i, line in enumerate(lines) if SESSION_ANCHOR in line]
    return lines[starts[-1]:] if starts else lines


def measure(log_path: str | Path, agent_log: str | Path | None = None,
            baseline: int = 30378, threshold: float = 0.2) -> dict:
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
        for line in Path(agent_log).read_text(encoding="utf-8", errors="replace").splitlines():
            if "textures: patched" in line:
                patched = True
                patch_line = line
            elif "textures: TextureData sha mismatch" in line and mismatch_line is None:
                mismatch_line = line

    drop = 1.0 - (before / baseline) if baseline > 0 else 0.0
    gate_ok = (
        menu_t is not None
        and patched
        and before <= max(50, int(baseline * threshold))
    )
    return {
        "menu_s": round(menu_t / 1000.0, 1) if menu_t is not None else None,
        "normal_before_menu": before,
        "normal_after_menu": after,
        "normal_window_s": (
            round((window[-1] - window[0]) / 1000.0, 1) if len(window) > 1 else 0.0
        ),
        "baseline": baseline,
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
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    result = measure(args.log, args.agent_log, args.baseline, args.threshold)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8", newline="\n")
    return 0 if result["gate_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/tools/test_m1b_measure.py -q`

Expected: 3 passed。

- [ ] **Step 5: 构建 agent 并安装到 260mods**

```bash
bash tools/java/build-agent.sh
python tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite --action install
```

（若安装器参数不同，按其 `--help` 调整；目标是让 `Miko_Lite.txt` 的
`-javaagent:...hypernova.agent.jar` 行指向新构建。）

同时把仓库的 `data/config/hypernova/hypernova.json` 同步到
`Starsector-098-260mods/mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json`。

- [ ] **Step 6: A/B 冒烟（controller 执行）**

```bash
# A: 补丁开（textures.enabled=true）
python tools/smoke_run.py --profile miko-lite --rounds 1 --linger 10 --json-out build/m1b-on.json
python tools/m1b_measure.py --log Starsector-098-260mods/starsector-core/starsector.log \
  --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
  --baseline 30378 --json-out build/m1b-on-measure.json

# B: 补丁关（临时把安装目录的 textures.enabled 改 false）
#   跑完恢复
python tools/smoke_run.py --profile miko-lite --rounds 1 --linger 10 --json-out build/m1b-off.json
python tools/m1b_measure.py --log Starsector-098-260mods/starsector-core/starsector.log \
  --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
  --baseline 30378 --json-out build/m1b-off-measure.json
```

Expected:
- A：`patched=true`，`normal_before_menu` ≤ 50（理想为 0；菜单背景的 ~12 张在菜单后才加载），`gate_ok=true`。
- B：`patched=false`，`normal_before_menu` ≈ 30,000，`gate_ok=false`。
- A 的主菜单时间比 B 少 **≥ 25 s**（法线桶 34–64 s 中的绝大部分），且 A 的菜单渲染正常（无黑块/花屏）。

若 A 的 `normal_before_menu` 仍 > 1,500：检查 agent 日志的 `patched`/`mismatch` 行与 `textures.enabled`；按 Escape Hatch 报告，不进入 Task 5。

- [ ] **Step 7: Commit**

```bash
git add tools/m1b_measure.py tests/tools/test_m1b_measure.py
git commit -m "feat(m1b): measure normal-map loads before the menu and gate on the patch

Parse the last Starsector session, count cache/*_normal.png loads before the
main-menu anchor, and require both a >=80% drop and the agent's texture patch
log line. This is the M-1b exit gate.

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5（可选，不进门禁）: DDS 离线烘焙工具

> 这条路线不参与 M-1b 的出口判定。它使用用户已有的 `DDSCreator.exe`，把 30,378 张法线图在**普通 mod 目录**下烘焙成 BC7 DDS，再由本工具改写成 `DDSCache/GraphicsLib/cache` 布局。由于 DDSCreator 是交互式 TUI，实际烘焙需要人工跑一次；本任务交付的是 staging / adopt / 校验工具和运行手册。

**Files:**
- Create: `tools/dds_normal_cache.py`
- Create: `tests/tools/test_dds_normal_cache.py`
- Create: `docs/m1b-dds-optional.md`

**Interfaces:**
- `python tools/dds_normal_cache.py prepare [--game <dir>] [--limit N] [--copy]`：创建 `mods/hypernova_dds_staging/graphics/normalcache/*.png`（默认硬链接）和 `mod_info.json`。
- `python tools/dds_normal_cache.py adopt [--game <dir>] [--dry-run]`：读取 `mods/DDSCache/hypernova_dds_staging/dds_metadata.json`，改写并合并到 `mods/DDSCache/GraphicsLib/dds_metadata.json`，把 DDS 放到 `mods/DDSCache/GraphicsLib/cache/`。
- `python tools/dds_normal_cache.py verify [--game <dir>]`：检查每个 metadata 的 DDS 存在、DX10/BC7 头、尺寸与 PNG 一致。

- [ ] **Step 1: 写失败测试**

`tests/tools/test_dds_normal_cache.py`：

```python
import json
import struct
from pathlib import Path

from dds_normal_cache import rewrite_entry, dds_info, png_size


def test_rewrite_entry_maps_staging_path_to_graphicslib_cache():
    entry = {
        "ModID": "hypernova_dds_staging",
        "ModFolderName": "hypernova_dds_staging",
        "RelativeImagePath": "graphics\\normalcache\\foo___SHIP_normal.png",
        "DDSFilePath": "\\mods\\DDSCache\\hypernova_dds_staging\\graphics\\normalcache\\foo___SHIP_normal.dds",
        "CompressionFormat": "BC7",
        "Width": 256,
        "Height": 128,
    }
    out = rewrite_entry(entry)
    assert out["ModFolderName"] == "GraphicsLib"
    assert out["RelativeImagePath"] == "cache\\foo___SHIP_normal.png"
    assert out["DDSFilePath"] == "\\mods\\DDSCache\\GraphicsLib\\cache\\foo___SHIP_normal.dds"
    assert out["CompressionFormat"] == "BC7"


def test_dds_info_rejects_non_bc7(tmp_path):
    p = tmp_path / "x.dds"
    data = bytearray(148)
    data[0:4] = b"DDS "
    struct.pack_into("<I", data, 4, 124)
    struct.pack_into("<I", data, 12, 64)    # height
    struct.pack_into("<I", data, 16, 128)   # width
    data[84:88] = b"DX10"
    struct.pack_into("<I", data, 128, 98)   # DXGI_FORMAT_BC7_UNORM
    p.write_bytes(data)
    info = dds_info(p)
    assert info["width"] == 128 and info["height"] == 64 and info["dxgiFormat"] == 98

    data[128:132] = struct.pack("<I", 71)   # BC1
    p.write_bytes(data)
    assert dds_info(p)["dxgiFormat"] == 71


def test_png_size_reads_ihdr(tmp_path):
    p = tmp_path / "x.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
                  + struct.pack(">II", 200, 100) + b"\x08\x06\x00\x00\x00")
    assert png_size(p) == (200, 100)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/tools/test_dds_normal_cache.py -q`

Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现 `tools/dds_normal_cache.py`**

```python
#!/usr/bin/env python3
"""可选 DDS 路线：用现成 DDSCreator 烘焙 GraphicsLib 法线缓存，再改写成 FR 能读的布局。

DDSCreator.exe 明确跳过 shaderLib 的 cache/ 和 graphics/shaders/。绕法：
把法线 PNG 硬链接到一个普通 mod 的 graphics/normalcache/ 下，让 DDSCreator
按普通 mod 烘焙；adopt 再把 metadata 的 ModFolderName/RelativeImagePath/
DDSFilePath 改回 GraphicsLib/cache，并把 DDS 放到 DDSCache/GraphicsLib/cache/。

不自动运行 DDSCreator（它是交互式 TUI）；prepare 打印手工步骤。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import sys
from pathlib import Path

STAGING = "hypernova_dds_staging"
NORMAL_SUBDIR = "graphics/normalcache"
BC7_DXGI = 98


def game_paths(game: Path) -> tuple[Path, Path]:
    mods = game / "mods"
    return mods / "GraphicsLib/cache", mods


def dds_info(path: Path) -> dict:
    data = path.read_bytes()[:148]
    if len(data) < 148 or data[0:4] != b"DDS ":
        raise ValueError(f"not a DDS file: {path}")
    height, width = struct.unpack_from("<II", data, 12)
    fourcc = data[84:88]
    dxgi = struct.unpack_from("<I", data, 128)[0] if fourcc == b"DX10" else None
    return {"width": width, "height": height, "fourcc": fourcc.decode("ascii", "replace"),
            "dxgiFormat": dxgi}


def png_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ValueError(f"not a PNG file: {path}")
    return struct.unpack(">II", head[16:24])


def rewrite_entry(entry: dict) -> dict:
    rel = entry["RelativeImagePath"].replace("/", "\\")
    name = rel.rsplit("\\", 1)[-1]
    if not name.endswith(".png"):
        raise ValueError(f"unexpected RelativeImagePath: {rel}")
    dds_name = name[:-4] + ".dds"
    out = dict(entry)
    out["ModID"] = "GraphicsLib"
    out["ModFolderName"] = "GraphicsLib"
    out["RelativeImagePath"] = "cache\\" + name
    out["DDSFilePath"] = "\\mods\\DDSCache\\GraphicsLib\\cache\\" + dds_name
    return out


def cmd_prepare(args) -> int:
    cache_dir, mods = game_paths(args.game)
    staging = mods / STAGING
    target = staging / NORMAL_SUBDIR
    if not cache_dir.is_dir():
        print(f"missing {cache_dir}", file=sys.stderr)
        return 2
    target.mkdir(parents=True, exist_ok=True)
    (staging / "mod_info.json").write_text(json.dumps({
        "id": STAGING, "name": "Hypernova DDS staging", "author": "Hypernova",
        "version": "0.1.0", "gameVersion": "0.98a-RC8",
        "description": "Temporary normal-map staging for DDSCreator.", "jars": [],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    pngs = sorted(cache_dir.glob("*_normal.png"))
    if args.limit:
        pngs = pngs[: args.limit]
    linked = copied = 0
    for src in pngs:
        dst = target / src.name
        if dst.exists():
            continue
        if args.copy:
            shutil.copy2(src, dst)
            copied += 1
        else:
            try:
                os.link(src, dst)
                linked += 1
            except OSError:
                shutil.copy2(src, dst)
                copied += 1
    print(f"staged {len(pngs)} PNGs ({linked} hardlinks, {copied} copies) -> {target}")
    print()
    print("下一步（人工）：")
    print("  1. 在 260mods 的 mod 列表里启用 hypernova_dds_staging（DDSCreator 只处理已启用 mod）。")
    print("  2. 运行 VramOptimizer/bin/DDSCreator.exe，选择 Process Mods，等它完成。")
    print("  3. 确认 mods/DDSCache/hypernova_dds_staging/dds_metadata.json 存在。")
    print("  4. 运行: python tools/dds_normal_cache.py adopt")
    print("  5. adopt 完成后禁用 staging mod；它只用于烘焙。")
    return 0


def cmd_adopt(args) -> int:
    cache_dir, mods = game_paths(args.game)
    staging_meta = mods / "DDSCache" / STAGING / "dds_metadata.json"
    if not staging_meta.is_file():
        print(f"missing {staging_meta}; run DDSCreator first", file=sys.stderr)
        return 2
    entries = json.loads(staging_meta.read_text(encoding="utf-8"))
    rewritten = []
    for entry in entries:
        rel = entry.get("RelativeImagePath", "")
        if not rel.replace("/", "\\").startswith("graphics\\normalcache\\"):
            continue
        out = rewrite_entry(entry)
        # 从原 entry 的 DDSFilePath 推导 staging 侧路径：
        # \mods\DDSCache\hypernova_dds_staging\graphics\normalcache\foo.dds
        src_dds = mods / "DDSCache" / STAGING / Path(
            entry["DDSFilePath"].split("\\" + STAGING + "\\", 1)[-1].replace("\\", "/"))
        dst_dds = cache_dir / out["DDSFilePath"].split("\\")[-1]
        if not src_dds.is_file():
            print(f"missing DDS {src_dds}", file=sys.stderr)
            return 2
        info = dds_info(src_dds)
        if info["dxgiFormat"] != BC7_DXGI:
            print(f"not BC7: {src_dds} ({info})", file=sys.stderr)
            return 2
        src_png = cache_dir / Path(out["RelativeImagePath"].replace("\\", "/")).name
        if src_png.is_file():
            w, h = png_size(src_png)
            if (w, h) != (info["width"], info["height"]):
                print(f"size mismatch {src_png}: png={w}x{h} dds={info['width']}x{info['height']}",
                      file=sys.stderr)
                return 2
        rewritten.append((src_dds, dst_dds, out))
    if not rewritten:
        print("no staging entries found; check DDSCreator skip rules", file=sys.stderr)
        return 2
    if args.dry_run:
        print(f"dry-run: would adopt {len(rewritten)} normals")
        for _, _, out in rewritten[:5]:
            print("  ", out["RelativeImagePath"], "->", out["DDSFilePath"])
        return 0
    cache_dir.mkdir(parents=True, exist_ok=True)
    (mods / "DDSCache/GraphicsLib").mkdir(parents=True, exist_ok=True)
    meta_path = mods / "DDSCache/GraphicsLib/dds_metadata.json"
    existing = []
    if meta_path.is_file():
        existing = [e for e in json.loads(meta_path.read_text(encoding="utf-8"))
                    if not e.get("RelativeImagePath", "").replace("/", "\\").startswith("cache\\")]
    for src, dst, _ in rewritten:
        if dst.exists():
            dst.unlink()
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)
    meta = existing + [out for _, _, out in rewritten]
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"adopted {len(rewritten)} normals -> {cache_dir} (metadata {meta_path})")
    print("现在禁用 hypernova_dds_staging，重启游戏。")
    return 0


def cmd_verify(args) -> int:
    _, mods = game_paths(args.game)
    meta_path = mods / "DDSCache/GraphicsLib/dds_metadata.json"
    if not meta_path.is_file():
        print(f"missing {meta_path}", file=sys.stderr)
        return 2
    entries = [e for e in json.loads(meta_path.read_text(encoding="utf-8"))
               if e.get("RelativeImagePath", "").replace("/", "\\").startswith("cache\\")]
    bad = 0
    for e in entries:
        dds = mods / "DDSCache/GraphicsLib" / Path(e["DDSFilePath"].split("GraphicsLib\\", 1)[-1].replace("\\", "/"))
        if not dds.is_file():
            bad += 1
            print("missing", dds, file=sys.stderr)
            continue
        info = dds_info(dds)
        if info["dxgiFormat"] != BC7_DXGI:
            bad += 1
            print("not BC7", dds, info, file=sys.stderr)
    print(f"verified {len(entries)} entries, {bad} bad")
    return 0 if bad == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="Starsector-098-260mods")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--copy", action="store_true")
    p.set_defaults(func=cmd_prepare)
    a = sub.add_parser("adopt")
    a.add_argument("--dry-run", action="store_true")
    a.set_defaults(func=cmd_adopt)
    v = sub.add_parser("verify")
    v.set_defaults(func=cmd_verify)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/tools/test_dds_normal_cache.py -q`

Expected: 3 passed。若 `tools` 不是包，测试脚本用 `from tools.dds_normal_cache import ...` 需要 `tools/__init__.py`；仓库已有 `tools/hn_json.py` 等被测试导入的方式——按现有 `conftest.py` 的 sys.path 约定处理，若失败则在测试里用 `import importlib.util` 加载，修正并报告。

- [ ] **Step 5: 小样本 dry-run**

```bash
python tools/dds_normal_cache.py prepare --limit 10
python tools/dds_normal_cache.py adopt --dry-run
```

Expected: staging 建好 10 个硬链接；adopt 在 DDSCreator 未跑时明确报 missing metadata（exit 2），不写任何文件。

- [ ] **Step 6: 写运行手册 `docs/m1b-dds-optional.md`**

手册必须包含：
- 为什么 DDSCreator 跳过 shaderLib，以及 staging 的绕法。
- 完整命令序列（prepare → 启用 staging → DDSCreator → adopt → 禁用 staging）。
- 产物布局与 FR 的 key 规则（`ModFolderName` + `RelativeImagePath`）。
- A/B 测量：`textures.enabled=false` + DDS 开，对比 `normal_before_menu` 与菜单时间；说明 DDS 只降低单张成本，不消除 3 万次纹理创建。
- 质量检查：进战斗看舰船/武器法线是否正常；BC7 有损，出现异常就回滚（删除 `DDSCache/GraphicsLib` 即可）。
- 回滚步骤：删除 `mods/DDSCache/GraphicsLib/cache/*.dds` 和对应 metadata 条目；或整目录备份还原。

- [ ] **Step 7: Commit**

```bash
git add tools/dds_normal_cache.py tests/tools/test_dds_normal_cache.py docs/m1b-dds-optional.md
git commit -m "feat(m1b): optional DDSCreator-assisted BC7 baking for normal maps

Stage normal PNGs under a normal-looking mod so DDSCreator's shaderLib skip
does not apply, then rewrite the metadata/layout into DDSCache/GraphicsLib
and verify DX10/BC7 headers and dimensions. Manual TUI step; not part of the
M-1b gate.

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: 最终验证 + 规格/文档

**Files:**
- Modify: `技术笔记-纹理按需加载.md` §7 M-1b
- Create: `docs/m1b-results.md`（实测表 + 门禁结论 + 战斗检查清单）

**Interfaces:**
- Consumes: Task 1–4 的产物与测量 JSON；Task 5 的手册。
- Produces: 规格里的 M-1b 最终状态、数字、回滚说明。

- [ ] **Step 1: 跑全量测试**

```bash
bash tools/java/run-agent-tests.sh
bash tools/java/run-tests.sh
python -m pytest tests/tools -q
```

Expected: agent 测试全绿（36 + 新增）；M1 测试全绿；pytest 全绿。若 `test_smoke_check.py` 的 2 条 M1 遗留失败仍在，记录为 deferred（不是本任务引入）。

- [ ] **Step 2: 最终 A/B 冒烟**

按 Task 4 Step 6 再跑一次 A/B，记录：
- `normal_before_menu`（patched / unpatched）
- `menu_s`（patched / unpatched）
- `patched` 日志行
- 法线窗口

写入 `docs/m1b-results.md`。

- [ ] **Step 3: 战斗内法线人工检查（用户执行）**

清单：
1. 用正常启动器（不是 launchDirect）启动 260mods，加载一个存档。
2. 进入一场包含多种舰船/武器的战斗。
3. 检查：舰船/武器有正常的光照层次，没有全黑、全亮、彩虹噪点或明显平面化。
4. 检查 `starsector.log`：战斗加载期间应出现 `Loading image [cache/..._normal.png]`（说明懒加载真的在工作），且不出现 `Failed to load texture`。
5. 截图留档；若异常，记录 mod/舰船名并回滚补丁（`textures.enabled=false`）。

- [ ] **Step 4: 更新规格 §7 M-1b**

把 `技术笔记-纹理按需加载.md` §7 的 M-1b 段改为：

- **状态**：完成（agent 路线）；DDS 路线为可选工具。
- **实测**：修复 M-1d oracle 后的基线；patched/unpatched 的 `normal_before_menu` 与菜单时间；法线窗口。
- **出口**：`cache/*_normal.png` 启动行数下降 ≥ 80%（实测值）；战斗内法线正常（人工检查日期/截图）。
- **上限**：即使全部消掉，首屏 ~56 s；M-1b 单独不足以达标 G-01。
- **回滚**：`textures.enabled=false` 或移除 agent 行。

- [ ] **Step 5: Commit**

```bash
git add 技术笔记-纹理按需加载.md docs/m1b-results.md
git commit -m "docs(m1b): record the lazy normal-cache results and optional DDS runbook

Update the milestone status, exit evidence, rollback, and the fact that M-1b
alone cannot reach the 40 s goal.

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Self-Review

### 1. Spec coverage

| 规格 | 任务 |
|---|---|
| §7 M-1b 目标：30,378 张法线图移出启动路径 | Task 3（懒加载） |
| §7 M-1b 候选①：扩展 DDSCache 到 GraphicsLib/cache | Task 5（可选） |
| §7 M-1b 候选②：shaderLib 只按需加载 | Task 3（agent 补丁） |
| §7 M-1b 出口：日志行数下降 ≥80% | Task 4（`m1b_measure.py` 门禁） |
| §7 M-1b 出口：战斗内法线正常 | Task 6（人工检查清单） |
| §7 上限 ~56 s | Task 4/6 实测记录 |
| §10.1 ADR-02：textures 模块由 agent 注册 | Task 3 注册顺序 + Task 3 wiring test |
| M-1d 回归：`hasSource` stat 风暴 | Task 1（addendum） |

### 2. Placeholder scan

- 无 TBD/TODO；所有新增文件都有完整代码或明确的命令。
- Task 5 的 DDSCreator 交互是外部人工步骤，已在运行手册中写明，不是代码占位。

### 3. Type consistency

- `SourceOracle.sourceCount()`：Task 1 定义，`ScriptCacheHook` 使用。
- `TextureCacheTransformer.TARGET` / `create()` / `sha256()` / 构造器：Task 3 的测试与接线一致。
- `TexturePatchConfig.load()` / `enabled()`：Task 3 一致。
- `measure()` / CLI 参数：Task 4 测试与实现一致。
- `rewrite_entry` / `dds_info` / `png_size`：Task 5 测试与实现一致。

### 4. Review Focus tests

1. 补丁类被父加载器提前加载 → `TexturesWiringTest.agentJarCarriesPatchResourceButNotTheClass`。
2. hash 不匹配仍替换 → `TextureCacheTransformerTest.rejectsDifferentBytes`。
3. 懒条目永远不被加载 → Task 6 人工战斗检查 + `TextureCacheTransformer` smoke。
4. `hasSource` 仍逐次 stat → `SourceOracleTest.hasSourceUsesSnapshotNotFilesystem`。
5. DDS 路径/尺寸错 → `test_rewrite_entry_*` + `adopt` 的 `png_size`/`dds_info` 校验。

### 5. Proportion

计划包含完整代码，因为 SDD 的 implementer 是转录工；关键决策（补丁边界、O(1) 索引、资源名、门禁阈值）都在正文里，不是靠实现者猜。

---

## Execution Handoff

本计划按 **pipeline** 执行。Task 1 必须先过 A/B 冒烟（菜单 ≤150 s，回收 ≥35 s）才进入 Task 2；Task 4 的 A/B 是 M-1b 出口门禁；Task 5 可选、不阻塞 Task 6。每个任务独立 commit，审查输入为 brief + report + diff。
