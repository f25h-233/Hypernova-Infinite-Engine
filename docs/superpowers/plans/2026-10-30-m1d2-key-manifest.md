# M-1d-2 缓存 key 清单化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把缓存 key 的文件枚举从「每次 4 次属性读取/文件」压成「一次 `walkFileTree` + `BasicFileAttributes`」，并把热启动 `cache key` 中位数从 **7,606 ms**（15 次实测）降到 **< 1,000 ms**。

**Architecture:** 新增 `KeyScanner`：用 `Files.walkFileTree` 单次枚举拿到每个候选文件的 `path/size/mtime`，按 mod 源根并行（默认 4 线程，可关）；`KeyManifest.refresh` 新增接收已读属性的重载，直接复用清单里的 sha256，不再二次 stat；清单无变化时跳过 3.3 MB 的 JSON 重写。key 的 canonical 形式（`java/classpath/enabled` + `path|size|sha256`）**逐字不变**，因此未变更安装的 key id 必须保持 `6646f5b6…`。

**Tech Stack:** Java 17（`--release 17`，class major 61）、`java.nio.file`（`Files.walkFileTree` / `BasicFileAttributes`）、JUnit 5、Bash（Git Bash）、`org.json`（游戏自带 `json.jar`）；测量用 Base 的 JRE 17 + `tools/smoke_run.py`（Miko Lite，JDK 28）。

**Spec:** `技术笔记-纹理按需加载.md` §7「M-1d-2 缓存 key 清单化」。计划是论证，冲突时按规格裁决并记入 ledger。

## 开工前实测（2026-10-30，controller 亲测，写进 ledger）

### A. 生产算法的分项基准（真实 260mods 文件树，12,308 个文件，热 OS 缓存）

方法：`build/keybench/KeyBench.java`（一次性基准，未入库）直接调用生产类，`cacheRoot` 指向真实 `key-manifest.json` 的**临时副本**，不写真实缓存。系统 Java 21，5 轮取中位数。

| 阶段 | 中位数 | 说明 |
|---|---:|---|
| `KeyManifest.load` | 88 ms | 3.3 MB / 12,330 条，游戏自带 org.json |
| `collectFiles` | **2,155 ms** | 主因：`Files.walk` + `isRegularFile` + `addFile` 的重复 stat |
| 2×stat（`size`+`getLastModifiedTime`） | 1,141 ms | 12,308 个文件 |
| 单次 `readAttributes` | **443 ms** | 同样 12,308 个文件，比 2×stat 快 2.6× |
| `KeyManifest.refresh` | 937 ms | 含上述 2×stat，哈希复用本身可忽略 |
| canonical 排序 + SHA-256 | 14 ms | 可忽略 |
| `manifest.save` | 75 ms | 3.3 MB JSON |
| **旧总耗时** | **3,220 ms** | load+collect+refresh+canonical+save |
| **新扫描（串行）** | **412 ms** | `walkFileTree` + attrs 单次枚举 |
| **新扫描（4 线程）** | **172 ms** | 按 mod 源根并行 |
| **新扫描（8 线程）** | **165 ms** | 4→8 无收益，取 4 |
| 新流水线（串行，估算） | **≈508 ms** | scan + 哈希复用 + canonical + save |
| 新流水线（4 线程，估算） | **≈268 ms** | 同上，换并行 scan |

等价性：新扫描与旧 `collectFiles` 的路径集合 `onlyOld=0`；`onlyNew=1` 是 `hypernova.agent.jar`（基准的 `walkTree` 未排除，**生产实现必须排除**，见 Task 1 测试）。

### B. 游戏内真实分布（旧实现，`scripts-agent.log`，同一天 15 次启动）

| 统计 | 值 |
|---|---:|
| 次数 | 15 |
| 中位数 | **7,606 ms** |
| 最小 / 最大 | 3,336 / 14,402 ms |
| `preload` 等待 | 6–12 ms（背景 key 在 preload 前已完成） |

游戏内是基准的 1.0–4.5 倍（与游戏初始化抢 CPU/磁盘、OS 缓存冷热有关）。据此：

- **串行**预计落到 0.5–2.3 s，**4 线程**预计 0.27–1.2 s。
- 目标定为 **热启动 key 中位数 < 1,000 ms**（spec 允许「做完批属性/并行后按 <1000 ms 验收」）；**回归硬线 3,000 ms**。若实测中位数落在 1,000–3,000 ms，**如实记录，不得宣称 <1 s**，由 controller 裁决是否继续。
- 不采用「目录 mtime 跳过未变目录」：NTFS 上改文件内容不改父目录 mtime，仍须逐文件读属性；而串行逐文件 `readAttributes`（443 ms）并不比 `walkFileTree`（412 ms）快，持久化目录清单只会多一个真值来源，没有收益。此决策写进 `docs/m1d2-results.md`。

## Global Constraints

- Java 编译必须 `--release 17`；产物 class major version 必须是 61（`build-agent.sh` 已有门禁）。
- agent 是**可选件**：缺失、配置关闭、FR 缺失、异常 → 只禁用对应模块，游戏必须照常启动；所有钩子 `catch (Throwable)`，绝不外抛。
- **canonical 格式冻结**：头部 `java=` / `classpath=` / `enabled=` 三行 + `path|size|sha256`，**不含 mtime**。未变更安装的 key id 必须保持 `6646f5b6…`。
- **racy-clean 语义保留**：`mtime >= savedAt` 的文件必须重算 sha256；`-Dhypernova.rehash=true` 强制全部重算。
- 文件集合语义与旧 `collectFiles` **逐字等价**：mods 根下所有含 `mod_info.json` 的直接子目录；每个 mod 的 `src/`、`jars/`、`data/scripts/` 递归，加 `mod_info.json`、mod 根级 `*.jar`；`starsector-core/data/scripts`；`enabled_mods.json`；`fr.agent.jar`、`fr.jar`；classpath 中位于 `gameRoot` 下的 jar。排除 `hypernova.agent.jar`。不解析 `mod_info.json`。
- 不新增第三方依赖；不改 `src/main/java/hypernova/**`（M1 textures 模块冻结）；不改 key/pack/store 的存储格式。
- 除 Task 3 的显式冒烟外，测试不得启动游戏；不得执行 `taskkill //F //IM node.exe`。
- 每个任务一个独立 commit；消息前缀 `feat(m1d2):` / `test(m1d2):` / `docs(m1d2):`，并附 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。
- 本计划按 **pipeline** 执行（ledger 首部记录 `Mode: pipeline`）。

## Escape Hatch

- 若计划里的断言数字、测试顺序、文件路径或方法描述符与实际实现不符 → **按实际修正并报告**（写进 `task-N-report.md`），无需请示。
- 若需求自相矛盾或无法同时满足 → **停下报告 controller，不许挑一半照做**。写清矛盾原文、为什么不能同时成立、建议裁决。
- Pipeline 下只改本任务 `Touches:` 声明内的文件；需要越界 → 停下报告，等 controller 裁决。
- 若 Task 3 的 3 次热启动中位数 **≥ 1,000 ms 且 < 3,000 ms**：如实报告，不得改口径；可再用 `-Dhypernova.keyThreads=1` 跑 3 次对照（串行 vs 并行），选实测更优者并记录。若中位数 **≥ 3,000 ms**：停，不宣称达标，附日志与分项。
- 若新扫描的文件数与旧 `collectFiles` 在真实安装上不一致（超过 `hypernova.agent.jar` 这一个已知差异）→ 停，报告差异路径，不得放行。

## Review Focus

