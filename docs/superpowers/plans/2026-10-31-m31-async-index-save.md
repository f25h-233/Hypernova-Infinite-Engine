# M3.1 索引 save 异步化 + 空叶子目录硬化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 file index 的首次/重建写盘从 `DirectoryCrawler.cacheLocations()` 的启动关键路径移到 daemon 写盘线程（快照 + `.tmp` + 原子 rename，进程提前退出即放弃、下次全量 crawl），同时修掉「构建时为空、之后新增文件的目录不会被 `dirs` 记录」的已知失效缺陷；不改变索引格式版本、命中行为与回滚开关。

**Architecture:** 只动 agent 的 `FileIndexHook`（`save` 变调度、新增 `writeIndex`/`captureDirs`）+ 测试；transformer 与 `FileIndex` 格式零改动。写线程通过 `Thread.start()` 的 happens-before 读取 crawl 完成后的 `FileHandle` 快照；同一时刻最多一个 writer；目录 mtime 晚于 crawl 结束时间时放弃写盘（比同步 save 更保守）。空叶子目录通过把 FR 已经枚举到的目录 handle 的自身路径加进 `dirs` 来修正。

**Tech Stack:** Java 17（major 61）、JUnit 5、Python 3（`python -I`）、pytest、Git Bash（Windows 11）、`tools/smoke_run.py` / `tools/m3_ab.py` 测量栈。

**Spec:** `技术笔记-纹理按需加载.md` §7 M3.1（行 769–792）、§10.1 ADR-05 补记 3（行 873）；M3 结果 `docs/m3-results.md` §3.1（一次性构建 +15.1 s 的证据）；M3 已知 deferred 见 `hn-m3-complete` 末尾。

## 侦察证据（写计划前实测，不是假设）

| 证据 | 事实 | 来源 |
|---|---|---|
| 同步 save 的调用点 | `FileIndexTransformer` 在 `DirectoryCrawler.cacheLocations()I` 的**原始** IRETURN 前注入 `FileIndexHook.save(crawler, count)`；命中路径的注入 prologue 直接 IRETURN，不会走到 save | `src/agent/java/hypernova/agent/FileIndexTransformer.java:34-61` |
| 一次性构建成本 | 两轮独立 warm 构建均 menu **83.2 s**，同日 control 中位 68.1 s → **+15.1 s**；`written entries=223536, dirs=17067`；索引 3,332,575 B | `docs/m3-results.md` §3.1 |
| FR 0.9.7rc2 枚举结构 | `DirectoryCrawler.collector` 对**每个路径**（含目录）都放 `FileHandle`；`cacheLocations` 内部 `awaitTermination` 完成后才返回 | `.cache/fr-src/v0.9.7rc2_..._FileLoaderFast.java:242-357` |
| 空叶子缺陷 | `dirs` 只收 `file.getParentFile()` + DIRECTORY 根；**空目录自身从不入 `dirs`**，之后往里加文件时父目录 mtime 不变 → 命中不可见 | `FileIndexHook.addSaved`（现 425-443 行）；M3 Task 4 Minor-1 |
| 索引路径 | `ctx.cacheRoot().getParent()/file-index.idx.gz`（`saves/hypernova/file-index.idx.gz`） | `FileIndexHook.indexFile`（506-508 行） |
| 格式门 | `FileIndex.VERSION = 2`；`read` 对 magic/version/FR 版本/shapeStamp 不匹配返回 null | `FileIndex.java:29-111` |
| 本机 | 32 逻辑核（`nproc`），计划编写时无 java 进程 | `nproc` / `tasklist` |
| 现有测试 | Java agent 套件 97 found / 96 pass / 1 pre-existing symlink abort / 0 fail | `hn-m3-complete` |
| 日志消费方 | 只有 `tools/smoke_run.py` 收集 `file index:` 行并原样打印；无解析器依赖 `written` 行的精确格式 | `grep tools/*.py tests/tools/*.py` |

**结论：** 加一个 `+", ms=" + ...` 字段和新的 `save scheduled` / `save skipped` 行是安全的；`dirs` 集合规模只增加“空目录”这一小部分（非空目录本来就已作为父目录记录），命中路径的 stat 量基本不变。

## Global Constraints

- 不改 `Starsector-098-260mods/Miko_Lite.txt`、`Miko_Lite_nofr.txt`、`Miko_Simple.txt`、Base `fr.vmparams` 的**内容**；`Miko_Lite_nofr.txt` 只能由 `tools/m1e_profile.py` 从 `Miko_Lite.txt` 派生。启动档保持 CRLF，agent 安装器写 LF 的行由 `tools/install_agent.py` 负责。
- 不改 FR 版本（0.9.7rc2）、VOpt（1.0.45）、mod 列表；260mods 仍为 256 mods / agent-only。
- **不改 `FileIndex.VERSION`（保持 2）与序列化布局**；已有的 v2 索引不强制重建，空叶子硬化在下次重建后生效（spec §7 M3.1「格式/版本门与回滚开关不变」）。
- agent 编译目标 `--release 17`，所有自有 class major 61；agent 代码**不得编译期引用** `com.genir.*` / `com.fs.*` 之外的新依赖（现有反射约定不变）。
- 所有启动期新增逻辑 **fail-open**：线程创建失败、反射失败、目录变化、IO 失败都退回“不写索引”，绝不阻止游戏启动；写盘失败只影响下一次构建。
- 回滚开关不变：`-Dhypernova.fileIndex=false`（系统属性优先）或 `data/config/hypernova/hypernova.json` 的 `"fileIndex": { "enabled": false }`。
- 260mods 测量一律 `miko-lite` warm；A/B 同日同档；同时只跑一个游戏实例；杀进程只用 `taskkill /F /PID <pid>`，**绝不用** `taskkill //F //IM node.exe`。
- Python 工具一律 `python -I`；测量前把旧 `starsector.log` / `scripts-agent.log` 归档到 `build/m31-logs/`。
- 每个任务独立 commit，前缀 `feat(m3.1):` / `fix(m3.1):` / `docs(m3.1):` / `test(m3.1):` / `chore(m3.1):`。
- **逃逸舱**：若断言数字/测试顺序与实现不符，按实际修正并报告，无需请示；**若需求自相矛盾或无法同时满足 → 停下报告，不许挑一半照做。**