1. **文件集合漂移**：`hypernova.agent.jar` 出现在 mod 的 `jars/` 里、目录名以 `.jar` 结尾、大小写扩展名（`.JAVA`）、符号链接到文件、没有 `mod_info.json` 的目录——新扫描必须和旧 `Files.walk` 语义一致（含/不含都要一致）。Task 1 的 `KeyScannerTest.scanFindsExactlyTheLegacyFileSet` + `symlinkToFileFollowsLegacySemantics`。
2. **旧哈希复用掩盖内容修改**：同尺寸、mtime 被改回旧值且 `mtime < savedAt` 时，缓存会复用旧 sha256（spec 已知限制）。`-Dhypernova.rehash=true` 必须能强制全部重算。Task 2 的 `rehashPropertyForcesContentRecheck`。
3. **并行扫描丢文件/重复**：线程池中途异常或被中断时不得漏文件；并行与串行必须得到同一集合。Task 1 的 `parallelAndSerialProduceSameSet`。
4. **跳过清单写入破坏 racy-clean**：无变化时跳过 3.3 MB 重写；但新增/删除/重算过哈希时必须写，否则 `savedAt` 停滞会让后续每次重启都重算。Task 2 的 `unchangedInputsDoNotRewriteManifest` + `refreshMarksDirtyOnlyWhenSomethingChanged`。
5. **清单损坏/扫描后文件消失**：半截 JSON → 全量重算；`refresh` 遇到已删除文件必须跳过条目而不是抛异常。现有 `KeyManifest.load` 的 rebuild 路径 + Task 2 的 `refreshSkipsFileThatVanishedAfterScan`。

## File Structure

| 路径 | 责任 | 任务 |
|---|---|---|
| `src/agent/java/hypernova/agent/KeyScanner.java` | 单次 `walkFileTree` + `BasicFileAttributes` 枚举；可选按源根并行 | 1 |
| `src/agent/java/hypernova/agent/ScriptCacheKey.java` | `classpathOrder` 改包内可见（供 scanner 复用）；`collectFiles` 委托 scanner | 1/2 |
| `tests/agent/java/hypernova/agent/KeyScannerTest.java` | 与旧算法的等价性、attrs、并行、symlink | 1 |
| `src/agent/java/hypernova/agent/KeyManifest.java` | `refresh(List<FileInfo>, boolean)`；`dirty`/`saveNeeded()`；`-Dhypernova.rehash` 由调用方传入 | 2 |
| `src/agent/java/hypernova/agent/ScriptCacheKey.java` | `compute` 接新扫描 + 分项日志 + 无变化跳写 | 2 |
| `tests/agent/java/hypernova/agent/ScriptCacheKeyTest.java` | rehash 开关、跳写 | 2 |
| `tests/agent/java/hypernova/agent/KeyManifestRefreshTest.java` | 文件消失、dirty 语义、force | 2 |
| `tools/java/keybench/KeyBench.java` | 真实安装的分项基准（可重复） | 3 |
| `tools/java/key-bench.sh` | 构建并跑 KeyBench（串行/4 线程各一轮） | 3 |
| `docs/m1d2-results.md` | 基线/新测/门禁/回滚/已知限制 | 3 |
| `技术笔记-纹理按需加载.md` §7 M-1d-2 | 状态与实测回写 | 3 |

---

### Task 1: `KeyScanner` — 单次属性枚举 + 可选并行

**Files:**
- Create: `src/agent/java/hypernova/agent/KeyScanner.java`
- Modify: `src/agent/java/hypernova/agent/ScriptCacheKey.java`（只把 `private static List<String> classpathOrder(RuntimeContext)` 改成包内可见 `static`；不改行为）
- Test: `tests/agent/java/hypernova/agent/KeyScannerTest.java`

**Interfaces:**
- Consumes: `RuntimeContext.modsRoot()`、`RuntimeContext.gameRoot()`；`ScriptCacheKey.classpathOrder(RuntimeContext) -> List<String>`；`AgentLog.fail(String, Throwable)`。
- Produces:
  - `KeyScanner.FileInfo`：`record FileInfo(Path path, long size, long mtimeMillis)`
  - `KeyScanner.scan(RuntimeContext) -> List<FileInfo>`（包内可见；按 `path.toString()` 升序、去重）
  - `KeyScanner.threads() -> int`（读 `-Dhypernova.keyThreads`，未设置/非法时 `min(4, max(1, availableProcessors))`）

**Touches:** `src/agent/java/hypernova/agent/KeyScanner.java`、`src/agent/java/hypernova/agent/ScriptCacheKey.java`、`tests/agent/java/hypernova/agent/KeyScannerTest.java`

- [ ] **Step 1: 写失败测试**

创建 `tests/agent/java/hypernova/agent/KeyScannerTest.java`：

```java
package hypernova.agent;

import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.Locale;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.*;

/**
 * KeyScanner 的语义锚点：它必须与旧的 collectFiles（Files.walk + 逐文件 stat）
 * 找到**完全相同**的文件集合，同时只做一次属性读取。
 */
class KeyScannerTest {
    @TempDir Path tmp;

    @Test
    void scanFindsExactlyTheLegacyFileSet() throws Exception {
        Path game = tmp.resolve("game");
        Path mods = game.resolve("mods");

        Path a = mods.resolve("modA");
        Files.createDirectories(a.resolve("src/x/y"));
        Files.createDirectories(a.resolve("jars/sub"));
        Files.createDirectories(a.resolve("data/scripts/z"));
        Files.writeString(a.resolve("mod_info.json"), "{\"id\":\"a\"}");
        Files.writeString(a.resolve("src/x/A.java"), "class A {}");
        Files.writeString(a.resolve("src/x/y/B.JAVA"), "class B {}");
        Files.writeString(a.resolve("src/x/notes.txt"), "ignore");
        Files.write(a.resolve("jars/a.jar"), new byte[]{1});
        Files.write(a.resolve("jars/sub/nested.jar"), new byte[]{2});
        Files.write(a.resolve("jars/hypernova.agent.jar"), new byte[]{3});
        Files.write(a.resolve("root.jar"), new byte[]{4});
        Files.writeString(a.resolve("data/scripts/z/S.java"), "class S {}");
        // 目录名以 .jar 结尾：旧实现只收普通文件，必须排除。
        Files.createDirectories(a.resolve("dir.jar"));

        // 没有 mod_info.json 的目录：整棵跳过。
        Path b = mods.resolve("modB");
        Files.createDirectories(b.resolve("src"));
        Files.writeString(b.resolve("src/No.java"), "class No {}");

        // 与 mods/ 同级的副本目录：不在扫描范围内。
        Path sibling = game.resolve("mods - copy/m");
        Files.createDirectories(sibling.resolve("src"));
        Files.writeString(sibling.resolve("mod_info.json"), "{}");
        Files.writeString(sibling.resolve("src/Copy.java"), "class Copy {}");

        Files.createDirectories(game.resolve("starsector-core/data/scripts/core"));
        Files.writeString(game.resolve("starsector-core/data/scripts/core/Core.java"),
                "class Core {}");
        Files.write(game.resolve("starsector-core/fr.agent.jar"), new byte[]{5});
        Files.write(game.resolve("starsector-core/fr.jar"), new byte[]{6});
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[]}");

        RuntimeContext ctx = ctx(game, mods);
        Set<String> legacy = legacyCollect(ctx);
        Set<String> scanned = paths(KeyScanner.scan(ctx));

        assertEquals(legacy, scanned, "new scanner must reproduce the legacy file set exactly");
        assertFalse(scanned.stream().anyMatch(p -> p.endsWith("hypernova.agent.jar")));
        assertFalse(scanned.stream().anyMatch(p -> p.endsWith("dir.jar")));
        assertFalse(scanned.stream().anyMatch(p -> p.endsWith("No.java")));
        assertFalse(scanned.stream().anyMatch(p -> p.endsWith("Copy.java")));
        assertFalse(scanned.stream().anyMatch(p -> p.endsWith("notes.txt")));
        assertTrue(scanned.stream().anyMatch(p -> p.endsWith("B.JAVA")));
        assertTrue(scanned.stream().anyMatch(p -> p.endsWith("nested.jar")));
        assertTrue(scanned.stream().anyMatch(p -> p.endsWith("root.jar")));
    }

    @Test
    void scanCarriesSizeAndMtime() throws Exception {
        Path game = tmp.resolve("game2");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("m");
        Files.createDirectories(mod.resolve("src"));
        Files.writeString(mod.resolve("mod_info.json"), "{\"id\":\"m\"}");
        Path f = mod.resolve("src/F.java");
        Files.writeString(f, "class F {}");
        long mtime = 1_700_000_000_123L;
        Files.setLastModifiedTime(f, FileTime.fromMillis(mtime));
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[]}");

        KeyScanner.FileInfo info = KeyScanner.scan(ctx(game, mods)).stream()
                .filter(i -> i.path().equals(f.toAbsolutePath().normalize()))
                .findFirst().orElseThrow();

        assertEquals(Files.size(f), info.size());
        assertEquals(mtime, info.mtimeMillis());
    }

    @Test
    void parallelAndSerialProduceSameSet() throws Exception {
        Path game = tmp.resolve("game3");
        Path mods = game.resolve("mods");
        for (int m = 0; m < 12; m++) {
            Path mod = mods.resolve("m" + m);
            Files.createDirectories(mod.resolve("src/a"));
            Files.writeString(mod.resolve("mod_info.json"), "{\"id\":\"m" + m + "\"}");
            Files.writeString(mod.resolve("src/a/C" + m + ".java"), "class C" + m + " {}");
        }
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[]}");
        RuntimeContext ctx = ctx(game, mods);

        String old = System.getProperty("hypernova.keyThreads");
        try {
            System.setProperty("hypernova.keyThreads", "1");
            Set<String> serial = paths(KeyScanner.scan(ctx));
            System.setProperty("hypernova.keyThreads", "4");
            Set<String> parallel = paths(KeyScanner.scan(ctx));
            assertEquals(serial, parallel, "parallel scan must not add or drop files");
        } finally {
            if (old == null) System.clearProperty("hypernova.keyThreads");
            else System.setProperty("hypernova.keyThreads", old);
        }
    }

    @Test
    void symlinkToFileFollowsLegacySemantics() throws Exception {
        Path game = tmp.resolve("game4");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("m");
        Files.createDirectories(mod.resolve("src"));
        Files.writeString(mod.resolve("mod_info.json"), "{\"id\":\"m\"}");
        Path target = mod.resolve("src/Real.java");
        Files.writeString(target, "class Real {}");
        Path link = mod.resolve("src/Link.java");
        try {
            Files.createSymbolicLink(link, target);
        } catch (IOException | UnsupportedOperationException e) {
            Assumptions.assumeTrue(false, "symlinks unsupported here: " + e);
        }
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[]}");
        RuntimeContext ctx = ctx(game, mods);

        Set<String> legacy = legacyCollect(ctx);
        Set<String> scanned = paths(KeyScanner.scan(ctx));
        assertEquals(legacy, scanned,
                "a symlink to a regular file was fingerprinted by the legacy walk; keep it");
    }

    private Set<String> paths(java.util.List<KeyScanner.FileInfo> files) {
        Set<String> out = new TreeSet<>();
        for (KeyScanner.FileInfo f : files) out.add(f.path().toString());
        return out;
    }

    /** 旧 collectFiles 的逐字复刻，仅作为测试预言机；生产已不再走这条路径。 */
    private Set<String> legacyCollect(RuntimeContext ctx) throws IOException {
        Set<Path> files = new TreeSet<>();
        Path mods = ctx.modsRoot();
        if (Files.isDirectory(mods)) {
            try (DirectoryStream<Path> ds = Files.newDirectoryStream(mods)) {
                for (Path dir : ds) {
                    if (!Files.isDirectory(dir)) continue;
                    if (!Files.isRegularFile(dir.resolve("mod_info.json"))) continue;
                    legacyTree(dir.resolve("src"), files);
                    legacyTree(dir.resolve("jars"), files);
                    legacyTree(dir.resolve("data/scripts"), files);
                    legacyFile(dir.resolve("mod_info.json"), files);
                    try (DirectoryStream<Path> jars = Files.newDirectoryStream(dir)) {
                        for (Path p : jars) {
                            if (p.getFileName().toString().toLowerCase(Locale.ROOT)
                                    .endsWith(".jar")) {
                                legacyFile(p, files);
                            }
                        }
                    }
                }
            }
        }
        legacyFile(mods.resolve("enabled_mods.json"), files);
        legacyTree(ctx.gameRoot().resolve("starsector-core/data/scripts"), files);
        legacyFile(ctx.gameRoot().resolve("starsector-core/fr.agent.jar"), files);
        legacyFile(ctx.gameRoot().resolve("starsector-core/fr.jar"), files);
        for (String cp : ScriptCacheKey.classpathOrder(ctx)) legacyFile(Path.of(cp), files);

        Set<String> out = new TreeSet<>();
        for (Path p : files) out.add(p.toString());
        return out;
    }

    private void legacyTree(Path root, Set<Path> out) throws IOException {
        if (!Files.isDirectory(root)) return;
        try (Stream<Path> s = Files.walk(root)) {
            for (java.util.Iterator<Path> it = s.iterator(); it.hasNext(); ) {
                Path p = it.next();
                if (!Files.isRegularFile(p)) continue;
                String n = p.getFileName().toString().toLowerCase(Locale.ROOT);
                if (n.endsWith(".java") || n.endsWith(".jar") || n.equals("mod_info.json")) {
                    legacyFile(p, out);
                }
            }
        }
    }

    private void legacyFile(Path p, Set<Path> out) {
        if (p == null || !Files.isRegularFile(p)) return;
        if (p.getFileName().toString().equals("hypernova.agent.jar")) return;
        out.add(p.toAbsolutePath().normalize());
    }

    private RuntimeContext ctx(Path game, Path mods) {
        Path saves = tmp.resolve("saves-" + Math.abs(game.hashCode()));
        ScriptCacheConfig cfg = new ScriptCacheConfig(true, 1L << 20, 2, 3000, false);
        return new RuntimeContext(game, mods, saves, saves.resolve("cache"),
                saves.resolve("agent.log"), saves.resolve("telemetry.jsonl"), cfg);
    }
}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash tools/java/run-agent-tests.sh KeyScannerTest`

Expected: 编译失败，`找不到符号: 类 KeyScanner`。

- [ ] **Step 3: 实现 `KeyScanner`**

创建 `src/agent/java/hypernova/agent/KeyScanner.java`：