## Review Focus

1. **构建后目录被改动 → 写入的 mtime 比条目新，命中时隐藏新文件。** 预期行为：`dirs` 里任何一个目录的 mtime 晚于 crawl 结束时间，就放弃本次写盘（下次全量 crawl），绝不写出“新 mtime + 旧条目”的索引。对应测试：`Task 1 / captureDirsRejectsChangedAndMissingDirectories` + `writeIndexSkipsWhenTheDirectorySetChangedAfterTheCrawl`。
2. **构建时为空、之后被填充的目录。** 预期行为：该目录自身在 `dirs` 中，新增文件使目录 mtime 变化 → 索引失效并全量 crawl。对应测试：`Task 1 / emptyLeafDirectoryInvalidatesWhenAFileAppears`。
3. **游戏在写盘中途退出。** 预期行为：最终文件名下要么不存在、要么是完整可读的索引；`.tmp` 残留无害；下次启动 fail-open 全量 crawl。对应测试：`Task 1 / writeIndex...` 的原子写路径 + `Task 3` 的真实进程早退冒烟。
4. **跨线程可见性 / 生命周期。** 预期行为：writer 只读 `save()` 内同步快照（`collector.toArray()` / `locations.toArray()`），快照在 `Thread.start()` 之前完成（happens-before）；同一时刻至多一个 writer；`agent` 日志可出现 `save already in progress; skipping`，但不允许并发写同一个 `.tmp`。对应测试：`Task 1` 现有全家桶 + A/B 日志（无并发写）。
5. **异步写拖慢稳态命中路径。** 预期行为：`dirs` 规模只增加空目录；命中仍 3/3 且无 `full crawl`；首次构建 menu delta 目标 ≤2 s（相对同日 control）。对应测量：`Task 3` A/B + 3/3 hits。

---

### Task 1: 异步写盘 + 空叶子目录硬化（agent 代码 + 测试）

**Files:**
- Modify: `src/agent/java/hypernova/agent/FileIndexHook.java`（`save`、`addSaved`、新增 `writeIndex`/`captureDirs`/`awaitSavesForTest`、`resetForTest`）
- Modify: `tests/agent/fixtures/com/genir/renderer/overrides/loading/FileLoaderFast.java`（`crawlAndSave` 等待异步写）
- Test: `tests/agent/java/hypernova/agent/FileIndexHookTest.java`（新增 4 个测试）

**Dependencies:** []（无前置任务）
**Touches:** `src/agent/java/hypernova/agent/FileIndexHook.java`、`tests/agent/fixtures/com/genir/renderer/overrides/loading/FileLoaderFast.java`、`tests/agent/java/hypernova/agent/FileIndexHookTest.java`

**Interfaces:**
- Consumes: FR 0.9.7rc2 `DirectoryCrawler` 的 `this$0` / `collector` / `allLocations` 字段；`FileIndex.Location/Dir/Entry`；`RuntimeContext.cacheRoot()`；`AgentLog.info/fail`。
- Produces:
  - `public static void FileIndexHook.save(Object crawler, int count)` — 语义改为**调度**，立即返回；日志 `file index: save scheduled entries=<n>`。
  - `public static void FileIndexHook.awaitSavesForTest(long timeoutMs)` — 等待当前 writer 结束（测试 seam，跨包可见）。
  - `static boolean FileIndexHook.writeIndex(String frVersion, String shapeStamp, List<FileIndex.Location> keys, Object[] locations, Object[] items, Path target, long crawlEndMs)` — 写成功返回 true；目录消失/晚于 `crawlEndMs` 变化返回 false 且不落盘。
  - `static List<FileIndex.Dir> FileIndexHook.captureDirs(Set<String> dirs, long crawlEndMs)` — 成功返回列表；任一目录缺失或 `mtime > crawlEndMs` 返回 null 并记一行日志。
  - 日志新增：`file index: written entries=<n>, dirs=<n>, ms=<n>`；`file index: save skipped; directory missing [..]`；`file index: save skipped; directory changed after crawl [..]`；`file index: save already in progress; skipping`。

- [ ] **Step 1: 写失败的测试**

在 `tests/agent/java/hypernova/agent/FileIndexHookTest.java` 顶部 import 增加 `java.util.Set`（保持现有 `Field`/`Files` 等 import），并在 `supportedFrVersionsArePinned()` 之前加入以下测试与私有辅助方法：