```java
package hypernova.agent;

import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/**
 * 缓存 key 的文件枚举器。
 *
 * <p>旧实现每个文件要读多次属性：{@code Files.walk} 递归时一次、{@code Files.isRegularFile}
 * 过滤一次、{@code Files.size} 与 {@code Files.getLastModifiedTime} 各一次。这里改成
 * {@link Files#walkFileTree} + {@link BasicFileAttributes}：枚举一次就拿到 path/size/mtime，
 * 后续 {@link KeyManifest#refresh} 直接复用，不再 stat。
 *
 * <p>260mods 实测（热 OS 缓存、12,308 个文件）：collect 2,155 ms + refresh 937 ms →
 * scan 412 ms（串行）/ 172 ms（4 线程）。
 *
 * <p>行为必须与旧 {@code ScriptCacheKey.collectFiles} 逐字等价；等价性由
 * {@code KeyScannerTest} 对着一份旧算法复刻来守护。
 */
public final class KeyScanner {
    /** 一个进入指纹的文件；mtime 用毫秒，与 {@link KeyManifest.Entry} 一致。 */
    public record FileInfo(Path path, long size, long mtimeMillis) {
    }

    private KeyScanner() {
    }

    static List<FileInfo> scan(RuntimeContext ctx) {
        Map<String, FileInfo> out = new TreeMap<>();
        List<Path> roots = new ArrayList<>();
        List<Path> singles = new ArrayList<>();

        // 方案 B：mods 根下所有含 mod_info.json 的直接子目录都进指纹，不解析 JSON。
        Path mods = ctx.modsRoot();
        if (Files.isDirectory(mods)) {
            try (DirectoryStream<Path> ds = Files.newDirectoryStream(mods)) {
                for (Path dir : ds) {
                    if (!Files.isDirectory(dir)) continue;
                    Path info = dir.resolve("mod_info.json");
                    if (!Files.isRegularFile(info)) continue;
                    roots.add(dir.resolve("src"));
                    roots.add(dir.resolve("jars"));
                    roots.add(dir.resolve("data/scripts"));
                    singles.add(info);
                    try (DirectoryStream<Path> jars = Files.newDirectoryStream(dir)) {
                        for (Path p : jars) {
                            if (p.getFileName().toString().toLowerCase(Locale.ROOT)
                                    .endsWith(".jar")) {
                                singles.add(p);
                            }
                        }
                    } catch (IOException e) {
                        AgentLog.fail("mod jar scan failed: " + dir, e);
                    }
                }
            } catch (IOException e) {
                AgentLog.fail("mod scan failed", e);
            }
        }
        singles.add(mods.resolve("enabled_mods.json"));
        roots.add(ctx.gameRoot().resolve("starsector-core/data/scripts"));
        singles.add(ctx.gameRoot().resolve("starsector-core/fr.agent.jar"));
        singles.add(ctx.gameRoot().resolve("starsector-core/fr.jar"));
        for (String cp : ScriptCacheKey.classpathOrder(ctx)) singles.add(Path.of(cp));

        walkAll(roots, out, threads());
        for (Path p : singles) addFile(p, out);
        return new ArrayList<>(out.values());
    }

    /** {@code -Dhypernova.keyThreads=N}；未设置或非法值 → auto。1 = 串行。 */
    static int threads() {
        String v = System.getProperty("hypernova.keyThreads", "");
        if (!v.isBlank()) {
            try {
                int n = Integer.parseInt(v.trim());
                if (n > 0) return Math.min(32, n);
            } catch (NumberFormatException ignored) {
                // 非法值退回 auto
            }
        }
        return Math.min(4, Math.max(1, Runtime.getRuntime().availableProcessors()));
    }

    private static void walkAll(List<Path> roots, Map<String, FileInfo> out, int threads) {
        if (threads <= 1 || roots.size() <= 1) {
            for (Path r : roots) walkTree(r, out);
            return;
        }
        ExecutorService pool = Executors.newFixedThreadPool(threads, r -> {
            Thread t = new Thread(r, "Hypernova-KeyScan");
            t.setDaemon(true);
            return t;
        });
        boolean interrupted = false;
        try {
            List<Callable<Map<String, FileInfo>>> tasks = new ArrayList<>(roots.size());
            for (Path root : roots) {
                tasks.add(() -> {
                    Map<String, FileInfo> local = new TreeMap<>();
                    walkTree(root, local);
                    return local;
                });
            }
            for (Future<Map<String, FileInfo>> f : pool.invokeAll(tasks)) {
                try {
                    out.putAll(f.get());
                } catch (ExecutionException e) {
                    AgentLog.fail("key scan task failed", e.getCause());
                }
            }
        } catch (InterruptedException e) {
            interrupted = true;
            Thread.currentThread().interrupt();
        } finally {
            pool.shutdownNow();
        }
        if (interrupted) {
            // 被中断时 invokeAll 可能只跑了一部分；串行补全，绝不漏文件。
            for (Path r : roots) walkTree(r, out);
        }
    }

    private static void walkTree(Path root, Map<String, FileInfo> out) {
        if (!Files.isDirectory(root)) return;
        try {
            Files.walkFileTree(root, new SimpleFileVisitor<>() {
                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                    if (isFingerprintFile(file, attrs)) add(file, attrs, out);
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFileFailed(Path file, IOException exc) {
                    // 与旧 Files.walk 不同：单个子树不可读时继续扫兄弟节点（更安全方向：
                    // 宁可多收，不可漏收；漏收会让缓存带毒）。
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException e) {
            AgentLog.fail("walk failed: " + root, e);
        }
    }

    private static boolean isFingerprintFile(Path file, BasicFileAttributes attrs) {
        String name = file.getFileName().toString();
        if (name.equals("hypernova.agent.jar")) return false;
        String lower = name.toLowerCase(Locale.ROOT);
        if (!(lower.endsWith(".java") || lower.endsWith(".jar")
                || lower.equals("mod_info.json"))) {
            return false;
        }
        // walkFileTree 默认不跟随链接；旧 Files.isRegularFile 会跟随。补上这一差异，
        // 让「指向普通文件的符号链接」仍进指纹。
        return attrs.isRegularFile()
                || (attrs.isSymbolicLink() && Files.isRegularFile(file));
    }

    private static void add(Path file, BasicFileAttributes attrs, Map<String, FileInfo> out) {
        long size = attrs.size();
        long mtime = attrs.lastModifiedTime().toMillis();
        if (attrs.isSymbolicLink()) {
            // 链接本身的大小/时间不是旧实现看到的；旧实现跟随链接，这里也跟随。
            try {
                size = Files.size(file);
                mtime = Files.getLastModifiedTime(file).toMillis();
            } catch (IOException e) {
                return;
            }
        }
        Path abs = file.toAbsolutePath().normalize();
        out.put(abs.toString(), new FileInfo(abs, size, mtime));
    }

    private static void addFile(Path p, Map<String, FileInfo> out) {
        if (p == null) return;
        try {
            // readAttributes 默认跟随链接，与旧 Files.isRegularFile 语义一致。
            BasicFileAttributes attrs = Files.readAttributes(p, BasicFileAttributes.class);
            if (!attrs.isRegularFile()) return;
            if (p.getFileName().toString().equals("hypernova.agent.jar")) return;
            add(p, attrs, out);
        } catch (IOException ignored) {
            // 不存在/不可读：旧 Files.isRegularFile 同样返回 false
        }
    }
}
```

同时把 `ScriptCacheKey.classpathOrder` 的可见性从 `private static` 改为包内可见 `static`（方法体不动）。

- [ ] **Step 4: 跑测试确认通过**

Run: `bash tools/java/run-agent-tests.sh KeyScannerTest`

Expected: `KeyScannerTest` 4 个测试通过（symlink 在不支持的环境会 skip，不算失败）。再跑一次全量确认无回归：`bash tools/java/run-agent-tests.sh` → 现有 53 个 + 新增 4 个全绿。

- [ ] **Step 5: Commit**

```bash
git add src/agent/java/hypernova/agent/KeyScanner.java src/agent/java/hypernova/agent/ScriptCacheKey.java tests/agent/java/hypernova/agent/KeyScannerTest.java
git commit -m "feat(m1d2): scan key inputs in one attribute pass

Replace the per-file double-stat walk with Files.walkFileTree plus
BasicFileAttributes, optionally parallelised across mod roots. The file
set is pinned to the legacy collectFiles semantics by an equivalence test.

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: 接线 `ScriptCacheKey` / `KeyManifest`（复用属性、rehash 开关、跳写、分项日志）

**Files:**
- Modify: `src/agent/java/hypernova/agent/KeyManifest.java`（新增重载 + dirty/saveNeeded）
- Modify: `src/agent/java/hypernova/agent/ScriptCacheKey.java`（`compute` 与 `collectFiles`）
- Test: `tests/agent/java/hypernova/agent/ScriptCacheKeyTest.java`（追加 2 条）
- Test: `tests/agent/java/hypernova/agent/KeyManifestRefreshTest.java`（新建 3 条）

**Interfaces:**
- Consumes: `KeyScanner.FileInfo`、`KeyScanner.scan(RuntimeContext)`（Task 1）。
- Produces:
  - `KeyManifest.refresh(List<KeyScanner.FileInfo> files, boolean forceRehash) -> List<Entry>`
  - `KeyManifest.saveNeeded() -> boolean`
  - `ScriptCacheKey.compute(RuntimeContext) -> Result`（签名与 `Result` 记录不变；`elapsedMillis` 仍是总耗时）
  - 日志行 `cache key breakdown: files=..., scan=... ms, load=... ms, refresh=... ms, canonical=... ms, save=... ms, total=... ms, rehash=...`

**Touches:** `src/agent/java/hypernova/agent/KeyManifest.java`、`src/agent/java/hypernova/agent/ScriptCacheKey.java`、`tests/agent/java/hypernova/agent/ScriptCacheKeyTest.java`、`tests/agent/java/hypernova/agent/KeyManifestRefreshTest.java`

- [ ] **Step 1: 写失败测试（KeyManifest 层）**

创建 `tests/agent/java/hypernova/agent/KeyManifestRefreshTest.java`：

```java
package hypernova.agent;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class KeyManifestRefreshTest {
    @TempDir Path tmp;

    @Test
    void refreshSkipsFileThatVanishedAfterScan() throws Exception {
        Path f = tmp.resolve("gone.java");
        Files.writeString(f, "class Gone {}");
        KeyManifest m = KeyManifest.load(tmp.resolve("manifest.json"));
        Files.delete(f);

        List<KeyManifest.Entry> entries = m.refresh(
                List.of(new KeyScanner.FileInfo(f, 10L, 1L)), false);

        assertTrue(entries.isEmpty(), "a file deleted between scan and hash must be skipped");
    }

    @Test
    void refreshIsCleanWhenAttributesMatchAndNotRacy() throws Exception {
        Path f = tmp.resolve("a.java");
        Files.writeString(f, "class A {}");
        FileTime past = FileTime.fromMillis(System.currentTimeMillis() - 60_000L);
        Files.setLastModifiedTime(f, past);
        Path mf = tmp.resolve("manifest.json");
        KeyScanner.FileInfo info = new KeyScanner.FileInfo(f, Files.size(f), past.toMillis());

        KeyManifest first = KeyManifest.load(mf);
        first.refresh(List.of(info), false);
        assertTrue(first.saveNeeded(), "a new file must make the manifest dirty");
        first.save(mf);

        KeyManifest reloaded = KeyManifest.load(mf);
        reloaded.refresh(List.of(info), false);
        assertFalse(reloaded.saveNeeded(),
                "unchanged inputs below savedAt must reuse the hash and skip the rewrite");
    }

    @Test
    void forceRehashAlwaysMarksDirty() throws Exception {
        Path f = tmp.resolve("b.java");
        Files.writeString(f, "class B {}");
        FileTime past = FileTime.fromMillis(System.currentTimeMillis() - 60_000L);
        Files.setLastModifiedTime(f, past);
        Path mf = tmp.resolve("manifest2.json");
        KeyScanner.FileInfo info = new KeyScanner.FileInfo(f, Files.size(f), past.toMillis());

        KeyManifest first = KeyManifest.load(mf);
        first.refresh(List.of(info), false);
        first.save(mf);

        KeyManifest reloaded = KeyManifest.load(mf);
        reloaded.refresh(List.of(info), true);
        assertTrue(reloaded.saveNeeded(),
                "-Dhypernova.rehash=true must not take the reuse fast path");
    }
}
```

- [ ] **Step 2: 写失败测试（key 层）**

在 `tests/agent/java/hypernova/agent/ScriptCacheKeyTest.java` 末尾（`private RuntimeContext ctx(...)` 之前）追加：

```java
    /**
     * 已知限制：size+mtime 都没变、且 mtime < savedAt 时，缓存会复用旧 sha256。
     * 这是 R5 为了性能接受的窗口；-Dhypernova.rehash=true 必须能强制重算。
     */
    @Test
    void rehashPropertyForcesContentRecheck() throws Exception {
        Path game = tmp.resolve("gameRehash");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("foo");
        Files.createDirectories(mod.resolve("src/a"));
        Files.writeString(mod.resolve("mod_info.json"), "{\"id\":\"foo\"}");
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[\"foo\"]}");
        Path java = mod.resolve("src/a/R.java");
        Files.writeString(java, "package a; public class R {int x;}");
        RuntimeContext ctx = ctx(game, mods);
        String k1 = ScriptCacheKey.compute(ctx).id();

        // 把清单 savedAt 推到未来，让 size+mtime 未变的文件走哈希复用路径。
        Path manifest = ctx.cacheRoot().resolve("key-manifest.json");
        JSONObject root = new JSONObject(Files.readString(manifest));
        root.put("savedAt", System.currentTimeMillis() + 3_600_000L);
        Files.writeString(manifest, root.toString());

        FileTime mtime = Files.getLastModifiedTime(java);
        Files.writeString(java, "package a; public class R {int y;}"); // 同尺寸
        Files.setLastModifiedTime(java, mtime);

        assertEquals(k1, ScriptCacheKey.compute(ctx).id(),
                "same size+mtime must reuse the cached sha256 without the rehash flag");

        System.setProperty("hypernova.rehash", "true");
        try {
            assertNotEquals(k1, ScriptCacheKey.compute(ctx).id(),
                    "-Dhypernova.rehash=true must re-hash every file");
        } finally {
            System.clearProperty("hypernova.rehash");
        }
    }

    /** 无变化时不得重写 3.3 MB 的清单（每次启动都写是纯浪费）。 */
    @Test
    void unchangedInputsDoNotRewriteManifest() throws Exception {
        Path game = tmp.resolve("gameNoWrite");
        Path mods = game.resolve("mods");
        Path mod = mods.resolve("foo");
        Files.createDirectories(mod.resolve("src/a"));
        Files.writeString(mod.resolve("mod_info.json"), "{\"id\":\"foo\"}");
        Files.writeString(mods.resolve("enabled_mods.json"), "{\"enabledMods\":[\"foo\"]}");
        Path java = mod.resolve("src/a/W.java");
        Files.writeString(java, "package a; public class W {}");
        // 把源文件 mtime 固定到过去，保证第一次 compute 的 savedAt 严格大于它。
        FileTime past = FileTime.fromMillis(System.currentTimeMillis() - 60_000L);
        Files.setLastModifiedTime(java, past);
        Files.setLastModifiedTime(mod.resolve("mod_info.json"), past);
        Files.setLastModifiedTime(mods.resolve("enabled_mods.json"), past);

        RuntimeContext ctx = ctx(game, mods);
        ScriptCacheKey.compute(ctx);
        Path manifest = ctx.cacheRoot().resolve("key-manifest.json");
        FileTime firstWrite = Files.getLastModifiedTime(manifest);

        Thread.sleep(50);
        ScriptCacheKey.compute(ctx);

        assertEquals(firstWrite, Files.getLastModifiedTime(manifest),
                "a no-op refresh must not rewrite the manifest");
    }
```

- [ ] **Step 3: 跑测试确认失败**

Run: `bash tools/java/run-agent-tests.sh ScriptCacheKeyTest`

Expected: 编译失败——`KeyManifest.refresh(List<KeyScanner.FileInfo>, boolean)` 与 `saveNeeded()` 不存在。

- [ ] **Step 4: 实现 `KeyManifest` 重载与 dirty**

在 `KeyManifest` 字段区加：

```java
    /** 本次 refresh 是否产生了需要落盘的差异（新文件/删除/重算哈希）。 */
    private boolean dirty;
```

在 `refresh(List<Path> files)` 之后新增：

```java
    /**
     * 用 {@link KeyScanner.FileInfo} 里已经读到的 size/mtime 刷新清单，不再重复 stat。
     *
     * <p>复用条件与旧实现一致：清单里有同 path、同 size、同 mtime，且
     * {@code mtime < savedAt}（git 式 racy-clean；清单写完之后才改过的文件不可信）。
     * {@code forceRehash=true} 时无条件重算（{@code -Dhypernova.rehash=true}）。
     *
     * <p>任何一次「没有走复用」都置 {@link #dirty}：即使哈希恰好没变，也要把新的
     * mtime 落盘，否则下次启动还会再算一遍。删除文件（条目数变化）同样置 dirty。
     */
    public List<Entry> refresh(List<KeyScanner.FileInfo> files, boolean forceRehash) {
        int previousSize = byPath.size();
        List<Entry> out = new ArrayList<>(files.size());
        for (KeyScanner.FileInfo f : files) {
            String path = f.path().toString();
            long size = f.size();
            long mtime = f.mtimeMillis();
            Entry prev = byPath.get(path);
            String hash;
            if (!forceRehash && prev != null && prev.size() == size && prev.mtime() == mtime
                    && mtime < savedAt) {
                hash = prev.sha256();
            } else {
                dirty = true;
                try {
                    hash = sha256(f.path());
                } catch (IOException e) {
                    AgentLog.fail("stat/hash failed: " + path, e);
                    continue;
                }
            }
            out.add(new Entry(path, size, mtime, hash));
        }
        if (out.size() != previousSize) dirty = true;
        byPath.clear();
        for (Entry e : out) byPath.put(e.path(), e);
        return out;
    }

    /** 清单是否需要重写：有差异，或从未成功写过（savedAt=0 / 文件缺失）。 */
    public boolean saveNeeded() {
        return dirty || savedAt == 0L;
    }