```java
    @Test
    void emptyLeafDirectoryInvalidatesWhenAFileAppears() throws Exception {
        Path mod = tmp.resolve("game/mods/mod1");
        Path empty = mod.resolve("graphics/empty");
        Files.createDirectories(empty);
        Object loc = location(mod);
        FileLoaderFast first = new FileLoaderFast(List.of((FileLoader.ResourceLocation) loc));
        assertTrue(first.crawlAndSave() > 0);

        Files.writeString(empty.resolve("new.png"), "new");
        Thread.sleep(20);
        empty.toFile().setLastModified(System.currentTimeMillis());

        FileLoaderFast second = new FileLoaderFast(List.of((FileLoader.ResourceLocation) loc));
        assertEquals(-1, FileIndexHook.tryLoad(crawlerOf(second)),
                "a directory that was empty at build time must invalidate the index");
        assertTrue(mapOf(second).isEmpty(), "failed load must not leave partial entries");
        assertTrue(crawl(second) > 0, "full crawl must see the new file");
    }

    @Test
    void captureDirsRejectsChangedAndMissingDirectories() throws Exception {
        Path mod = tmp.resolve("game/mods/mod1");
        Files.createDirectories(mod);
        long stableCrawlEnd = System.currentTimeMillis() + 5_000;
        List<FileIndex.Dir> ok = FileIndexHook.captureDirs(Set.of(mod.toString()), stableCrawlEnd);
        assertNotNull(ok);
        assertEquals(1, ok.size());
        assertNull(FileIndexHook.captureDirs(Set.of(mod.toString()), 0L),
                "a directory modified after the crawl must abort the save");
        assertNull(FileIndexHook.captureDirs(
                Set.of(tmp.resolve("game/mods/never-existed").toString()), stableCrawlEnd),
                "a missing directory must abort the save");
    }

    @Test
    void writeIndexSkipsWhenTheDirectorySetChangedAfterTheCrawl() throws Exception {
        Path mod = tmp.resolve("game/mods/mod1");
        Object loc = location(mod);
        FileLoaderFast fast = new FileLoaderFast(List.of((FileLoader.ResourceLocation) loc));
        Object crawler = crawlerOf(fast);
        cacheLocations(crawler);
        Object outer = field(crawler, "this$0");
        @SuppressWarnings("unchecked")
        List<Object> locations = (List<Object>) field(outer, "allLocations");
        @SuppressWarnings("unchecked")
        List<Object> collector = (List<Object>) field(crawler, "collector");
        List<FileIndex.Location> keys = FileIndexHook.locationKeysForTest(locations);
        Path target = tmp.resolve("idx.gz");
        assertFalse(FileIndexHook.writeIndex("0.9.7rc2", "stamp", keys,
                locations.toArray(), collector.toArray(), target, 0L));
        assertFalse(Files.exists(target), "aborted save must not write the final file");
    }

    @Test
    void writeIndexPersistsAReadableIndexWhenDirectoriesAreStable() throws Exception {
        Path mod = tmp.resolve("game/mods/mod1");
        Object loc = location(mod);
        FileLoaderFast fast = new FileLoaderFast(List.of((FileLoader.ResourceLocation) loc));
        Object crawler = crawlerOf(fast);
        cacheLocations(crawler);
        Object outer = field(crawler, "this$0");
        @SuppressWarnings("unchecked")
        List<Object> locations = (List<Object>) field(outer, "allLocations");
        @SuppressWarnings("unchecked")
        List<Object> collector = (List<Object>) field(crawler, "collector");
        List<FileIndex.Location> keys = FileIndexHook.locationKeysForTest(locations);
        Path target = tmp.resolve("idx.gz");
        assertTrue(FileIndexHook.writeIndex("0.9.7rc2", "stamp", keys,
                locations.toArray(), collector.toArray(), target,
                System.currentTimeMillis() + 5_000));
        FileIndex index = FileIndex.read(target, "0.9.7rc2", "stamp");
        assertNotNull(index, "written index must be readable with the same stamps");
        assertEquals(keys, index.locations());
        assertFalse(index.entries().isEmpty());
    }

    private static Object field(Object target, String name) throws Exception {
        Field f = target.getClass().getDeclaredField(name);
        f.setAccessible(true);
        return f.get(target);
    }
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash tools/java/run-agent-tests.sh FileIndexHookTest`

Expected: 编译失败（`captureDirs` / `writeIndex` 不存在）；`emptyLeafDirectoryInvalidatesWhenAFileAppears` 即使在补上编译错误后也会失败。

- [ ] **Step 3: 实现 `save` 调度 + `writeIndex` + `captureDirs`**

在 `src/agent/java/hypernova/agent/FileIndexHook.java` 的 import 区加入 `java.util.concurrent.atomic.AtomicReference`（现有 `AtomicInteger` 保留），并在类字段区（`LAST_LOADED` 之后）加入：

```java
    private static final AtomicReference<Thread> SAVE_THREAD = new AtomicReference<>();
    private static final Object SAVE_LOCK = new Object();
```

把现有的 `save(Object crawler, int count)` 方法整体替换为：