```

并在 `save(Path file)` 末尾（`savedAt = now;` 之后）加 `dirty = false;`。

同时让旧的 `refresh(List<Path>)` 在重算哈希的 `else` 分支里也置 `dirty = true`、结尾按条目数变化置 dirty（否则两条路径的 dirty 语义不一致，测试会漂移）：

```java
                String hash = (prev != null && prev.size() == size && prev.mtime() == mtime
                        && mtime < savedAt)
                        ? prev.sha256() : sha256(p);
```
改为：

```java
                String hash;
                if (prev != null && prev.size() == size && prev.mtime() == mtime
                        && mtime < savedAt) {
                    hash = prev.sha256();
                } else {
                    dirty = true;
                    hash = sha256(p);
                }
```

并在该方法 `byPath.clear();` 之前加：

```java
        if (out.size() != oldSize) dirty = true;
```
（在方法开头记录 `int oldSize = byPath.size();`。）

- [ ] **Step 5: 实现 `ScriptCacheKey.compute` 接线**

把 `compute` 全文替换为：

```java
    public static Result compute(RuntimeContext ctx) {
        long t0 = System.nanoTime();

        long t = System.nanoTime();
        List<KeyScanner.FileInfo> files = KeyScanner.scan(ctx);
        long scanMs = millis(t);

        t = System.nanoTime();
        Path manifestFile = ctx.cacheRoot().resolve("key-manifest.json");
        KeyManifest manifest = KeyManifest.load(manifestFile);
        long loadMs = millis(t);

        t = System.nanoTime();
        boolean forceRehash = Boolean.getBoolean("hypernova.rehash");
        List<KeyManifest.Entry> entries = manifest.refresh(files, forceRehash);
        long refreshMs = millis(t);

        t = System.nanoTime();
        List<String> classpathOrder = classpathOrder(ctx);
        StringBuilder sb = new StringBuilder(1 << 20);
        sb.append("java=").append(System.getProperty("java.version", "")).append('\n');
        sb.append("classpath=").append(String.join(File.pathSeparator, classpathOrder)).append('\n');
        // 启用清单进 canonical：enabledMods 的「集合」变化会改变 classpath 装载/编译优先级
        // 与游戏实际加载的 mod（ModManager.loadEnabledModList 按 id 匹配）。
        // 这里排序后写入，所以【本行】只表达集合、不表达顺序；但【整体 key】对顺序仍敏感：
        // enabled_mods.json 自身的字节 sha256 在下面的文件清单里，顺序一变该文件的 sha256
        // 就变，key 随之变（顺序确实影响 classpath 优先级，必须敏感）。实测见 R12 报告。
        sb.append("enabled=").append(String.join(",", enabledIds(ctx.modsRoot()))).append('\n');
        List<KeyManifest.Entry> sorted = new ArrayList<>(entries);
        sorted.sort(Comparator.comparing(KeyManifest.Entry::path));
        for (KeyManifest.Entry e : sorted) {
            // 只写 path|size|sha256，不写 mtime：sha256 已完整覆盖内容，mtime 进 canonical
            // 只会额外制造 miss —— git checkout / 解压 / 备份还原 / 复制粘贴等「内容不变、
            // 时间变」的操作都会让整份缓存失效，代价是一次完整冷编译。
            // mtime 仍保留在 KeyManifest 内部，仅用于 size+mtime 短路省重算 sha 的性能
            // （由 racy-clean 守卫兜底），该决策不传播到 key 本身。
            sb.append(e.path()).append('|').append(e.size()).append('|')
                    .append(e.sha256()).append('\n');
        }
        String canonical = sb.toString();
        String id = sha256(canonical.getBytes(StandardCharsets.UTF_8)).substring(0, 32);
        long canonicalMs = millis(t);

        t = System.nanoTime();
        if (manifest.saveNeeded()) {
            try {
                manifest.save(manifestFile);
            } catch (IOException e) {
                AgentLog.fail("key manifest save failed", e);
            }
        }
        long saveMs = millis(t);

        long bytes = entries.stream().mapToLong(KeyManifest.Entry::size).sum();
        long totalMs = millis(t0);
        AgentLog.info("cache key breakdown: files=" + entries.size()
                + ", scan=" + scanMs + " ms, load=" + loadMs + " ms, refresh=" + refreshMs
                + " ms, canonical=" + canonicalMs + " ms, save=" + saveMs + " ms, total="
                + totalMs + " ms, rehash=" + forceRehash);
        return new Result(id, canonical, entries.size(), bytes, totalMs);
    }

    private static long millis(long startNanos) {
        return (System.nanoTime() - startNanos) / 1_000_000;
    }
```

把 `collectFiles` 换成委托（保留给测试与 `--verify` 的调用形态）：

```java
    static List<Path> collectFiles(RuntimeContext ctx) {
        List<Path> out = new ArrayList<>();
        for (KeyScanner.FileInfo f : KeyScanner.scan(ctx)) out.add(f.path());
        return out;
    }
```

删除不再使用的 `addTree`、`addFile`、`scanModFolders` 三个私有方法（若 `addFile` 仍被别处引用则保留；当前只有 `collectFiles` 用）。`scanModFolders` 的注释（方案 B 的理由）移到 `KeyScanner.scan` 的对应位置（Task 1 的代码已带该注释）。

- [ ] **Step 6: 跑测试确认通过**

Run: `bash tools/java/run-agent-tests.sh`

Expected: 全绿（53 个既有 + Task 1 的 4 个 + Task 2 的 5 个）。若 `unchangedInputsDoNotRewriteManifest` 因文件系统时间戳粒度失败，按实际把 `Thread.sleep(50)` 调大到 1,100 ms，并在报告中记录。

- [ ] **Step 7: Commit**

```bash
git add src/agent/java/hypernova/agent/KeyManifest.java src/agent/java/hypernova/agent/ScriptCacheKey.java tests/agent/java/hypernova/agent/ScriptCacheKeyTest.java tests/agent/java/hypernova/agent/KeyManifestRefreshTest.java
git commit -m "feat(m1d2): reuse scanned attributes in the key manifest

The manifest refresh now takes the size/mtime already read by KeyScanner
instead of stat-ing every file again. Add the -Dhypernova.rehash=true
escape hatch, skip the 3.3 MB manifest rewrite when nothing changed, and
log a per-stage breakdown of the key computation.

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 真实安装基准 + 3 次热启动 + 规格回写

**Files:**
- Create: `tools/java/keybench/KeyBench.java`
- Create: `tools/java/key-bench.sh`
- Create: `docs/m1d2-results.md`
- Modify: `技术笔记-纹理按需加载.md` §7「M-1d-2」

**Interfaces:**
- Consumes: `KeyScanner.scan`、`KeyManifest.refresh(List<KeyScanner.FileInfo>, boolean)`、`KeyManifest.saveNeeded()`、`ScriptCacheKey.compute`（Task 1/2）；`tools/smoke_run.py --profile miko-lite`、`tools/install_agent.py`（既有）。
- Produces: 可复现的分项基准脚本；`docs/m1d2-results.md` 的实测表与门禁结论；§7 的 M-1d-2 最终状态。

**Touches:** `tools/java/keybench/KeyBench.java`、`tools/java/key-bench.sh`、`docs/m1d2-results.md`、`技术笔记-纹理按需加载.md`

- [ ] **Step 1: 写基准工具**

创建 `tools/java/keybench/KeyBench.java`：

```java
package hypernova.agent;

import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;

/**
 * 真实安装上的 key 分项基准。用法：
 *   KeyBench &lt;gameRoot&gt; &lt;modsRoot&gt; &lt;cacheRoot&gt; [iterations]
 *
 * <p>cacheRoot 必须是**清单的临时副本目录**，不能指向真实 scripts-cache：
 * 本工具会写 key-manifest.json。等价性与正确性由 KeyScannerTest/KeyManifestRefreshTest
 * 负责；这里只测真实 12k 文件树的阶段耗时。
 */
public final class KeyBench {
    private KeyBench() {
    }

    public static void main(String[] args) throws Exception {
        Path game = Path.of(args[0]).toAbsolutePath().normalize();
        Path mods = Path.of(args[1]).toAbsolutePath().normalize();
        Path cache = Path.of(args[2]).toAbsolutePath().normalize();
        int iters = args.length > 3 ? Integer.parseInt(args[3]) : 5;
        Path manifestFile = cache.resolve("key-manifest.json");

        ScriptCacheConfig cfg = new ScriptCacheConfig(true, 1L << 20, 2, 3000, false);
        RuntimeContext ctx = new RuntimeContext(game, mods, game.resolve("saves"), cache,
                cache.resolve("agent.log"), cache.resolve("telemetry.jsonl"), cfg);

        long[] scan = new long[iters], load = new long[iters], refresh = new long[iters],
                canon = new long[iters], save = new long[iters], total = new long[iters];
        String key = "";
        int fileCount = 0;

        for (int i = 0; i < iters; i++) {
            long t = System.nanoTime();
            List<KeyScanner.FileInfo> files = KeyScanner.scan(ctx);
            scan[i] = ms(t);

            t = System.nanoTime();
            KeyManifest manifest = KeyManifest.load(manifestFile);
            load[i] = ms(t);

            t = System.nanoTime();
            List<KeyManifest.Entry> entries = manifest.refresh(files, false);
            refresh[i] = ms(t);

            t = System.nanoTime();
            List<KeyManifest.Entry> sorted = new ArrayList<>(entries);
            sorted.sort(Comparator.comparing(KeyManifest.Entry::path));
            StringBuilder sb = new StringBuilder(1 << 20);
            for (KeyManifest.Entry e : sorted) {
                sb.append(e.path()).append('|').append(e.size()).append('|')
                        .append(e.sha256()).append('\n');
            }
            key = sha256(sb.toString()).substring(0, 32);
            canon[i] = ms(t);

            t = System.nanoTime();
            if (manifest.saveNeeded()) manifest.save(manifestFile);
            save[i] = ms(t);

            fileCount = entries.size();
            total[i] = scan[i] + load[i] + refresh[i] + canon[i] + save[i];
            System.out.printf(Locale.ROOT,
                    "iter %d: files=%d key=%s scan=%d load=%d refresh=%d canon=%d save=%d total=%d%n",
                    i, fileCount, key, scan[i], load[i], refresh[i], canon[i], save[i], total[i]);
        }
        System.out.println("median: files=" + fileCount + " key=" + key
                + " scan=" + med(scan) + " load=" + med(load) + " refresh=" + med(refresh)
                + " canon=" + med(canon) + " save=" + med(save) + " total=" + med(total));
    }

    private static long ms(long t0) {
        return (System.nanoTime() - t0) / 1_000_000;
    }

    private static long med(long[] v) {
        long[] c = v.clone();
        Arrays.sort(c);
        return c[c.length / 2];
    }

    private static String sha256(String s) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                .digest(s.getBytes(java.nio.charset.StandardCharsets.UTF_8)));
    }
}
```

创建 `tools/java/key-bench.sh`：

```bash
#!/usr/bin/env bash
# 用法: bash tools/java/key-bench.sh [游戏根目录]
# 在真实安装的文件树上跑 key 分项基准；manifest 用临时副本，不写真实缓存。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi; }
ROOT_W="$(winpath "$ROOT")"
GAME="$(winpath "${1:-$ROOT/Starsector-098-260mods}")"
CORE="$ROOT_W/Starsector-098-Base/starsector-core"
JAVA="$ROOT_W/Starsector-098-Base/jre/bin/java.exe"
test -x "$JAVA" || { echo "FATAL: Base JRE not found: $JAVA" >&2; exit 1; }

bash "$ROOT_W/tools/java/build-agent.sh" >/dev/null
OUT="$ROOT_W/build/keybench"
rm -rf "$OUT/classes"
mkdir -p "$OUT/classes"
javac --release 17 -encoding UTF-8 \
  -cp "$ROOT_W/build/agent/classes;$CORE/json.jar" \
  -d "$OUT/classes" "$ROOT_W/tools/java/keybench/KeyBench.java"

TMP="$(winpath "$(mktemp -d)")"
cp "$GAME/saves/hypernova/scripts-cache/key-manifest.json" "$TMP/" 2>/dev/null || true
CP="$ROOT_W/build/agent/classes;$CORE/json.jar;$OUT/classes"

echo "== threads=4 (auto) =="
"$JAVA" -Dhypernova.keyThreads=4 -cp "$CP" hypernova.agent.KeyBench "$GAME" "$GAME/mods" "$TMP" 5
echo "== threads=1 =="
"$JAVA" -Dhypernova.keyThreads=1 -cp "$CP" hypernova.agent.KeyBench "$GAME" "$GAME/mods" "$TMP" 5
rm -rf "$TMP"
```

- [ ] **Step 2: 跑基准并记录**

```bash
bash tools/java/key-bench.sh
```

Expected（热 OS 缓存，与开工前实测同量级）：
- `threads=4`：`total` 中位数 **≤ 400 ms**；
- `threads=1`：`total` 中位数 **≤ 800 ms**；
- `files=12308`（或当前真实值）、`key` 与 `scripts-agent.log` 里的 key 一致（若 classpath 差异导致不同，记录原因：基准的 java.class.path 不含游戏 jar）。

把输出原样贴进 `docs/m1d2-results.md`。若 `total` 明显高于上述预期，先检查是否冷缓存（重跑一次）再继续。

- [ ] **Step 3: 全量测试**

```bash
bash tools/java/run-agent-tests.sh
bash tools/java/run-tests.sh
python -m pytest tests/tools -q
```

Expected：agent 全绿；M1 95/95；pytest 全绿。若 `test_smoke_check.py` 的 2 条 M-1d 遗留失败仍在，记录为 deferred（不是本任务引入）。

- [ ] **Step 4: 构建并安装到三档**

```bash
bash tools/java/build-agent.sh
python tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite --jar build/agent/hypernova.agent.jar
python tools/install_agent.py --game Starsector-098-260mods --env 260mods-simple --jar build/agent/hypernova.agent.jar
python tools/install_agent.py --game Starsector-098-Base --env base --jar build/agent/hypernova.agent.jar
```

Expected：三次都成功；`Miko_Lite.txt` 仍是 LF，agent 行在 `-javaagent:fr.agent.jar` **之前**。

- [ ] **Step 5: 3 次热启动**

```bash
python tools/smoke_run.py --profile miko-lite --rounds 3 --json-out build/m1d2-key.json
```

Expected：3 轮都到主菜单（每轮 80–130 s）；无崩溃；`build/m1d2-key.json` 生成。**跑之前确认内存 ≥20 GB 空闲，不要同时跑其他重进程。**

- [ ] **Step 6: 提取门禁数据**

```bash
python - <<'EOF'
import re
p = r'Starsector-098-260mods/saves/hypernova/scripts-agent.log'
take = re.findall(r'cache key ready \(background\): ([0-9a-f]+), took (\d+) ms', open(p, encoding='utf-8', errors='replace').read())
bd = re.findall(r'cache key breakdown: files=(\d+), scan=(\d+) ms, load=(\d+) ms, refresh=(\d+) ms, canonical=(\d+) ms, save=(\d+) ms, total=(\d+) ms, rehash=(\w+)', open(p, encoding='utf-8', errors='replace').read())
pre = re.findall(r'scripts cache preloaded: key=([0-9a-f]+), entries=(\d+), bytes=(\d+), in (\d+) ms', open(p, encoding='utf-8', errors='replace').read())
print('key runs (last 3):', take[-3:])
print('breakdown (last 3):', bd[-3:])
print('preload (last 3):', pre[-3:])
EOF
```

Expected：
- 最后 3 条 key 的 `took` **中位数 < 1000 ms**（目标）；若在 1000–3000 ms 之间，如实记录并走 Escape Hatch；
- 3 条 key id 相同，且等于安装前日志里的 key（未变更安装 key id 不变）；
- `preloaded entries=2113`；`rehash=false`；
- `breakdown` 的 `scan` 明显小于旧 `collectFiles` 的 2,155 ms。