```java
    /**
     * Schedules the index write on a daemon thread and returns immediately.
     *
     * <p>The snapshot is taken on the crawler thread: {@link Thread#start()}
     * publishes every write that happened before it (including the crawl's
     * {@code FileHandle} fields), and FR discards the crawler right after
     * {@code cacheLocations} returns. The payload is written to a {@code .tmp}
     * file and only renamed into place when complete, so a process that exits
     * early leaves either no index or a complete one; the next launch then
     * fail-opens to a full crawl.
     */
    public static void save(Object crawler, int count) {
        if (!enabled() || count <= 0 || LOADED.contains(crawler)) return;
        RuntimeContext ctx = context;
        if (ctx == null) return;
        try {
            Object outer = get(crawler, "this$0");
            if (outer == null) return;
            @SuppressWarnings("unchecked")
            List<Object> locations = (List<Object>) get(outer, "allLocations");
            @SuppressWarnings("unchecked")
            List<Object> collector = (List<Object>) get(crawler, "collector");
            if (locations == null || collector == null || locations.isEmpty()) return;
            String frVersion = frVersion();
            if (!supportedFrVersion(frVersion)) return;
            String shapeStamp = shapeStamp(locations, outer.getClass().getClassLoader());
            if (shapeStamp == null) {
                AgentLog.info("file index: cannot resolve runtime shape; index not saved");
                return;
            }
            List<FileIndex.Location> keys = locationKeys(locations);
            if (keys == null) return;

            // The injected call runs right before cacheLocations returns, so the
            // enumeration is complete; this timestamp bounds what the writer may
            // accept as an unchanged directory.
            long crawlEndMs = System.currentTimeMillis();
            Object[] items = collector.toArray();
            Object[] allLocations = locations.toArray();
            Path target = indexFile(ctx);

            Thread writer = new Thread(() -> {
                try {
                    writeIndex(frVersion, shapeStamp, keys, allLocations, items, target,
                            crawlEndMs);
                } finally {
                    SAVE_THREAD.compareAndSet(Thread.currentThread(), null);
                }
            }, "hypernova-file-index-writer");
            writer.setDaemon(true);
            writer.setPriority(Thread.MIN_PRIORITY);
            synchronized (SAVE_LOCK) {
                Thread previous = SAVE_THREAD.get();
                if (previous != null && previous.isAlive()) {
                    AgentLog.info("file index: save already in progress; skipping");
                    return;
                }
                SAVE_THREAD.set(writer);
            }
            AgentLog.info("file index: save scheduled entries=" + count);
            writer.start();
        } catch (Throwable t) {
            AgentLog.fail("file index save failed; next launch will crawl", t);
        }
    }

    /** Writes the snapshot; false means the index was not persisted. */
    static boolean writeIndex(String frVersion, String shapeStamp,
                              List<FileIndex.Location> keys, Object[] locations,
                              Object[] items, Path target, long crawlEndMs) {
        long start = System.currentTimeMillis();
        try {
            IdentityHashMap<Object, Integer> index = new IdentityHashMap<>();
            for (int i = 0; i < locations.length; i++) index.put(locations[i], i);
            List<FileIndex.Entry> entries = new ArrayList<>(Math.max(16, items.length));
            Set<String> dirs = new LinkedHashSet<>();
            for (Object item : items) {
                if (item instanceof List<?> list) {
                    for (Object handle : list) addSaved(handle, index, entries, dirs);
                } else {
                    addSaved(item, index, entries, dirs);
                }
            }
            for (FileIndex.Location location : keys) {
                if (!"DIRECTORY".equals(location.type())) continue;
                if (isExcluded(location.type(), location.path())) continue;
                File root = new File(location.path());
                if (root.isDirectory()) dirs.add(root.getPath());
            }
            List<FileIndex.Dir> dirList = captureDirs(dirs, crawlEndMs);
            if (dirList == null) return false;
            if (entries.isEmpty() && dirList.isEmpty()) return false;
            new FileIndex(frVersion, shapeStamp, keys, dirList, entries).write(target);
            AgentLog.info("file index: written entries=" + entries.size()
                    + ", dirs=" + dirList.size() + ", ms="
                    + (System.currentTimeMillis() - start));
            return true;
        } catch (Throwable t) {
            AgentLog.fail("file index save failed; next launch will crawl", t);
            return false;
        }
    }

    /**
     * Reads the recorded directory mtimes. Returns null when a directory
     * disappeared or was modified after the crawl finished: the enumeration
     * would then describe an older state than the timestamps, and a later cache
     * hit could hide the change. Aborting is fail-open (next launch crawls).
     */
    static List<FileIndex.Dir> captureDirs(Set<String> dirs, long crawlEndMs) {
        List<FileIndex.Dir> out = new ArrayList<>(dirs.size());
        for (String dir : dirs) {
            long mtime = new File(dir).lastModified();
            if (mtime == 0) {
                AgentLog.info("file index: save skipped; directory missing [" + dir + "]");
                return null;
            }
            if (mtime > crawlEndMs) {
                AgentLog.info("file index: save skipped; directory changed after crawl ["
                        + dir + "]");
                return null;
            }
            out.add(new FileIndex.Dir(dir, mtime));
        }
        return out;
    }

    /** Waits for the currently scheduled writer; exposed for the test fixture. */
    public static void awaitSavesForTest(long timeoutMs) {
        for (int i = 0; i < 10; i++) {
            Thread writer = SAVE_THREAD.get();
            if (writer == null) return;
            try {
                writer.join(timeoutMs);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            if (SAVE_THREAD.get() == writer) return;
        }
    }
```

- [ ] **Step 4: 实现 `addSaved` 的目录自身记录**

把现有的 `addSaved(...)` 方法整体替换为（唯一差异：在拿到 `file` 且 `locationIndex != null` 之后，先把目录自身路径加入 `dirs`）：

```java
    private static void addSaved(Object handle, IdentityHashMap<Object, Integer> index,
                                 List<FileIndex.Entry> entries, Set<String> dirs) {
        try {
            Object location = get(handle, "location");
            String type = typeName(location);
            String path = pathOf(location);
            if (!"DIRECTORY".equals(type) || isExcluded(type, path)) return;
            File file = (File) get(handle, "file");
            Integer locationIndex = index.get(location);
            if (file == null || locationIndex == null) return;
            // FR enumerates directories as handles too. Recording each directory's
            // own path is what makes a directory that was EMPTY at build time
            // invalidate the index when a file appears inside it later (its
            // parent's mtime does not change in that case).
            if (file.isDirectory()) dirs.add(file.getPath());
            String key = keyFor(file, location);
            if (key.isEmpty()) return;
            entries.add(new FileIndex.Entry(key, file.getPath(), locationIndex));
            File parent = file.getParentFile();
            if (parent != null) dirs.add(parent.getPath());
        } catch (Throwable ignored) {
            // One bad handle must not abort the whole index.
        }
    }
```

- [ ] **Step 5: `resetForTest` 先等 writer**

把现有的 `resetForTest()` 方法替换为：

```java
    static void resetForTest() {
        awaitSavesForTest(30_000);
        LOADED.clear();
        LAST_LOADED.set(Integer.MIN_VALUE);
        context = null;
    }
```

- [ ] **Step 6: 测试 fixture 等待异步写**

在 `tests/agent/fixtures/com/genir/renderer/overrides/loading/FileLoaderFast.java` 中，把 `crawlAndSave()` 替换为：

```java
    /** Runs the crawl and saves on the same crawler instance (production shape). */
    public int crawlAndSave() {
        DirectoryCrawler crawler = new DirectoryCrawler();
        int count = crawler.cacheLocations();
        FileIndexHook.save(crawler, count);
        FileIndexHook.awaitSavesForTest(30_000);
        return count;
    }
```

- [ ] **Step 7: 跑目标测试确认通过**

Run: `bash tools/java/run-agent-tests.sh FileIndex`

Expected: `FileIndexTest`、`FileIndexHookTest`、`FileIndexTransformerTest` 全绿（无 failed / aborted）。

- [ ] **Step 8: 跑全部 agent 测试（防回归）**

Run: `JAVA_RUNTIME="D:/github/Hypernova-Infinite-Engine/Starsector-098-Base/jre/bin/java.exe" bash tools/java/run-agent-tests.sh`

Expected: 101 found（97 既有 + 4 新增）/ 100 successful / 1 pre-existing symlink aborted / 0 failed。

- [ ] **Step 9: Commit**

```bash
git add src/agent/java/hypernova/agent/FileIndexHook.java \
  tests/agent/fixtures/com/genir/renderer/overrides/loading/FileLoaderFast.java \
  tests/agent/java/hypernova/agent/FileIndexHookTest.java
git commit -m "feat(m3.1): write the file index off the startup path"
```

---

### Task 2: `smoke_run.py` 每轮清索引开关（首次构建 A/B 的前置工具）

**Files:**
- Modify: `tools/smoke_run.py`
- Test: `tests/tools/test_smoke_run.py`

**Dependencies:** []（无前置任务，文件与 Task 1 不重叠）
**Touches:** `tools/smoke_run.py`、`tests/tools/test_smoke_run.py`

**Interfaces:**
- Consumes: 现有 `PROFILES` / `main()` 流程。
- Produces:
  - `smoke_run.index_path_for(game: Path) -> Path`（`saves/hypernova/file-index.idx.gz`）
  - `smoke_run.clear_index(game: Path) -> bool`（存在则删除并返回 True）
  - CLI `--clear-index-each-round`（每轮启动前调用 `clear_index`）

- [ ] **Step 1: 写失败的测试**

在 `tests/tools/test_smoke_run.py` 末尾加入：

```python
def test_index_path_for_points_at_saves_index():
    game = Path("game-root")
    assert smoke.index_path_for(game) == game / "saves" / "hypernova" / "file-index.idx.gz"


def test_clear_index_removes_only_the_index(tmp_path):
    index = smoke.index_path_for(tmp_path)
    index.parent.mkdir(parents=True)
    index.write_bytes(b"x")
    keep = index.parent / "scripts-cache"
    keep.write_bytes(b"keep")
    assert smoke.clear_index(tmp_path) is True
    assert not index.exists()
    assert keep.exists()
    assert smoke.clear_index(tmp_path) is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -I -m pytest tests/tools/test_smoke_run.py -q`

Expected: FAIL / AttributeError（`index_path_for` / `clear_index` 不存在）。

- [ ] **Step 3: 实现两个函数与 CLI 开关**

在 `tools/smoke_run.py` 的 `agent_log_for(game)` 定义之后加入：

```python
def index_path_for(game: Path) -> Path:
    return game / "saves" / "hypernova" / "file-index.idx.gz"


def clear_index(game: Path) -> bool:
    """Deletes the file index; True when a file was removed."""
    index = index_path_for(game)
    if not index.exists():
        return False
    index.unlink()
    return True
```

在 `main()` 的 argparse 参数区（`--clear-cache-first` 之后）加入：

```python
    ap.add_argument("--clear-index-each-round", action="store_true",
                    help="每轮启动前删除 file-index.idx.gz（测首次构建成本）")
```

把轮次循环替换为：

```python
    for i in range(1, args.rounds + 1):
        if args.clear_index_each_round and clear_index(game):
            print(f"[smoke] cleared {index_path_for(game)}")
        print(f"\n########## 第 {i}/{args.rounds} 轮 ##########")
        rows.append(one_round(cfg, game, args))
        if i < args.rounds:
            time.sleep(3)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -I -m pytest tests/tools/test_smoke_run.py -q`

Expected: 全部 PASS（含既有测试）。

- [ ] **Step 5: Commit**

```bash
git add tools/smoke_run.py tests/tools/test_smoke_run.py
git commit -m "feat(m3.1): add a per-round file-index reset to the smoke runner"
```

---

### Task 3: 构建/安装 + 首次构建 A/B + 3/3 命中 + 早退 fail-open + 门禁

**Files:**
- Create: `docs/m31-results.md`
- Modify（如测量发现缺陷）：回退到 Task 1 的责任人修，本任务不直接改代码
- Runtime artifacts: `build/m31-*.json`、`build/m31-logs/*`（不入库）

**Dependencies:** [Task 1, Task 2]
**Touches:** `docs/m31-results.md`（新建）；`build/m31-*.json`、`build/m31-logs/*`（不入库）

**Interfaces:**
- Consumes: Task 1 的新 agent jar；Task 2 的 `--clear-index-each-round`；`tools/m3_ab.py`；`tools/m1b_measure.py`；`tools/m1e_profile.py`；`tools/install_agent.py`；`tools/m1e_java_audit.py`。
- Produces: `docs/m31-results.md` 中的四张表（首次构建 A/B、3/3 命中、早退 fail-open、门禁）与结论（是否达到 ≤2 s；若未达到，如实报告实际值）。

- [ ] **Step 1: 环境确认与旧日志归档**

```bash
tasklist //FI "IMAGENAME eq java.exe" //NH
mkdir -p build/m31-logs
cp Starsector-098-260mods/starsector-core/starsector.log build/m31-logs/pre-260.log 2>/dev/null || true
cp Starsector-098-260mods/saves/hypernova/scripts-agent.log build/m31-logs/pre-260-agent.log 2>/dev/null || true
```

Expected: 无 java 进程（否则先请用户停掉，不要盲杀）；两条 `cp` 成功或不存在。

- [ ] **Step 2: 构建 + Java 17 全量测试 + ABI audit**

```bash
bash tools/java/build-agent.sh
JAVA_RUNTIME="D:/github/Hypernova-Infinite-Engine/Starsector-098-Base/jre/bin/java.exe" \
  bash tools/java/run-agent-tests.sh
python -I tools/m1e_java_audit.py \
  --classes build/agent/classes \
  --jar build/agent/hypernova.agent.jar \
  --source src/agent/java \
  --expect-major 61 \
  --json-out build/m31-java-audit.json
```

Expected: `OK: build/agent/hypernova.agent.jar`；101/100/1 abort/0 failed；`ok=true`、`java21_api_hits=[]`。

- [ ] **Step 3: 安装到三档并同步配置**

```bash
python -I tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite
python -I tools/install_agent.py --game Starsector-098-260mods --env 260mods-simple
python -I tools/install_agent.py --game Starsector-098-Base  --env base
cp data/config/hypernova/hypernova.json \
  Starsector-098-260mods/mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json
cp data/config/hypernova/hypernova.json \
  Starsector-098-Base/mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json
```

Expected: 三个启动文件都含 agent 行且其余内容不变；`hypernova.json` 含 `"fileIndex": {"enabled": true}`。