- [ ] **Step 7: 写 `docs/m1d2-results.md`**

必须包含：

1. **结论**：门禁通过/不通过（按 Step 6 的实测数字，不按期望值）。
2. **环境**：260mods、Miko Lite（JDK 28）、Lite 内存档、日期。
3. **旧基线**：15 次分布（中位数 7,606 ms，范围 3,336–14,402 ms），注明来自同一天同一安装的 `scripts-agent.log`。
4. **新实测**：3 次 `took` + `breakdown` 三阶段 + `preload` + key id。
5. **分项基准**：`key-bench.sh` 的 threads=4 / threads=1 两段原始输出。
6. **门禁判定**：中位数 <1,000 ms → 通过；1,000–3,000 ms → 记录但标注「未达 <1 s 目标」；>3,000 ms → 不通过。
7. **顺带观察**：主菜单时间（3 轮）与 85.5 s 基线对比（不作为本里程碑门禁）。
8. **回滚/开关**：
   - `-Dhypernova.keyThreads=1` → 串行扫描（加在启动参数文件主类行之前，保持 LF）；
   - `-Dhypernova.rehash=true` → 强制全量重算 sha256；
   - 删除 `saves/hypernova/scripts-cache/key-manifest.json` → 下次全量重建。
9. **已知限制**：size+mtime 均未变的内容修改会复用旧哈希（rehash 兜底）；未采用目录 mtime 剪枝及原因；`KEY_AWAIT_MILLIS=8s` 超时后同步重算的路径仍在，但新 key 已在 8 s 内完成（记录实测最大值）。

- [ ] **Step 8: 回写规格 §7 M-1d-2**

把 `技术笔记-纹理按需加载.md` 的 M-1d-2 段改为（数字按 Step 6 实测填）：

```markdown
### M-1d-2 缓存 key 清单化（已完成，2026-10-30）

- **状态**：完成。`KeyScanner` 用 `Files.walkFileTree` + `BasicFileAttributes` 单次枚举
  取 path/size/mtime（按 mod 源根并行，默认 4 线程，`-Dhypernova.keyThreads=1` 关闭）；
  `KeyManifest.refresh` 复用已读属性与清单里的 sha256；清单无变化时不重写。
- **实测**：开工前 15 次热启动 key 耗时中位数 **7,606 ms**（3,336–14,402 ms）；
  改造后 3 次中位数 **<填实测> ms**，`scan=<填>`、`load=<填>`、`refresh=<填>`、
  `canonical=<填>`、`save=<填>`。真实安装分项基准（热缓存、4 线程）total **<填> ms**。
- **出口**：中位数 <1,000 ms（目标）/ <3,000 ms（硬线）；未变更安装 key id 保持
  `<填>`；`preload entries=2,113`；A/B 多轮见 `docs/m1d2-results.md`。
- **回滚**：`-Dhypernova.keyThreads=1`（串行）、`-Dhypernova.rehash=true`（强制全哈希）、
  删除 `saves/hypernova/scripts-cache/key-manifest.json`（全量重建）。
- **已知限制**：size+mtime 均未变的内容修改会复用旧 sha256（spec 风险，rehash 兜底）；
  目录 mtime 不能检测内容修改，故未用于剪枝；`KEY_AWAIT_MILLIS=8 s` 超时后的同步重算
  路径保留，但实测新 key 最大值 <填> ms，不会触发。
```

- [ ] **Step 9: Commit**

```bash
git add tools/java/keybench/KeyBench.java tools/java/key-bench.sh docs/m1d2-results.md 技术笔记-纹理按需加载.md
git commit -m "docs(m1d2): measure the key scan on the real install

Record the pre/post key-computation distribution, the staged benchmark,
the unchanged key id, rollback switches, and the documented limitation
around size+mtime reuse.

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Self-Review

### 1. Spec coverage

| 规格（§7 M-1d-2） | 任务 |
|---|---|
| 先测 `walkFileTree + BasicFileAttributes` 单次枚举成本 | 开工前实测 A + Task 3 Step 2 |
| 串行 size+mtime 实测约 3.1 s，目标不写死 <1 s | 开工前实测 A（3,220 ms）；目标 <1,000 ms 且硬线 3,000 ms |
| 按 mod root 并行（4–8 线程） | Task 1 `KeyScanner.walkAll`，默认 4 |
| manifest 持久化文件清单；变化目录才重扫 | **不采用**，理由与实测写入 `docs/m1d2-results.md`（NTFS 目录 mtime 不能检测内容修改；逐文件 attrs 更便宜） |
| 保留 racy-clean（`mtime < savedAt`） | Task 2 `refresh(FileInfo, boolean)` 复用条件；`KeyManifestRefreshTest` |
| `-Dhypernova.rehash=true` 强制全量 | Task 2 实现 + `rehashPropertyForcesContentRecheck` |
| 内容变更不能只靠目录 mtime | `docs/m1d2-results.md` 已知限制；Task 1/2 注释 |
| 连续 3 次热启动记录 `took` 分布 | Task 3 Step 5/6 |
| 未变更安装 key id 不变 | Task 3 Step 6 断言 + `docs/m1d2-results.md` |
| 测试覆盖新增/删除/改内容/改回旧 mtime/force | Task 1 等价性（新增/删除通过集合比较）；Task 2 `rehashPropertyForcesContentRecheck`（改内容+改回 mtime）、`refreshSkipsFileThatVanishedAfterScan`（删除）、`forceRehashAlwaysMarksDirty`（force） |
| manifest 损坏 → 全量重扫 | 既有 `KeyManifest.load` rebuild 路径；`KeyManifestVerifyTest` 已覆盖，不重复 |
| A/B 多轮中位数 | Task 3 Step 5/6（旧 15 次分布 vs 新 3 次；同一安装、同一天） |

### 2. Placeholder scan

- 无 TBD/TODO；Task 3 的 `docs/m1d2-results.md` 与 §7 里的 `<填>` 是**要求填实测值**的占位，不是未决设计；Step 6 给出了提取命令与判定阈值。
- 所有新增类都有完整代码；修改点给出了方法级完整替换代码。

### 3. Type consistency

- `KeyScanner.FileInfo(Path, long, long)`：Task 1 定义；Task 2 `refresh(List<FileInfo>, boolean)`、Task 3 KeyBench 使用一致。
- `KeyManifest.saveNeeded()`：Task 2 定义；Task 3 KeyBench 使用一致。
- `ScriptCacheKey.classpathOrder`：Task 1 改包内可见；Task 1 测试的 `legacyCollect` 与 `KeyScanner.scan` 使用一致。
- `KeyScanner.threads()`：只被 `scan` 调用；测试通过系统属性驱动，不直接调用。
- `ScriptCacheKey.Result`：记录未改，`CacheTool`/测试无需调整。

### 4. Review Focus tests

1. 文件集合漂移 → `KeyScannerTest.scanFindsExactlyTheLegacyFileSet`、`symlinkToFileFollowsLegacySemantics`。
2. 旧哈希复用 → `ScriptCacheKeyTest.rehashPropertyForcesContentRecheck`。
3. 并行丢/重 → `KeyScannerTest.parallelAndSerialProduceSameSet`。
4. 跳写破坏 racy-clean → `ScriptCacheKeyTest.unchangedInputsDoNotRewriteManifest`、`KeyManifestRefreshTest.refreshIsCleanWhenAttributesMatchAndNotRacy`。
5. 清单损坏/文件消失 → `KeyManifestRefreshTest.refreshSkipsFileThatVanishedAfterScan` + 既有 rebuild 测试。

### 5. Proportion

计划的关键决策（单次枚举、并行默认值、canonical 冻结、跳写条件、门禁阈值）都来自开工前实测；代码块只覆盖新增/替换的方法，不复述未改动的类。

---

## Execution Handoff

本计划按 **pipeline** 执行。Task 1 先过全量 agent 测试才进入 Task 2；Task 2 的 key 级测试必须证明「无变化不写清单」与「rehash 能强制重算」；Task 3 的 3 次热启动是里程碑出口门禁，数字必须来自日志而非期望值。每个任务独立 commit，审查输入为 brief + report + diff。