- [ ] **Step 4: 首次构建 A/B（交错 3+3，warm-up 不计）**

```bash
rm -f Starsector-098-260mods/saves/hypernova/file-index.idx.gz
python -I tools/smoke_run.py --profile miko-lite --rounds 1 \
  --jvm-arg=-Dhypernova.fileIndex=false --json-out build/m31-warmup-control.json
python -I tools/smoke_run.py --profile miko-lite --rounds 1 \
  --clear-index-each-round --json-out build/m31-warmup-treatment.json
python -I tools/smoke_run.py --profile miko-lite --rounds 1 \
  --jvm-arg=-Dhypernova.fileIndex=false --json-out build/m31-control-1.json
python -I tools/smoke_run.py --profile miko-lite --rounds 1 \
  --clear-index-each-round --json-out build/m31-treatment-1.json
python -I tools/smoke_run.py --profile miko-lite --rounds 1 \
  --jvm-arg=-Dhypernova.fileIndex=false --json-out build/m31-control-2.json
python -I tools/smoke_run.py --profile miko-lite --rounds 1 \
  --clear-index-each-round --json-out build/m31-treatment-2.json
python -I tools/smoke_run.py --profile miko-lite --rounds 1 \
  --jvm-arg=-Dhypernova.fileIndex=false --json-out build/m31-control-3.json
python -I tools/smoke_run.py --profile miko-lite --rounds 1 \
  --clear-index-each-round --json-out build/m31-treatment-3.json
```

Expected: 8 轮均 `ok=true` 到主菜单。每轮 treatment 的 `agent.file_index` 里应出现 `save scheduled` 与 `written entries=<约 22 万>, dirs=<约 1.7 万>, ms=<n>`；不得出现 `save failed` / `save skipped`。control 不应出现任何 `file index:` 行。**测量期间不要跑别的重负载任务**（异步 writer 与游戏争 CPU 是唯一噪声源）。

- [ ] **Step 5: 汇总 + 判定 ≤2 s**

```bash
python -I - <<'PY'
import json, pathlib
for name in ("control", "treatment"):
    rows = []
    for p in sorted(pathlib.Path("build").glob(f"m31-{name}-*.json")):
        rows += json.loads(p.read_text(encoding="utf-8"))
    pathlib.Path(f"build/m31-{name}.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
PY
python -I tools/m3_ab.py --control build/m31-control.json \
  --treatment build/m31-treatment.json --json-out build/m31-ab.json
```

Expected: `delta_s` = control 中位 − treatment 中位。**达标条件：`delta_s <= 2.0` 且每轮 treatment 都 `written`。** 若不达标但 `delta_s < 15.1`，照实记录实际值（这是 spec 的目标，不是验收硬门）；若 `delta_s < 0`（treatment 反而更慢），同样照实记录并在 Task 4 裁决（可能证据不足，需重跑一次交错）。

- [ ] **Step 6: 3/3 命中验证**

```bash
rm -f Starsector-098-260mods/saves/hypernova/file-index.idx.gz
python -I tools/smoke_run.py --profile miko-lite --rounds 1 \
  --json-out build/m31-hits-build.json
python -I tools/smoke_run.py --profile miko-lite --rounds 3 \
  --json-out build/m31-hits.json
python -I - <<'PY'
import json, pathlib
rows = json.loads(pathlib.Path("build/m31-hits.json").read_text(encoding="utf-8"))
for i, r in enumerate(rows, 1):
    lines = r.get("agent", {}).get("file_index", [])
    print(i, "ok=", r.get("ok"), "menu_s=", r.get("menu_s"),
          "loaded=", sum("file index: loaded" in l for l in lines),
          "full_crawl=", sum("full crawl" in l for l in lines))
PY
```

Expected: build 轮 `written`；3 轮命中轮每轮 `loaded=1`、`full_crawl=0`，且 `ok=true`。

- [ ] **Step 7: 早退 fail-open（真实进程中途杀）**

```bash
rm -f Starsector-098-260mods/saves/hypernova/file-index.idx.gz
python -I tools/smoke_run.py --profile miko-lite --rounds 1 --wait-menu 12 \
  --linger 0 --json-out build/m31-early-exit.json || true
grep -E "file index: (absent|save scheduled|written|save skipped)" \
  Starsector-098-260mods/saves/hypernova/scripts-agent.log | tail -5
ls -l Starsector-098-260mods/saves/hypernova/file-index.idx.gz* 2>/dev/null || echo "no index files"
```

Expected: 日志出现 `save scheduled`，且**不出现**其后的 `written`（kill 落在写盘中途）；`file-index.idx.gz` 不存在（`.tmp` 可存在）。若 `written` 已出现（kill 太晚），把 `--wait-menu` 降到 9 再试，最多重试 3 次。然后恢复验证：

```bash
python -I tools/smoke_run.py --profile miko-lite --rounds 1 \
  --json-out build/m31-recover.json
grep -E "file index:" Starsector-098-260mods/saves/hypernova/scripts-agent.log | tail -3
```

Expected: 恢复轮先 `absent, corrupt, or FR version/shape mismatch; full crawl`，随后 `written`；`ok=true`。

- [ ] **Step 8: Base 构建 + 命中**

```bash
rm -f Starsector-098-Base/saves/hypernova/file-index.idx.gz
python -I tools/smoke_run.py --profile base --rounds 2 --json-out build/m31-base.json
```

Expected: 两轮 `ok=true`；第 1 轮 `written`，第 2 轮 `loaded`。

- [ ] **Step 9: textures 门禁（回归确认）**

```bash
cp Starsector-098-260mods/starsector-core/starsector.log build/m31-logs/treatment.log
cp Starsector-098-260mods/saves/hypernova/scripts-agent.log build/m31-logs/treatment-agent.log
python -I tools/m1b_measure.py \
  --log build/m31-logs/treatment.log \
  --agent-log build/m31-logs/treatment-agent.log \
  --baseline 30378 --json-out build/m31-textures.json
```

Expected: `normal_before_menu=0`、`patched=true`、`mismatch_line=null`、`gate_ok=true`。

- [ ] **Step 10: no-FR 门禁（长跑 ~22 min，最后跑）**

```bash
python -I tools/m1e_profile.py \
  --src Starsector-098-260mods/Miko_Lite.txt \
  --out Starsector-098-260mods/Miko_Lite_nofr.txt --force
python -I tools/smoke_run.py --profile miko-lite-nofr --rounds 1 \
  --wait-menu 3600 --json-out build/m31-nofr.json
python -I tools/m1b_measure.py \
  --log Starsector-098-260mods/starsector-core/starsector.log \
  --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
  --expect-no-fr --normal-metric cleaned --baseline 30378 \
  --json-out build/m31-nofr-measure.json
```

Expected: `fr_present=false`、`fr_missing_disabled=true`、`gate_ok=true`；agent 日志**不应**出现 `file index transformer registered` 或任何 `file index:` 行（异步写路径在无 FR 时根本不注册）。

- [ ] **Step 11: 写 `docs/m31-results.md` 并提交**

文件骨架（所有 `<...>` 由实测数字替换，禁止留占位符）：

```markdown
# M3.1（索引 save 异步化）结果

> 日期：<YYYY-MM-DD>
> 环境：Starsector 0.98a + 260mods（256 mods，agent-only）、Miko Lite（JDK 28）
> 宿主：Fast Rendering 0.9.7rc2；agent jar <sha 前 8 位>；索引格式 v2（未改）

## 1. 改动
- `FileIndexHook.save` 改为 daemon 线程调度（快照 + `.tmp` + 原子 rename + MIN_PRIORITY）。
- 目录 mtime 晚于 crawl 结束时间 → 放弃本次写盘（fail-open）。
- `dirs` 增加目录自身路径（空叶子目录失效硬化）。
- 未改 `FileIndex.VERSION` / 序列化布局 / transformer / 回滚开关。

## 2. 首次构建 A/B（同日 `miko-lite` warm，交错 3+3，warm-up 不计）
| 轮 | control menu_s（`fileIndex=false`） | treatment menu_s（每轮删索引） |
|---|---:|---:|
| 1 | <..> | <..> |
| 2 | <..> | <..> |
| 3 | <..> | <..> |
| 中位 | <..> | <..> |

- `delta_s = <..>`（目标 ≤2.0；M3 同步 save 的一次性成本为 +15.1 s）。
- 每轮 treatment：`save scheduled` → `written entries=…, dirs=…, ms=<..>`。

## 3. 3/3 命中
| 轮 | menu_s | `file index: loaded` | `full crawl` |
|---|---:|---:|---:|
| 1 | <..> | 1 | 0 |
| 2 | <..> | 1 | 0 |
| 3 | <..> | 1 | 0 |

## 4. 早退 fail-open
- kill 前日志：`save scheduled`；kill 后：无 `written`，`file-index.idx.gz` 不存在（`.tmp` <有/无>）。
- 恢复轮：`full crawl` → `written` → 主菜单 `ok=true`。

## 5. 门禁
| 门禁 | 结果 |
|---|---|
| Java 17 测试 | <found/successful/aborted/failed> |
| ABI audit | ok=<..>, java21_api_hits=<..> |
| textures | normal_before_menu=0 / patched=<..> / gate_ok=<..> |
| Base | build → hit，两轮 ok |
| no-FR | fr_present=false / fileIndex 未注册 / gate_ok=<..> |
| 回滚 | control（`-Dhypernova.fileIndex=false`）3 轮正常 |

## 6. 边界与已知限制
- 异步窗口内目录被写 → 本次不落盘（下次重建）；比同步 save 的静默接受更保守。
- 爬取过程中（crawlEnd 之前的）写入仍是既有盲区，M3.1 不改变该窗口。
- 已有 v2 索引不会被强制重建；空叶子硬化在下次重建后生效。
```

```bash
git add docs/m31-results.md
git commit -m "docs(m3.1): record the async save A/B and runtime gates"
```

---

### Task 4: 规格/结果/记忆收口

**Files:**
- Modify: `技术笔记-纹理按需加载.md`（§7 M3.1 状态、§10.1 ADR-05 补记 4）
- Modify: `docs/m3-results.md`（§3.1 末尾加一行指向 M3.1 的结果；不改历史数字）
- Modify: `C:\Users\qwe13\.claude\projects\D--github-Hypernova-Infinite-Engine\memory\hn-next-session.md`（钩子改为 M2）
- Create: `C:\Users\qwe13\.claude\projects\D--github-Hypernova-Infinite-Engine\memory\hn-m31-complete.md`
- Modify: `C:\Users\qwe13\.claude\projects\D--github-Hypernova-Infinite-Engine\memory\MEMORY.md`（索引行）

**Dependencies:** [Task 3]
**Touches:** `技术笔记-纹理按需加载.md`、`docs/m3-results.md`、`docs/m31-results.md`、`~/.claude/projects/D--github-Hypernova-Infinite-Engine/memory/{hn-next-session.md,hn-m31-complete.md,MEMORY.md}`

**Interfaces:**
- Consumes: Task 3 的 `docs/m31-results.md` 全部数字。
- Produces: 下次会话钩子（`/SDD 开始M2`）；规格里 M3.1 的最终状态。

- [ ] **Step 1: 更新规格 §7 M3.1**

把 `### M3.1 索引 save 异步化（2026-10-31 裁决；M2 前置）` 小节的 `**状态**` 行替换为（其余验收/停止条件保留）：

```markdown
- **状态**：**已完成（<YYYY-MM-DD>）**。首次构建 A/B control 中位 <C> s → treatment 中位 <T> s
  （delta <D> s，目标 ≤2 s <达成/未达成：实际值>）；3/3 命中；早退 fail-open 验证通过；
  Java 17 / Base / no-FR 门禁通过；格式 v2、回滚开关不变。
  详见 `docs/m31-results.md`。
```

- [ ] **Step 2: 追加 ADR-05 补记 4**

在 `§10.1` 的 `> **ADR-05 补记 3（2026-10-31，M3 收口后）**` 段之后追加：

```markdown
> **ADR-05 补记 4（<YYYY-MM-DD>，M3.1 收口后）**：M3.1 已完成——索引 save 移入 daemon
> 线程（快照 + `.tmp` + 原子 rename；目录 mtime 晚于 crawl 结束时放弃写盘），并硬化空叶子
> 目录失效；首次构建 menu delta <D> s（目标 ≤2 s<，实际值如实记录>）；3/3 命中；
> 格式 v2 与回滚开关不变。下一里程碑 **M2**（option 2：OD-02 A 全预载 + manifest
> 键稳定性/覆盖前置，再全量）。
```

- [ ] **Step 3: `docs/m3-results.md` §3.1 加指向**

在 §3.1 末尾（“后续方向（不在 M3 范围）”一段之后）加入：

```markdown
- **M3.1 已跟进（<YYYY-MM-DD>）**：异步 save + 空叶子目录硬化已落地，首次构建 A/B 见
  `docs/m31-results.md`；§3.1 的 +15.1 s 是 M3 时同步 save 的历史口径。
```

- [ ] **Step 4: 更新记忆**

`hn-next-session.md` 首段钩子改为：下个会话发 **`/SDD 开始M2`**；M3.1 已完成；读 `docs/m31-results.md`；M2 option 2（OD-02 A 全预载 + manifest 键稳定性/覆盖前置，再全量）。删除已经完成的 M3.1 待办条目，保留“可选归因 A/B”等未做项。

新建 `hn-m31-complete.md`：

```markdown
---
name: hn-m31-complete
description: "M3.1 完成（<日期>）：索引 save 异步化 + 空叶子目录硬化；首次构建 delta <D> s；3/3 命中；早退 fail-open；下一 M2"
metadata:
  node_type: memory
  type: project
---

**M3.1 完成（<日期>）。** 要点：
- `FileIndexHook.save` → daemon `hypernova-file-index-writer`（快照 + `.tmp` + ATOMIC_MOVE + MIN_PRIORITY）；`awaitSavesForTest` 测试 seam。
- 目录 mtime 晚于 crawl 结束 → 放弃写盘（`save skipped; directory changed after crawl`）。
- `dirs` 增加目录自身路径 → 空叶子目录新增文件可失效（回归测试）。
- 首次构建 A/B：control <C> → treatment <T> s（delta <D> s；M3 同步 save 为 +15.1 s）；3/3 命中；早退 fail-open。
- 格式 v2 未改；回滚 `-Dhypernova.fileIndex=false` 不变。
- 下一：`/SDD 开始M2`（option 2）。见 [[hn-next-session]]、`docs/m31-results.md`。
```

在 `MEMORY.md` 顶部附近加一行索引：

```markdown
- [**M3.1 完成**](hn-m31-complete.md) — 索引 save 异步化 + 空叶子硬化；首次构建 delta <D> s；3/3 命中；下一 M2
```

- [ ] **Step 5: Commit**

```bash
git add 技术笔记-纹理按需加载.md docs/m3-results.md
git commit -m "docs(m3.1): close the milestone and point to M2"
```

---

## 计划自审（写完立即执行，不留到执行期）

| spec 要求（§7 M3.1） | 落点 |
|---|---|
| 把 save 移出启动关键路径（daemon） | Task 1 Step 3；Task 3 Step 4/5 测量 |
| 临时文件 + 原子 rename；退出则放弃 | Task 1 Step 3（复用既有 `FileIndex.write`）；Task 3 Step 7 |
| 不改变格式/语义/命中行为 | Task 1（`FileIndex.java` 零改动）；Task 3 Step 6（3/3 命中） |
| 首次构建 menu delta ≤2 s | Task 3 Step 4/5（如实记录是否达成） |
| 索引 3/3 命中 | Task 3 Step 6 |
| 退出前写盘 fail-open | Task 1 Step 3 + Task 3 Step 7 |
| 格式/版本门与回滚开关不变 | Global Constraints；Task 3 Step 4 control 即回滚验证 |
| 空叶子目录失效硬化（M3 deferred） | Task 1 Step 1（测试）+ Step 4（实现） |
| 停止条件：线程安全无法保证 → 保留同步 | Review Focus #4；Task 1 的快照 + 单 writer 设计已覆盖；若实测出现并发/竞争证据，按停止条件回退并在 ledger 裁决 |

**占位符扫描：** 计划中没有 TBD/TODO/悬空 stub；Task 3/4 的 `<...>` 是明确的“实测后替换”值，由测量步骤产出。

**类型一致性：** `save(Object,int)` 签名不变；新增 `writeIndex(String,String,List<FileIndex.Location>,Object[],Object[],Path,long)->boolean`、`captureDirs(Set<String>,long)->List<FileIndex.Dir>`、`awaitSavesForTest(long)`；fixture 与测试调用一致。

## 执行备注（controller 用）

- 模式：**pipeline**（Task 1/2 无共享文件，可顺序；Task 3 依赖两者；Task 4 依赖 3）。若想把 1/2 并行，写者表无重叠，但 pipeline 更简单。
- 模型：Task 1/haiku（计划含完整代码）、Task 2/haiku、Task 3/sonnet（集成与判断）、Task 4/sonnet（文档措辞）；reviewer sonnet；最终全分支 opus。
- Task 3 全程约 40–60 分钟（8 轮 A/B + 3 轮命中 + 早退 + Base + ~22 min no-FR）；测量期间不得并行派其他 implementer 跑游戏或重负载。
- 若 Task 3 的 A/B 未达 ≤2 s：不当作失败修复代码，先重跑一次交错确认；仍不达标则如实写入结果并在 ledger 记 Ruling（异步仍是正确方向，收益以实测为准）。

## Addendum A（2026-10-31，controller 裁决，用户确认）

**Task 3 Step 10（no-FR 门禁，~22 min）跳过。** 理由：无 FR 时 `HypernovaAgent.supportedFrVersion()` 返回 unknown，`FileIndexTransformer` 不注册，本次改动的 save 路径不可达；M3 的 no-FR 门禁已覆盖注册逻辑；JRE17 全量 + Base + 260mods 已覆盖类加载。结果文档 §5 必须如实写「本轮跳过（裁决）」及理由，不得伪造结果。
