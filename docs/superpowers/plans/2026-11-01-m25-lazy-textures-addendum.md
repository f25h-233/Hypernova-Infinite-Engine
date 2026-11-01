# M2.5 Task 2–5 Addendum — 生产懒纹理（跳过 / 代理 / 按需物化）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Addendum 优先**：本文件覆盖主计划 `2026-11-01-m25-lazy-textures.md` 的 Task 2–5；主计划的 Task 1 与 GO 证据保持不变。

**Goal:** 在 GO 证据成立的前提下，把 M2.5 的只读探针升级为生产懒纹理：启动期跳过非 L1 纹理队列，登记与真图同尺寸/UV 的代理 `Object`，在加载线程或运行期主线程首次查表时用 donor 同步路径物化；默认关闭、可回滚、版本/形状门禁、fail-open。

**Architecture:** 复用主计划的三个 hook（预置同名 `lambda$queueImage$0`、`oOoO` rename+wrapper、pre-FR transformer 顺序）。新增：`ProxyShape`（反射 `com.fs.graphics.Object` 的 14 个字段/构造器）、`LazyGameThreadTransformer`（`BaseGameState.traverse` 入口捕获运行期主线程）、donor 7 参同步路径物化 + 逐字段拷贝 + `TextureLoader` path cache。探针模式保留；生产模式由 `textures.lazy.enabled`（默认 false）或 `-Dhypernova.textures.lazy=true` 开启。

**Tech Stack:** 同主计划；生产代码只用 JDK 反射 + 现有 ASM 9.1（不新增依赖）；agent 不 import 游戏/FR 类。

**Spec:** `技术笔记-纹理按需加载.md` §5.2/§5.3/§5.6/§7、REQ-R2-01..04、INV-06/10；R-M25-1..6。

---

## Global Constraints

- **默认关闭**：`textures.lazy.enabled=false`；A/B 只用 `-Dhypernova.textures.lazy=true/false`。M2.5 通过验收前不改默认值。
- **agent 在 FR 之前**；预置同名 donor lambda；若类里已有 `lambda$queueImage$0` → 放弃（不覆盖）。
- **永不跳过**：L1（skip 文件已排除）、`TEXTURE_ALPHA_ADDER`、`graphics/ui/bottomright*`（skip 文件已排除）、`w/h<=0`（已排除）。
- **物化线程**：只允许**加载线程**（`com.fs.util.C.mainThread`，`initResourceLoading` 记录）或**运行期主线程**（`BaseGameState.traverse` 捕获，跳过 launcher 状态）。texture worker / 其它线程只返回代理，不碰 GL。
- **代理尺寸**：`com.fs.graphics.Object` 的 width/height/imageWidth/imageHeight 用 manifest 的 `w/h`（非 Blacklist 路径 FR 不补 POT）；texWidth/texHeight = 1.0；stringId/path = 原 path。**不得用错 manifest 版本**；`install_manifest.py` 必须与 skip 文件同代生成。
- **物化路径**：反射 donor 7 参 `o00000(Object,String,int,int,int,int,boolean)`，参数 `null, path, 3553, 6408, 9729, 9729, false`；返回新 `Object`，逐字段拷入代理（不注册新对象、不重复 glGenTextures；新对象成为垃圾，其 GL id 归代理）。
- **fail-open**：形状 gate 失败 → `disabled=1`，所有路径走 `loadTextureAsync`；物化失败 → 保留占位、最多重试 1 次、日志；任何异常不得外抛到游戏。
- **不得改** `enabled_mods.json`、`Miko_*.txt`、`fr.vmparams`、游戏设置；安装只走已有脚本/安装器；**绝不用 `taskkill //F //IM node.exe`**。
- **DDS/VRAM 口径**：运行期 `loadTexture` 无 `ResourceHandle` → 物化为 PNG（RGBA），不是 BC7 DDS；VRAM 可能高于 baseline 的 DDS 懒上传。Task 4 必须实测，不得在测前宣称 VRAM 收益。
- **日志**：每轮归档 `starsector.log`；agent 日志取最后一个 `premain` 会话；FR 用 `v0.9.7rc2`。
- **Escape hatch**：断言数字/顺序与实现不符 → 按实际修正并报告；**需求自相矛盾 → 停下报告，不许挑一半照做。**

## Review Focus

1. **主线程捕获**：`BaseGameState.traverse` 入口注入 `captureMainThread(this)`；launcher 状态跳过；`FileLoader.mainThread` 是加载线程，不是运行期主线程——两者都允许物化，但不能混为“主线程”。
2. **代理字段/UV**：14 字段全部设置；非 POT 用 `w/h` 原尺寸；`stringId/path` 正确；`Sprite.setTexture` 在构造时缓存这些值，物化后必须与真图一致。
3. **物化同一 id**：donor 7 参返回新 Object；逐字段拷贝到代理；不把新对象注册进 `oOoO`；不重复 glGenTextures；`>1024²` 自然由新 id 规避。
4. **engine hit / path cache**：`probeResult` 收到非 null 时 `noteEngineHit` 拷字段；物化后把代理放进 `TextureLoader.ÔO0000`；避免同一 path 两个 GL id。
5. **skip 口径与形状 gate**：L1/alpha-adder/blacklist/无效尺寸；`oOoO`/`Object`/`TextureLoader` 形状失败 → disabled；agent 顺序反了 → 不覆盖。
6. **默认关闭/回滚**：`textures.lazy.enabled=false` 或删 agent 行；关闭后行为回到 M2；A/B 的 treatment 是显式属性。
7. **post-menu 7.3k burst**：v1 同步物化；Task 4 必须测 stutter/working set；若 >200 ms，回退或加预算（Task 5 决策）。

---

## Pre-flight（controller 在派发前写入 ledger）

- **Mode:** `pipeline`（继续；Task 2 → 内部 gate → Task 3 → Task 4 → Task 5）。
- **BASE:** 主计划 Task 1 的最终 fix 提交 `853df1e`；本 addendum 提交后作为 Task 2 的 BASE。
- **GO 证据（2026-11-01，fix jar）**：
  - 260mods p4–p7：queue 52,604；wouldSkip 45,785；skip_fraction 0.8704；operational `demandQueued` 菜单前 **798–801**（1.74–1.75%）、会话末 **7,313–7,382**（15.97–16.12%）；hits=all、misses=0；阈值 0.20×45,785=**9,157**；
  - G1 PASS；G2 operational PASS（raw 字面 NO-GO 按 R-M25-6 判为测量缺陷）；G3 PASS（环境漂移 caveat）；G4 PASS（0 Failed / 0 Verify / 0 Class；agent 0 ERROR）。
  - 用户裁决：**GO，先补 fix-jar G3（已完成），写 addendum 并派 Task 2**。
- **Rulings 继承**：R-M25-1（agent 在 FR 前）、R-M25-2（`Loading image` 是 PNG 计数）、R-M25-3（skip 集）、R-M25-4（默认 off）、R-M25-5（addendum）、R-M25-6（operational 口径）。
- **新增 Rulings**：
  1. **R-M25-7**：物化线程 = `FileLoader.mainThread`（加载线程）∪ `BaseGameState.traverse` 捕获（运行期主线程）；其它线程只返回代理。
  2. **R-M25-8**：代理尺寸用 runtime manifest 的 `w/h`；非 POT 不补；`stringId/path` = 原 path；`Sprite` 缓存的 UV 必须与真图一致。
  3. **R-M25-9**：生产默认 off；Task 4 的 A/B 结果未出前不得改默认；回滚 = 属性/配置 false 或删 agent 行。
  4. **R-M25-10**：Task 2 内部 gate = Base lazy=true + 260mods lazy=true 的菜单、`runtime main captured`、`materialized>0`、`failed=0`、无 `Failed to load texture`/Verify；不过则停，不派 Task 3/4。
- **环境**：260mods agent-only；Base 运行期 mod；两侧 skip 文件 73,446 / 3,112；fix jar 已安装（`3e19ff86`）；G3 轮次 c4 73.1（离群）/p6 63.1/c5 64.1/p7 62.6。
- **Touches（写者表）**：
  - T2: `src/agent/java/hypernova/agent/textures/{LazyTextureConfig,LazyTextures,LazyTextureTransformer,LazyGameThreadTransformer,ProxyShape}.java`、`src/agent/java/hypernova/agent/HypernovaAgent.java`、`tests/agent/java/hypernova/*`、`tests/agent/java/hypernova/agent/textures/ProxyShapeTest.java`、`tests/agent/fixtures/...`
  - T3: `tools/install_manifest.py`、`tests/tools/test_install_manifest.py`、`tools/java/{build-mod,install-manifest,smoke-prepare,smoke-restore}.sh`
  - T4: `tools/smoke_run.py`、`tests/tools/test_smoke_run.py`、`tools/m25_ab.py`（新）、`tests/tools/test_m25_ab.py`（新）
  - T5: `docs/m25-results.md`、`技术笔记-纹理按需加载.md`、memory 文件
- **依赖**：T2 → T3 → T4 → T5；T2 内部 gate 失败即停。

---

### Task 2: 生产跳过 + 代理 + 按需物化 + 主线程捕获

**Files:**
- Modify: `src/agent/java/hypernova/agent/textures/LazyTextureConfig.java`（加 `enabled`）
- Create: `src/agent/java/hypernova/agent/textures/ProxyShape.java`
- Modify: `src/agent/java/hypernova/agent/textures/LazyTextures.java`（生产分支 + 物化 + 线程 + 形状）
- Create: `src/agent/java/hypernova/agent/textures/LazyGameThreadTransformer.java`
- Modify: `src/agent/java/hypernova/agent/HypernovaAgent.java`（注册 game-thread transformer；enabled||probe）
- Test: `tests/agent/java/hypernova/LazyTextureConfigTest.java`（更新）
- Test: `tests/agent/java/hypernova/LazyGameThreadTransformTest.java`（新）
- Test: `tests/agent/java/hypernova/agent/textures/ProxyShapeTest.java`（新）+ fixture
- Test: `tests/agent/java/hypernova/agent/textures/LazyTexturesEligibleTest.java`（新）
- Test: `tests/agent/java/hypernova/LazyTransformTest.java`（保持通过）

**Interfaces:**
- Consumes: `LazySkipIndex`（已有）、`AgentLog`（已有）、ASM 9.1（已有）、`install_manifest.py` 生成的 skip 文件。
- Produces:
  - `record LazyTextureConfig(boolean enabled, boolean probe, Path skipFile)`；`static LazyTextureConfig load()`；`public static LazyTextureConfig load(String enabledProp, String probeProp, String skipProp, Path configFile)`；`boolean configEnabled(Path)`（私有）
  - `final class ProxyShape`：`static ProxyShape resolve(Class<?>) throws Exception`、`Object newProxy(String,int,int) throws Exception`、`void copy(Object,Object) throws Exception`
  - `LazyTextures` 新增：`static boolean eligible(boolean,boolean,boolean,LazySkipIndex,String,String)`、`boolean shouldSkip(String,String)`、`Object lookup(String)`、`void captureMainThread(Object)`、`void probeResult(String,Object)`（已存在，现调用 `noteEngineHit`）、`void start(LazyTextureConfig)`（enabled||probe）
  - `final class LazyGameThreadTransformer implements ClassFileTransformer`（目标 `com/fs/starfarer/BaseGameState#traverse()Ljava/lang/String;`）

- [ ] **Step 1: 写失败测试（config / ProxyShape / game-thread / eligible）**

`LazyTextureConfigTest`（替换为 4 参 load 的新语义）：

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
    void defaultsOff() {
        LazyTextureConfig c = LazyTextureConfig.load(null, null, null, null);
        assertFalse(c.enabled());
        assertFalse(c.probe());
        assertNull(c.skipFile());
    }

    @Test
    void enabledFromProperty() {
        LazyTextureConfig c = LazyTextureConfig.load("true", null, "C:/x/skip.txt", null);
        assertTrue(c.enabled());
        assertFalse(c.probe());
        assertEquals(Path.of("C:/x/skip.txt"), c.skipFile());
    }

    @Test
    void probeFromProperty() {
        LazyTextureConfig c = LazyTextureConfig.load(null, "true", "C:/x/skip.txt", null);
        assertFalse(c.enabled());
        assertTrue(c.probe());
    }

    @Test
    void configFileEnablesLazy(@TempDir Path dir) throws Exception {
        Path cfg = dir.resolve("mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json");
        Files.createDirectories(cfg.getParent());
        Files.writeString(cfg, "{\"textures\":{\"lazy\":{\"enabled\":true}}}");
        LazyTextureConfig c = LazyTextureConfig.load(null, null, null, cfg);
        assertTrue(c.enabled());
        assertEquals(dir.resolve("mods/hypernova_infinite_engine/data/config/hypernova/lazy-skip-v1.txt"),
                c.skipFile());
    }

    @Test
    void badConfigDefaultsOff(@TempDir Path dir) throws Exception {
        Path cfg = dir.resolve("mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json");
        Files.createDirectories(cfg.getParent());
        Files.writeString(cfg, "{not json");
        LazyTextureConfig c = LazyTextureConfig.load(null, null, null, cfg);
        assertFalse(c.enabled());
    }
}
```

`ProxyShapeTest` + fixture（同包，字段名必须与真实 `Object` 一致）：

```java
package hypernova.agent.textures;

import org.junit.jupiter.api.Test;
import java.awt.Color;
import static org.junit.jupiter.api.Assertions.*;

class ProxyShapeTest {
    @Test
    void newProxySetsDimensionsUvAndIds() throws Exception {
        ProxyShape shape = ProxyShape.resolve(TextureObjectFixture.class);
        TextureObjectFixture o = (TextureObjectFixture) shape.newProxy("graphics/a.png", 40, 24);
        assertEquals(3553, o.target());
        assertEquals(0, o.id());
        assertEquals(40, o.width());
        assertEquals(24, o.height());
        assertEquals(40, o.imageWidth());
        assertEquals(24, o.imageHeight());
        assertEquals(1.0f, o.texWidth(), 1e-6);
        assertEquals(1.0f, o.texHeight(), 1e-6);
        assertEquals("graphics/a.png", o.stringId());
        assertEquals("graphics/a.png", o.path());
    }

    @Test
    void copyCopiesAllFields() throws Exception {
        ProxyShape shape = ProxyShape.resolve(TextureObjectFixture.class);
        TextureObjectFixture from = new TextureObjectFixture(3553, 7, "b");
        from.setWidth(11); from.setHeight(13); from.setImageWidth(11); from.setImageHeight(13);
        from.setColors(Color.RED, Color.GREEN, Color.BLUE);
        TextureObjectFixture to = (TextureObjectFixture) shape.newProxy("a", 1, 1);
        shape.copy(from, to);
        assertEquals(7, to.id());
        assertEquals(11, to.width());
        assertEquals(13, to.height());
        assertEquals(Color.RED, to.color0());
        assertEquals(Color.GREEN, to.color1());
        assertEquals(Color.BLUE, to.color2());
    }

    @Test
    void missingFieldFails() {
        assertThrows(Exception.class, () -> ProxyShape.resolve(MissingFixture.class));
    }

    static final class MissingFixture {
        MissingFixture(int a, int b, String c) { }
    }
}
```

`TextureObjectFixture`（测试夹具，字段名/类型与 `com.fs.graphics.Object` 一一对应；getter/setter 供测试）：

```java
package hypernova.agent.textures;

import java.awt.Color;

final class TextureObjectFixture {
    private int ö00000;
    private int ô00000;
    private int ÒO0000;
    private int Ô00000;
    private int oO0000;
    private int Object;
    private float for;
    private float ø00000;
    private String int;
    private String Ò00000;
    private boolean Ø00000;
    private Color Õ00000 = Color.white;
    private Color o00000 = Color.white;
    private Color public = Color.white;

    TextureObjectFixture(int target, int id, String path) {
        this.ö00000 = target;
        this.ô00000 = id;
        this.int = path;
    }

    int target() { return ö00000; }
    int id() { return ô00000; }
    int width() { return oO0000; }
    int height() { return Object; }
    int imageWidth() { return Ô00000; }
    int imageHeight() { return ÒO0000; }
    float texWidth() { return for; }
    float texHeight() { return ø00000; }
    String path() { return int; }
    String stringId() { return Ò00000; }
    Color color0() { return Õ00000; }
    Color color1() { return o00000; }
    Color color2() { return public; }

    void setWidth(int v) { oO0000 = v; }
    void setHeight(int v) { Object = v; }
    void setImageWidth(int v) { Ô00000 = v; }
    void setImageHeight(int v) { ÒO0000 = v; }
    void setColors(Color a, Color b, Color c) { Õ00000 = a; o00000 = b; public = c; }
}
```

`LazyGameThreadTransformTest`（合成 BaseGameState；只需断言注入调用）：

```java
package hypernova;

import hypernova.agent.textures.LazyGameThreadTransformer;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class LazyGameThreadTransformTest {
    private static final String TARGET = "com/fs/starfarer/BaseGameState";

    @Test
    void injectsCaptureIntoTraverse() {
        byte[] in = classBytes(TARGET, cv -> {
            MethodVisitor mv = cv.visitMethod(Opcodes.ACC_PUBLIC, "traverse", "()Ljava/lang/String;", null, null);
            mv.visitCode();
            mv.visitInsn(Opcodes.ACONST_NULL);
            mv.visitInsn(Opcodes.ARETURN);
            mv.visitMaxs(0, 0);
            mv.visitEnd();
        });
        byte[] out = new LazyGameThreadTransformer().transform(null, TARGET, null, null, in);
        assertNotNull(out);
        assertTrue(calls(out, "traverse", "hypernova/agent/textures/LazyTextures", "captureMainThread"));
    }

    @Test
    void missingTraverseIsUntouched() {
        byte[] in = classBytes(TARGET, cv -> {
            MethodVisitor mv = cv.visitMethod(Opcodes.ACC_PUBLIC, "other", "()V", null, null);
            mv.visitCode(); mv.visitInsn(Opcodes.RETURN); mv.visitMaxs(0, 0); mv.visitEnd();
        });
        assertNull(new LazyGameThreadTransformer().transform(null, TARGET, null, null, in));
    }

    @Test
    void malformedBytesReturnNull() {
        assertNull(new LazyGameThreadTransformer().transform(null, TARGET, null, null, new byte[]{1, 2, 3}));
    }

    private static byte[] classBytes(String name, java.util.function.Consumer<ClassVisitor> body) {
        ClassWriter cw = new ClassWriter(0);
        cw.visit(Opcodes.V17, Opcodes.ACC_PUBLIC, name, null, "java/lang/Object", null);
        body.accept(cw);
        cw.visitEnd();
        return cw.toByteArray();
    }

    private static boolean calls(byte[] bytes, String method, String owner, String name) {
        List<String> hits = new ArrayList<>();
        new ClassReader(bytes).accept(new ClassVisitor(Opcodes.ASM9) {
            @Override public MethodVisitor visitMethod(int a, String n, String d, String s, String[] e) {
                return new MethodVisitor(Opcodes.ASM9) {
                    @Override public void visitMethodInsn(int op, String o, String mn, String d, boolean itf) {
                        if (method.equals(n) && owner.equals(o) && name.equals(mn)) hits.add(mn);
                    }
                };
            }
        }, 0);
        return !hits.isEmpty();
    }
}
```

`LazyTexturesEligibleTest`（纯函数矩阵；不碰游戏类）：

```java
package hypernova.agent.textures;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class LazyTexturesEligibleTest {
    @Test
    void skipMatrix(@TempDir Path dir) throws Exception {
        Path f = dir.resolve("skip.txt");
        Files.writeString(f, "graphics/a.png\t10\t20\n");
        LazySkipIndex idx = LazySkipIndex.load(f);

        assertTrue(LazyTextures.eligible(true, false, false, idx, "TEXTURE", "graphics/a.png"));
        assertFalse(LazyTextures.eligible(false, false, false, idx, "TEXTURE", "graphics/a.png"));
        assertFalse(LazyTextures.eligible(true, true, false, idx, "TEXTURE", "graphics/a.png"));
        assertFalse(LazyTextures.eligible(true, false, true, idx, "TEXTURE", "graphics/a.png"));
        assertFalse(LazyTextures.eligible(true, false, false, idx, "TEXTURE_ALPHA_ADDER", "graphics/a.png"));
        assertFalse(LazyTextures.eligible(true, false, false, idx, "TEXTURE", "graphics/b.png"));
        assertFalse(LazyTextures.eligible(true, false, false, null, "TEXTURE", "graphics/a.png"));
    }
}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash tools/java/run-agent-tests.sh Lazy`
Expected: 编译失败（`ProxyShape` / `LazyGameThreadTransformer` 不存在；`LazyTextureConfig` 仍是 2 参 record）。

- [ ] **Step 3: 实现 `LazyTextureConfig.java`（完整替换）**

```java
package hypernova.agent.textures;

import org.json.JSONObject;

import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Lazy-texture configuration.
 *
 * <p>enabled: textures.lazy.enabled in hypernova.json (default false) or
 * -Dhypernova.textures.lazy=true. probe: -Dhypernova.textures.lazy.probe=true
 * (debug only; never skips). skipFile: -Dhypernova.textures.lazy.skipFile, or
 * <mod>/data/config/hypernova/lazy-skip-v1.txt.
 */
public record LazyTextureConfig(boolean enabled, boolean probe, Path skipFile) {

    public static LazyTextureConfig load() {
        return load(System.getProperty("hypernova.textures.lazy"),
                System.getProperty("hypernova.textures.lazy.probe"),
                System.getProperty("hypernova.textures.lazy.skipFile"),
                locateConfig());
    }

    public static LazyTextureConfig load(String enabledProp, String probeProp,
                                         String skipProp, Path configFile) {
        boolean enabled = enabledProp != null && !enabledProp.isBlank()
                ? Boolean.parseBoolean(enabledProp) : configEnabled(configFile);
        boolean probe = probeProp != null && Boolean.parseBoolean(probeProp);
        Path skip = skipProp == null || skipProp.isBlank() ? null : Path.of(skipProp);
        if (skip == null) {
            Path modRoot = modRoot(configFile);
            if (modRoot != null) {
                skip = modRoot.resolve("data/config/hypernova/lazy-skip-v1.txt");
            }
        }
        return new LazyTextureConfig(enabled, probe, skip);
    }

    private static boolean configEnabled(Path file) {
        if (file == null || !Files.isRegularFile(file)) return false;
        try {
            JSONObject root = new JSONObject(Files.readString(file));
            JSONObject textures = root.optJSONObject("textures");
            JSONObject lazy = textures == null ? null : textures.optJSONObject("lazy");
            return lazy != null && lazy.optBoolean("enabled", false);
        } catch (Throwable t) {
            return false; // bad config must not enable lazy loading
        }
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

- [ ] **Step 4: 实现 `ProxyShape.java`（完整）**

```java
package hypernova.agent.textures;

import java.awt.Color;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

/**
 * Reflection shape of com.fs.graphics.Object (0.98a-RC8). Field names are the
 * obfuscated names verified by javap; any rename/type change makes resolve()
 * throw and the lazy module fail open (disabled).
 *
 * Field semantics (see docs/m25-spike.md):
 *   ö00000 target, ô00000 GL id, ÒO0000 imageHeight, Ô00000 imageWidth,
 *   oO0000 width, Object height, for texWidth, ø00000 texHeight,
 *   int path, Ò00000 stringId, Ø00000 deferred, three Color fields.
 */
final class ProxyShape {
    private final Constructor<?> ctor;
    private final Field[] all;
    private final Field width;
    private final Field height;
    private final Field imageWidth;
    private final Field imageHeight;
    private final Field texWidth;
    private final Field texHeight;
    private final Field path;
    private final Field stringId;

    private ProxyShape(Constructor<?> ctor, Field[] all, Field width, Field height,
                       Field imageWidth, Field imageHeight, Field texWidth, Field texHeight,
                       Field path, Field stringId) {
        this.ctor = ctor;
        this.all = all;
        this.width = width;
        this.height = height;
        this.imageWidth = imageWidth;
        this.imageHeight = imageHeight;
        this.texWidth = texWidth;
        this.texHeight = texHeight;
        this.path = path;
        this.stringId = stringId;
    }

    static ProxyShape resolve(Class<?> type) throws Exception {
        Constructor<?> ctor = type.getDeclaredConstructor(int.class, int.class, String.class);
        ctor.setAccessible(true);
        Field target = field(type, "ö00000", int.class);
        Field id = field(type, "ô00000", int.class);
        Field imageHeight = field(type, "ÒO0000", int.class);
        Field imageWidth = field(type, "Ô00000", int.class);
        Field width = field(type, "oO0000", int.class);
        Field height = field(type, "Object", int.class);
        Field texWidth = field(type, "for", float.class);
        Field texHeight = field(type, "ø00000", float.class);
        Field path = field(type, "int", String.class);
        Field stringId = field(type, "Ò00000", String.class);
        Field deferred = field(type, "Ø00000", boolean.class);
        Field color0 = field(type, "Õ00000", Color.class);
        Field color1 = field(type, "o00000", Color.class);
        Field color2 = field(type, "public", Color.class);
        Field[] all = {target, id, imageHeight, imageWidth, width, height,
                texWidth, texHeight, path, stringId, deferred, color0, color1, color2};
        return new ProxyShape(ctor, all, width, height, imageWidth, imageHeight,
                texWidth, texHeight, path, stringId);
    }

    Object newProxy(String pathValue, int w, int h) throws Exception {
        Object proxy = ctor.newInstance(3553, 0, pathValue);
        width.setInt(proxy, w);
        height.setInt(proxy, h);
        imageWidth.setInt(proxy, w);
        imageHeight.setInt(proxy, h);
        texWidth.setFloat(proxy, 1.0f);
        texHeight.setFloat(proxy, 1.0f);
        path.set(proxy, pathValue);
        stringId.set(proxy, pathValue);
        return proxy;
    }

    void copy(Object from, Object to) throws Exception {
        for (Field field : all) field.set(to, field.get(from));
    }

    private static Field field(Class<?> type, String name, Class<?> expected) throws Exception {
        Field field = type.getDeclaredField(name);
        if (field.getType() != expected) {
            throw new NoSuchFieldException(name + " has type " + field.getType());
        }
        field.setAccessible(true);
        return field;
    }
}
```

- [ ] **Step 5: 实现 `LazyGameThreadTransformer.java`（完整）**

```java
package hypernova.agent.textures;

import hypernova.agent.AgentLog;
import org.objectweb.asm.*;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

/**
 * Captures the runtime main thread at BaseGameState.traverse(). BaseGameState
 * is not a FR merge target (only constant-pool sync), so the injected call
 * survives. GLLauncher states are ignored by LazyTextures.captureMainThread.
 */
public final class LazyGameThreadTransformer implements ClassFileTransformer {
    public static final String TARGET = "com/fs/starfarer/BaseGameState";
    private static final String METHOD = "traverse";
    private static final String DESC = "()Ljava/lang/String;";
    private static final String HOOK = "hypernova/agent/textures/LazyTextures";

    @Override
    public byte[] transform(ClassLoader loader, String className, Class<?> redefined,
                            ProtectionDomain protectionDomain, byte[] bytes) {
        if (className == null || !TARGET.equals(className) || redefined != null || bytes == null) return null;
        try {
            ClassReader reader = new ClassReader(bytes);
            ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
            boolean[] patched = {false};
            ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
                @Override
                public MethodVisitor visitMethod(int access, String name, String desc,
                                                 String signature, String[] exceptions) {
                    MethodVisitor mv = super.visitMethod(access, name, desc, signature, exceptions);
                    if (!METHOD.equals(name) || !DESC.equals(desc)) return mv;
                    patched[0] = true;
                    return new MethodVisitor(Opcodes.ASM9, mv) {
                        @Override
                        public void visitCode() {
                            super.visitCode();
                            super.visitVarInsn(Opcodes.ALOAD, 0);
                            super.visitMethodInsn(Opcodes.INVOKESTATIC, HOOK,
                                    "captureMainThread", "(Ljava/lang/Object;)V", false);
                        }
                    };
                }
            };
            reader.accept(visitor, 0);
            if (!patched[0]) {
                AgentLog.info("lazy: BaseGameState.traverse missing; runtime main-thread capture disabled");
                return null;
            }
            AgentLog.info("lazy: runtime main-thread capture hook added to BaseGameState.traverse");
            return writer.toByteArray();
        } catch (Throwable t) {
            AgentLog.fail("lazy: BaseGameState transform failed; capture disabled", t);
            return null;
        }
    }
}
```

- [ ] **Step 6: 实现生产版 `LazyTextures.java`（完整替换；探针方法保留）**

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
 * M2.5 probe + production lazy-texture state.
 *
 * <p>Probe mode only counts; every queued texture still calls loadTextureAsync.
 * Production mode skips non-L1 queue entries, registers a proxy Object with the
 * manifest dimensions, and materializes it on the first lookup from the loading
 * thread or the runtime main thread. Any shape/reflection failure disables the
 * module (fail-open); materialize failures keep the proxy and are logged.
 */
public final class LazyTextures {
    // ---- probe counters (Task 1) ----
    private static final AtomicLong QUEUE_TOTAL = new AtomicLong();
    private static final AtomicLong QUEUE_WOULD_SKIP = new AtomicLong();
    private static final AtomicLong LOOKUP_TOTAL = new AtomicLong();
    private static final AtomicLong DEMAND_DISTINCT = new AtomicLong();
    private static final Map<String, AtomicLong> TYPES = new ConcurrentHashMap<>();
    private static final Map<String, Long> DEMAND_FIRST = new ConcurrentHashMap<>();
    private static final AtomicBoolean WIRED = new AtomicBoolean();
    private static final AtomicBoolean SUMMARY_STARTED = new AtomicBoolean();
    private static final AtomicBoolean DEGRADED = new AtomicBoolean();
    private static final Set<String> QUEUED_SKIP = ConcurrentHashMap.newKeySet();
    private static final Set<String> DEMAND_QUEUED = ConcurrentHashMap.newKeySet();
    private static final Set<String> DEMAND_HIT = ConcurrentHashMap.newKeySet();
    private static final Set<String> DEMAND_MISS = ConcurrentHashMap.newKeySet();

    // ---- production state ----
    private static final AtomicLong LAZY_SKIPPED = new AtomicLong();
    private static final AtomicLong LAZY_MATERIALIZED = new AtomicLong();
    private static final AtomicLong LAZY_DEFERRED = new AtomicLong();
    private static final AtomicLong LAZY_FAILED = new AtomicLong();
    private static final Map<String, ProxyEntry> PROXIES = new ConcurrentHashMap<>();

    private static volatile boolean enabled;
    private static volatile boolean probe;
    private static volatile boolean disabled;
    private static volatile ProxyShape proxyShape;
    private static volatile boolean shapeResolved;

    private static volatile Method syncMethod;
    private static volatile Object loaderSingleton;
    private static volatile Field pathCacheField;
    private static volatile boolean loaderResolved;

    private static volatile Thread runtimeMain;
    private static volatile Thread loadingThreadField;
    private static volatile boolean loadingThreadResolved;

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
        enabled = config.enabled();
        probe = config.probe();
        if (!enabled && !probe) return;
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
        AgentLog.info("lazy: started enabled=" + enabled + " probe=" + probe + "; skipFile=" + skipFile);
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

    public static void queue(Object loader, String type, String path) throws Throwable {
        try {
            QUEUE_TOTAL.incrementAndGet();
            TYPES.computeIfAbsent(type == null ? "" : type, k -> new AtomicLong()).incrementAndGet();
            if (WIRED.compareAndSet(false, true)) {
                AgentLog.info("lazy probe: lambda wired (first queue: type=" + type + ", path=" + path + ")");
            }
            LazySkipIndex idx = index;
            if (idx != null && idx.contains(path)) {
                QUEUED_SKIP.add(path);
                long n = QUEUE_WOULD_SKIP.incrementAndGet();
                if (n <= 20) AgentLog.info("lazy probe: would-skip " + path);
            }
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: counter failed; continuing", t);
        }
        if (shouldSkip(type, path)) {
            if (registerProxy(path)) {
                LAZY_SKIPPED.incrementAndGet();
                return;
            }
            AgentLog.fail("lazy: proxy unavailable for " + path + "; loading normally",
                    new IllegalStateException("proxy registration failed"));
        }
        loadAsync(loader, type, path);
    }

    static boolean eligible(boolean enabled, boolean probe, boolean disabled,
                            LazySkipIndex index, String type, String path) {
        if (!enabled || probe || disabled) return false;
        if ("TEXTURE_ALPHA_ADDER".equals(type)) return false;
        return index != null && index.contains(path);
    }

    public static boolean shouldSkip(String type, String path) {
        try {
            if (!eligible(enabled, probe, disabled, index, type, path)) return false;
            return ensureShape();
        } catch (Throwable t) {
            AgentLog.fail("lazy: skip decision failed for " + path + "; loading normally", t);
            return false;
        }
    }

    private static boolean registerProxy(String path) {
        try {
            if (PROXIES.containsKey(path)) return true;
            LazySkipIndex idx = index;
            LazySkipIndex.Dim dim = idx == null ? null : idx.get(path);
            ProxyShape shape = proxyShape;
            if (dim == null || shape == null) return false;
            Object obj = shape.newProxy(path, dim.w(), dim.h());
            ProxyEntry prev = PROXIES.putIfAbsent(path, new ProxyEntry(path, dim.w(), dim.h(), obj));
            if (prev == null && PROXIES.size() <= 20) {
                AgentLog.info("lazy: proxy " + path + " " + dim.w() + "x" + dim.h());
            }
            return true;
        } catch (Throwable t) {
            AgentLog.fail("lazy: proxy registration failed for " + path + "; loading normally", t);
            return false;
        }
    }

    public static Object lookup(String path) {
        try {
            ProxyEntry e = PROXIES.get(path);
            if (e == null) return null;
            if (!e.ready) {
                if (canMaterialize()) {
                    materialize(e);
                } else {
                    LAZY_DEFERRED.incrementAndGet();
                }
            }
            return e.obj;
        } catch (Throwable t) {
            AgentLog.fail("lazy: lookup failed for " + path, t);
            return null;
        }
    }

    private static boolean canMaterialize() {
        Thread t = Thread.currentThread();
        if (t == runtimeMain) return true;
        Thread loading = loadingThread();
        return loading != null && t == loading;
    }

    private static Thread loadingThread() {
        Thread t = loadingThreadField;
        if (t == null && !loadingThreadResolved) {
            synchronized (LazyTextures.class) {
                t = loadingThreadField;
                if (t == null && !loadingThreadResolved) {
                    try {
                        Class<?> fileLoader = Class.forName("com.fs.util.C",
                                false, LazyTextures.class.getClassLoader());
                        Method getInstance = fileLoader.getDeclaredMethod("Ó00000");
                        getInstance.setAccessible(true);
                        Object instance = getInstance.invoke(null);
                        Field field = fileLoader.getDeclaredField("mainThread");
                        field.setAccessible(true);
                        t = (Thread) field.get(instance);
                        loadingThreadField = t;
                    } catch (Throwable t2) {
                        AgentLog.info("lazy: FileLoader.mainThread unavailable; loading-thread materialize disabled");
                    } finally {
                        loadingThreadResolved = true;
                    }
                }
            }
        }
        return t;
    }

    public static void captureMainThread(Object state) {
        try {
            if (runtimeMain != null || state == null) return;
            String name = state.getClass().getName();
            if (name.contains("launcher") || name.contains("Launcher")) return;
            runtimeMain = Thread.currentThread();
            AgentLog.info("lazy: runtime main thread captured " + runtimeMain.getName() + " from " + name);
        } catch (Throwable t) {
            AgentLog.fail("lazy: main-thread capture failed", t);
        }
    }

    private static void materialize(ProxyEntry e) {
        synchronized (e) {
            if (e.ready || e.failed) return;
            long t0 = System.nanoTime();
            try {
                Object real = syncLoad(e.path);
                ProxyShape shape = proxyShape;
                if (shape == null) throw new IllegalStateException("proxy shape unavailable");
                shape.copy(real, e.obj);
                e.ready = true;
                putPathCache(e.path, e.obj);
                long ms = (System.nanoTime() - t0) / 1_000_000L;
                long n = LAZY_MATERIALIZED.incrementAndGet();
                if (n <= 20 || ms >= 50) {
                    AgentLog.info("lazy: materialized " + e.path + " " + e.w + "x" + e.h + " in " + ms + " ms");
                }
            } catch (Throwable t) {
                long attempts = e.attempts.incrementAndGet();
                if (attempts >= 2) e.failed = true;
                LAZY_FAILED.incrementAndGet();
                AgentLog.fail("lazy: materialize failed for " + e.path + " (attempt " + attempts + ")", t);
            }
        }
    }

    private static Object syncLoad(String path) throws Throwable {
        ensureLoader();
        Method sync = syncMethod;
        Object loader = loaderSingleton;
        if (sync == null || loader == null) throw new IllegalStateException("sync loader unavailable");
        try {
            return sync.invoke(loader, null, path, 3553, 6408, 9729, 9729, false);
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            throw cause == null ? e : cause;
        }
    }

    @SuppressWarnings("unchecked")
    private static void putPathCache(String path, Object obj) {
        Field field = pathCacheField;
        Object loader = loaderSingleton;
        if (field == null || loader == null) return;
        try {
            Object value = field.get(loader);
            if (value instanceof Map<?, ?>) {
                ((Map<Object, Object>) value).put(path, obj);
            }
        } catch (Throwable t) {
            AgentLog.fail("lazy: path cache put failed for " + path, t);
        }
    }

    private static boolean ensureShape() {
        if (shapeResolved) return !disabled;
        synchronized (LazyTextures.class) {
            if (shapeResolved) return !disabled;
            try {
                Class<?> obj = Class.forName("com.fs.graphics.Object");
                proxyShape = ProxyShape.resolve(obj);
                ensureLoader();
                if (syncMethod == null || loaderSingleton == null) {
                    throw new IllegalStateException("TextureLoader sync path unavailable");
                }
                AgentLog.info("lazy: shape ok; proxy + sync loader resolved");
            } catch (Throwable t) {
                disabled = true;
                AgentLog.fail("lazy: shape gate failed; lazy skip disabled", t);
            } finally {
                shapeResolved = true;
            }
            return !disabled;
        }
    }

    private static void ensureLoader() throws Exception {
        if (loaderResolved) {
            if (syncMethod == null || loaderSingleton == null) throw new IllegalStateException("loader shape");
            return;
        }
        synchronized (LazyTextures.class) {
            if (loaderResolved) {
                if (syncMethod == null || loaderSingleton == null) throw new IllegalStateException("loader shape");
                return;
            }
            try {
                Class<?> objClass = Class.forName("com.fs.graphics.Object");
                Class<?> repo = Class.forName("com.fs.graphics.oOoO");
                Method getLoader = repo.getDeclaredMethod("String");
                getLoader.setAccessible(true);
                Object loader = getLoader.invoke(null);
                if (loader == null) throw new IllegalStateException("TextureLoader singleton null");
                Method sync = null;
                for (Method method : loader.getClass().getDeclaredMethods()) {
                    if (!"o00000".equals(method.getName()) || method.getParameterCount() != 7) continue;
                    Class<?>[] p = method.getParameterTypes();
                    if (p[0] == objClass && p[1] == String.class
                            && p[2] == int.class && p[3] == int.class
                            && p[4] == int.class && p[5] == int.class
                            && p[6] == boolean.class) {
                        sync = method;
                        break;
                    }
                }
                if (sync == null) throw new NoSuchMethodException("TextureLoader.o00000 7-arg");
                sync.setAccessible(true);
                try {
                    Field cache = loader.getClass().getDeclaredField("ÔO0000");
                    if (!Map.class.isAssignableFrom(cache.getType())) {
                        throw new NoSuchFieldException("ÔO0000 not a Map");
                    }
                    cache.setAccessible(true);
                    pathCacheField = cache;
                } catch (Throwable t) {
                    AgentLog.info("lazy: TextureLoader path cache unavailable; proxy reuse disabled");
                }
                syncMethod = sync;
                loaderSingleton = loader;
                AgentLog.info("lazy: sync loader resolved on " + loader.getClass().getName());
            } finally {
                loaderResolved = true;
            }
        }
    }

    private static void loadAsync(Object loader, String type, String path) throws Throwable {
        Method m = loadAsyncMethod;
        if (m == null && !loadResolved) {
            synchronized (LazyTextures.class) {
                m = loadAsyncMethod;
                if (m == null && !loadResolved) {
                    try {
                        m = loader.getClass().getDeclaredMethod("loadTextureAsync", String.class, String.class);
                        m.setAccessible(true);
                        loadAsyncMethod = m;
                        AgentLog.info("lazy probe: loadTextureAsync resolved on " + loader.getClass().getName());
                    } catch (Throwable t) {
                        DEGRADED.set(true);
                        AgentLog.fail("lazy probe: loadTextureAsync missing; queued texture skipped", t);
                    } finally {
                        loadResolved = true;
                    }
                }
            }
        }
        if (m == null) return;
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

    public static void probeLookup(String path) {
        try {
            LOOKUP_TOTAL.incrementAndGet();
            LazySkipIndex idx = index;
            if (idx == null || !idx.contains(path)) return;
            if (DEMAND_FIRST.putIfAbsent(path, System.nanoTime()) == null) {
                long n = DEMAND_DISTINCT.incrementAndGet();
                if (n <= 20) AgentLog.info("lazy probe: demand " + path);
            }
            if (QUEUED_SKIP.contains(path)) DEMAND_QUEUED.add(path);
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: lookup counter failed; continuing", t);
        }
    }

    public static void probeResult(String path, Object value) {
        try {
            if (path == null || !QUEUED_SKIP.contains(path)) return;
            if (value != null) {
                DEMAND_HIT.add(path);
                noteEngineHit(path, value);
            } else {
                DEMAND_MISS.add(path);
            }
        } catch (Throwable t) {
            AgentLog.fail("lazy probe: result counter failed; continuing", t);
        }
    }

    private static void noteEngineHit(String path, Object value) {
        try {
            if (value == null) return;
            ProxyEntry e = PROXIES.get(path);
            if (e == null || e.ready || e.obj == value) return;
            synchronized (e) {
                if (e.ready || e.obj == value) return;
                ProxyShape shape = proxyShape;
                if (shape == null) return;
                shape.copy(value, e.obj);
                e.ready = true;
                long n = LAZY_MATERIALIZED.incrementAndGet();
                if (n <= 20) AgentLog.info("lazy: materialized via engine hit " + path);
            }
        } catch (Throwable t) {
            LAZY_FAILED.incrementAndGet();
            AgentLog.fail("lazy: engine-hit copy failed for " + path, t);
        }
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
            Thread lt = loadingThread();
            AgentLog.info("lazy probe: summary queue=" + QUEUE_TOTAL.get()
                    + " wouldSkip=" + QUEUE_WOULD_SKIP.get()
                    + " lookups=" + LOOKUP_TOTAL.get()
                    + " demand=" + DEMAND_DISTINCT.get()
                    + " index=" + (idx == null ? "none" : idx.size())
                    + " types=" + types()
                    + " queuedSkip=" + QUEUED_SKIP.size()
                    + " demandQueued=" + DEMAND_QUEUED.size()
                    + " hits=" + DEMAND_HIT.size()
                    + " misses=" + DEMAND_MISS.size()
                    + " degraded=" + (DEGRADED.get() ? 1 : 0)
                    + " skipped=" + LAZY_SKIPPED.get()
                    + " proxies=" + PROXIES.size()
                    + " materialized=" + LAZY_MATERIALIZED.get()
                    + " deferred=" + LAZY_DEFERRED.get()
                    + " failed=" + LAZY_FAILED.get()
                    + " disabled=" + (disabled ? 1 : 0)
                    + " main=" + (runtimeMain == null ? "none" : runtimeMain.getName())
                    + " loading=" + (lt == null ? "none" : lt.getName()));
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

    private static final class ProxyEntry {
        final String path;
        final int w;
        final int h;
        final Object obj;
        volatile boolean ready;
        volatile boolean failed;
        final AtomicLong attempts = new AtomicLong();

        ProxyEntry(String path, int w, int h, Object obj) {
            this.path = path;
            this.w = w;
            this.h = h;
            this.obj = obj;
        }
    }
}
```

- [ ] **Step 7: 接线 `HypernovaAgent` + 构建**

在 lazy 块中把 `if (lazy.probe())` 改为 `if (lazy.enabled() || lazy.probe())`，注册两个 transformer；import `LazyGameThreadTransformer`：

```java
            try {
                LazyTextureConfig lazy = LazyTextureConfig.load();
                if (lazy.enabled() || lazy.probe()) {
                    if (!frPresent()) {
                        AgentLog.info("lazy: FR missing; lazy textures disabled");
                    } else {
                        instrumentation.addTransformer(new LazyTextureTransformer(), false);
                        instrumentation.addTransformer(new LazyGameThreadTransformer(), false);
                        LazyTextures.start(lazy);
                        AgentLog.info("lazy: transformers registered");
                    }
                }
            } catch (Throwable t) {
                AgentLog.fail("lazy init failed; continuing", t);
            }
```

Run: `bash tools/java/build-agent.sh` → `OK`.
Run: `bash tools/java/run-agent-tests.sh Lazy` → **17/17**（`LazySkipIndex` 3 + `LazyTextureConfig` 5 + `LazyTransform` 5 + `LazyGameThreadTransform` 3 + `LazyTexturesEligible` 1）。
Run: `bash tools/java/run-agent-tests.sh Proxy` → **3/3**（`ProxyShapeTest`；类名不含 Lazy，必须单独过滤或跑全量）。
Run: `bash tools/java/run-tests.sh` → 103/103。
Run: `python -I -m pytest tests/tools -q` → 既有 2 stale + 256 passed。

- [ ] **Step 8: 生成 skip 文件 + 装 agent（若 Task 3 未做，先用 Task 1 工具）**

```bash
python -I tools/gen_lazy_skip.py --manifest Starsector-098-260mods/mods/hypernova_infinite_engine/data/config/hypernova/manifest-v1.json --out Starsector-098-260mods/mods/hypernova_infinite_engine/data/config/hypernova/lazy-skip-v1.txt
python -I tools/gen_lazy_skip.py --manifest Starsector-098-Base/mods/hypernova_infinite_engine/data/config/hypernova/manifest-v1.json --out Starsector-098-Base/mods/hypernova_infinite_engine/data/config/hypernova/lazy-skip-v1.txt
python -I tools/install_agent.py --game Starsector-098-Base --env base --action install
python -I tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite --action install
```

Expected：260mods skip=73,446；Base skip=3,112；jar 已刷新。

- [ ] **Step 9: Task 2 内部 gate（硬门禁；不过则停）**

Base：

```bash
python -I tools/smoke_run.py --profile base --rounds 1 --wait-menu 300 \
  --jvm-arg=-Dhypernova.textures.lazy=true \
  --json-out build/m25/internal-base-lazy.json
cp Starsector-098-Base/starsector-core/starsector.log build/m25/logs/base-starsector-lazy.log
cp Starsector-098-Base/saves/hypernova/scripts-agent.log build/m25/logs/base-agent-lazy.log
```

260mods：

```bash
python -I tools/smoke_run.py --profile miko-lite --rounds 1 --wait-menu 300 \
  --jvm-arg=-Dhypernova.textures.lazy=true \
  --json-out build/m25/internal-260-lazy.json
cp Starsector-098-260mods/starsector-core/starsector.log build/m25/logs/260-starsector-lazy.log
cp Starsector-098-260mods/saves/hypernova/scripts-agent.log build/m25/logs/260-agent-lazy.log
```

检查（缺一即内部 gate FAIL）：

1. `starsector.log`：0 `Failed to load texture`、0 `VerifyError`/`ClassFormatError`；两轮都到主菜单。
2. agent 日志（最后一个 premain 之后）：
   - `lazy: started enabled=true probe=false`；
   - `lazy: shape ok; proxy + sync loader resolved`；
   - `lazy: runtime main thread captured ... from ...State`（**若没有 → FAIL**）；
   - `lazy: proxy ...` 至少若干条；
   - `lazy: materialized ...` 至少若干条；
   - summary：`skipped>0`、`proxies>0`、`materialized>0`、`failed=0`、`disabled=0`、`degraded=0`；
   - 0 `ERROR`。
3. Base 菜单约 10–13 s；260mods 菜单有值（具体时间不在本任务判定；Task 4 做 A/B）。
4. **人工目检**（用户或 controller）：Base 主菜单正常；若加载存档/进战斗，无白块/错位（Task 4 再做强校验）。

如果 `runtime main thread captured` 缺失：`BaseGameState.traverse` 注入没生效/被 FR 改掉 → 停，按 Review Focus 1 查；不要改默认/继续 Task 3。
如果 `materialized=0`：`canMaterialize` 未命中 → 查 `loading=`/`main=` 名称与 `lookup` 调用线程；停。
如果 `disabled=1`：形状 gate 失败 → 看 ERROR 的 `shape gate failed`；停。

- [ ] **Step 10: 提交**

```bash
git add src/agent/java/hypernova/agent/textures/LazyTextureConfig.java \
        src/agent/java/hypernova/agent/textures/ProxyShape.java \
        src/agent/java/hypernova/agent/textures/LazyTextures.java \
        src/agent/java/hypernova/agent/textures/LazyGameThreadTransformer.java \
        src/agent/java/hypernova/agent/HypernovaAgent.java \
        tests/agent/java/hypernova/LazyTextureConfigTest.java \
        tests/agent/java/hypernova/LazyGameThreadTransformTest.java \
        tests/agent/java/hypernova/agent/textures/ProxyShapeTest.java \
        tests/agent/java/hypernova/agent/textures/TextureObjectFixture.java \
        tests/agent/java/hypernova/agent/textures/LazyTexturesEligibleTest.java
git commit -m "feat(m25): skip non-L1 startup textures and materialize proxies on demand" \
    -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

报告：写 `task-2-report.md`（内部 gate 数字、captures、materialized、菜单、失败/偏差）。

---

### Task 3: 安装集成（skip 文件 + 发行包 manifest）

**Files:**
- Modify: `tools/install_manifest.py`（生成 skip 文件）
- Modify: `tests/tools/test_install_manifest.py`
- Modify: `tools/java/install-manifest.sh`（接 `install_manifest.py`）
- Modify: `tools/java/build-mod.sh`（发行包用 M2 manifest + skip 文件）
- Modify: `tools/java/smoke-prepare.sh`、`tools/java/smoke-restore.sh`（避免双跑；验证 skip 文件）

**Interfaces:**
- Consumes: `gen_lazy_skip.build_skip/write_atomic`（已有）、`install()`（已有）。
- Produces: `InstallResult.skip_file: Path | None`、`InstallResult.skip_count: int`；`install_manifest.py` 在 manifest 同目录写 `lazy-skip-v1.txt`（Critical 时不写）。

- [ ] **Step 1: 写失败测试**

```python
def test_install_writes_lazy_skip_file(mini_game):
    _seed_core(mini_game)
    result = install(mini_game)
    assert result.skip_file == result.out.parent / "lazy-skip-v1.txt"
    assert result.skip_file.is_file()
    lines = result.skip_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == result.skip_count
    assert all(len(line.split("\t")) == 3 for line in lines)
    # L1 path must not be in the skip file
    l1 = {e["path"] for e in result.runtime["layers"]["L1"]}
    assert all(line.split("\t")[0] not in l1 for line in lines)


def test_critical_install_does_not_write_skip_file(mini_game):
    _seed_core(mini_game)
    result = install(mini_game, max_l1=1)
    assert any(f.severity == "Critical" for f in result.findings)
    assert result.skip_file is None
    assert result.skip_count == 0
```

- [ ] **Step 2: 跑失败**

Run: `python -I -m pytest tests/tools/test_install_manifest.py -q`
Expected: FAIL（`InstallResult` 无 `skip_file`）。

- [ ] **Step 3: 实现安装器改动**

在 `tools/install_manifest.py`：

```python
from gen_lazy_skip import build_skip, write_atomic  # noqa: E402

@dataclass(frozen=True)
class InstallResult:
    full: dict
    runtime: dict
    out: Path
    findings: list[Finding]
    skip_file: Path | None = None
    skip_count: int = 0
```

在 `install()` 里、`if not critical:` **之前**先初始化（否则 critical 分支的 return 会 UnboundLocalError）：

```python
    skip_file: Path | None = None
    skip_count = 0
```

在 `install()` 的 `if not critical:` 块内、manifest 原子写之后加：

```python
        skip_rows, _skip_stats = build_skip(runtime)
        skip_target = target.parent / "lazy-skip-v1.txt"
        write_atomic(skip_target, skip_rows)
        skip_file = skip_target
        skip_count = len(skip_rows)
```

`install()` 返回 `InstallResult(..., skip_file=skip_file, skip_count=skip_count)`；`main()` 打印新增 `skip=` 与 `skip_file=`。

- [ ] **Step 4: 跑测试**

Run: `python -I -m pytest tests/tools/test_install_manifest.py -q`
Expected: all passed。

- [ ] **Step 5: 接发行包与 smoke 脚本**

`tools/java/install-manifest.sh`：删除 M0 + `trim_manifest.py` 路径，改为：

```bash
python -I "$ROOT/tools/install_manifest.py" --game-root "$GAME_ROOT"
echo "installed: $GAME_ROOT/mods/hypernova_infinite_engine/data/config/hypernova/{manifest-v1.json,lazy-skip-v1.txt}"
```

（保留原有的 `data/` 拷贝与顺序；manifest/skip 由安装器最后写。）

`tools/java/build-mod.sh`：把 `MANIFEST_SRC="$ROOT_W/build/m0/$ENV/manifest-v1.json"` + `trim_manifest.py` 段替换为：

```bash
BASE_GAME="$ROOT_W/Starsector-098-Base"
python -I "$ROOT_W/tools/install_manifest.py" --game-root "$BASE_GAME" | tail -5
MANIFEST_INSTALLED="$BASE_GAME/mods/hypernova_infinite_engine/data/config/hypernova/manifest-v1.json"
SKIP_INSTALLED="$BASE_GAME/mods/hypernova_infinite_engine/data/config/hypernova/lazy-skip-v1.txt"
MANIFEST_DIST="$ROOT/dist/manifest-v1.json"
cp "$MANIFEST_INSTALLED" "$MANIFEST_DIST"
cp "$MANIFEST_INSTALLED" "$OUT/hypernova-manifest-v1.json"
```

打包目录新增：

```bash
cp "$SKIP_INSTALLED" "$MODDIR/data/config/hypernova/lazy-skip-v1.txt"
```

zip 断言增加：

```bash
if ! (cd "$OUT" && jar --list --file hypernova-0.1.0.zip) \
    | grep -qx 'data/config/hypernova/lazy-skip-v1.txt'; then
  echo "FATAL: zip 缺少 data/config/hypernova/lazy-skip-v1.txt" >&2
  exit 1
fi
```

`tools/java/smoke-prepare.sh` / `smoke-restore.sh`：`install-manifest.sh` 已改为 M2 后，删除紧随其后的重复 `install_manifest.py` 调用（或保留幂等调用；**不能**再解释为“install-manifest 装的是 M0”），并断言两侧 skip 文件存在。

- [ ] **Step 6: 验证**

```bash
python -I tools/install_manifest.py --game-root Starsector-098-Base | tail -5
ls -l Starsector-098-Base/mods/hypernova_infinite_engine/data/config/hypernova/lazy-skip-v1.txt
bash tools/java/build-mod.sh
python - <<'PY'
import json, zipfile
with zipfile.ZipFile('build/java/hypernova-0.1.0.zip') as z:
    names = set(z.namelist())
    assert 'data/config/hypernova/manifest-v1.json' in names
    assert 'data/config/hypernova/lazy-skip-v1.txt' in names
    m = json.loads(z.read('data/config/hypernova/manifest-v1.json'))
    print('manifest L1/L2/L3 =', len(m['layers']['L1']), len(m['layers']['L2']), len(m['layers']['L3']))
    print('skip lines =', z.read('data/config/hypernova/lazy-skip-v1.txt').decode().count('\n'))
PY
```

Expected：Base L1 185 / L2 509 / L3 2,612；skip 3,112；zip 含两文件。

- [ ] **Step 7: 提交**

```bash
git add tools/install_manifest.py tests/tools/test_install_manifest.py \
        tools/java/install-manifest.sh tools/java/build-mod.sh \
        tools/java/smoke-prepare.sh tools/java/smoke-restore.sh
git commit -m "feat(m25): generate the lazy skip file from the installer and ship the M2 manifest" \
    -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: A/B + VRAM + 正确性

**Files:**
- Modify: `tools/smoke_run.py`（working set / GPU 采样）
- Test: `tests/tools/test_smoke_run.py`
- Create: `tools/m25_ab.py`、`tests/tools/test_m25_ab.py`

**Interfaces:**
- Produces: `smoke_run.py` 结果新增 `ws_menu_mb`、`ws_exit_mb`、`gpu_menu_mb`；`tools/m25_ab.py --profile --rounds --out` 运行交错 C/T、输出中位/计数 JSON。

- [ ] **Step 1: 写失败测试**

```python
def test_smoke_process_memory_reads_self():
    from smoke_run import process_memory_mb
    assert process_memory_mb(os.getpid()) > 0


def test_lazy_stats_parses_summary():
    from m25_ab import lazy_stats_from_text
    text = ("2026-11-01T00:00:00Z INFO hypernova agent premain\n"
            "2026-11-01T00:01:00Z INFO lazy probe: summary queue=52604 wouldSkip=45785 "
            "lookups=1 demand=1 index=73446 types={} queuedSkip=45785 demandQueued=1 hits=1 "
            "misses=0 degraded=0 skipped=45785 proxies=45785 materialized=7325 deferred=0 "
            "failed=0 disabled=0 main=Thread-3 loading=Thread-7-FR-Main-Loader\n")
    s = lazy_stats_from_text(text)
    assert s["skipped"] == 45785 and s["materialized"] == 7325 and s["failed"] == 0
```

- [ ] **Step 2: 实现 `smoke_run.py` 采样**

在 `if sys.platform == "win32":` 的 ctypes 区加 `PROCESS_MEMORY_COUNTERS` 与 `process_memory_mb(pid)`（`psapi.GetProcessMemoryInfo`；失败返回 None）；`one_round` 在菜单后/退出前各采样一次；结果 dict 加 `ws_menu_mb`/`ws_exit_mb`；加 `gpu_memory_mb()`（`nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits`，无命令返回 None）并在菜单后采样 `gpu_menu_mb`。

- [ ] **Step 3: 实现 `tools/m25_ab.py`**

```python
#!/usr/bin/env python3
"""Interleaved control/treatment A/B for M2.5 lazy textures (same boot, warm)."""
import argparse, json, re, subprocess, sys
from pathlib import Path

LAZY_RE = re.compile(
    r"lazy probe: summary .*? skipped=(\d+) proxies=(\d+) materialized=(\d+) "
    r"deferred=(\d+) failed=(\d+) disabled=(\d+)")


def lazy_stats_from_text(text: str) -> dict:
    lines = text.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if "hypernova agent premain" in line:
            start = i
    out = {}
    for line in lines[start:]:
        m = LAZY_RE.search(line)
        if m:
            out = {"skipped": int(m.group(1)), "proxies": int(m.group(2)),
                   "materialized": int(m.group(3)), "deferred": int(m.group(4)),
                   "failed": int(m.group(5)), "disabled": int(m.group(6))}
    return out


def run_round(profile: str, lazy: bool, out: str, wait: float) -> dict:
    arg = "-Dhypernova.textures.lazy=" + ("true" if lazy else "false")
    cmd = [sys.executable, "-I", "tools/smoke_run.py", "--profile", profile,
           "--rounds", "1", "--wait-menu", str(wait), "--jvm-arg=" + arg,
           "--json-out", out]
    subprocess.run(cmd, check=True)
    return json.loads(Path(out).read_text(encoding="utf-8"))[0]


def median(values):
    values = sorted(values)
    n = len(values)
    if not n:
        return None
    return values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="miko-lite")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--wait-menu", type=float, default=300)
    ap.add_argument("--agent-log", default="")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    rows = []
    for i in range(1, args.rounds + 1):
        c = run_round(args.profile, False, f"build/m25/ab-c{i}.json", args.wait_menu)
        t = run_round(args.profile, True, f"build/m25/ab-t{i}.json", args.wait_menu)
        agent = Path(args.agent_log) if args.agent_log else \
            Path(f"Starsector-098-260mods/saves/hypernova/scripts-agent.log")
        stats = lazy_stats_from_text(agent.read_text(encoding="utf-8", errors="replace")) \
            if agent.is_file() else {}
        rows.append({"control": c, "treatment": t, "lazy": stats})
        print(f"#{i}: control={c['menu_s']} treatment={t['menu_s']} "
              f"ws={c.get('ws_menu_mb')}/{t.get('ws_menu_mb')} lazy={stats}")
    c_med = median([r["control"]["menu_s"] for r in rows])
    t_med = median([r["treatment"]["menu_s"] for r in rows])
    result = {"rows": rows, "control_median": c_med, "treatment_median": t_med,
              "delta_s": None if c_med is None or t_med is None else round(t_med - c_med, 2),
              "ws_control_median": median([r["control"].get("ws_menu_mb") for r in rows if r["control"].get("ws_menu_mb")]),
              "ws_treatment_median": median([r["treatment"].get("ws_menu_mb") for r in rows if r["treatment"].get("ws_menu_mb")]),
              "gpu_control_median": median([r["control"].get("gpu_menu_mb") for r in rows if r["control"].get("gpu_menu_mb")]),
              "gpu_treatment_median": median([r["treatment"].get("gpu_menu_mb") for r in rows if r["treatment"].get("gpu_menu_mb")])}
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑测试 + 构建**

`python -I -m pytest tests/tools/test_smoke_run.py tests/tools/test_m25_ab.py -q` → pass；`bash tools/java/build-mod.sh` 仍 OK。

- [ ] **Step 5: 跑 A/B（同 boot、warm、交错 3+3）**

先 warm-up 一轮 control（不计入）：`python -I tools/smoke_run.py --profile miko-lite --rounds 1 --jvm-arg=-Dhypernova.textures.lazy=false --json-out build/m25/ab-warm.json`；确认 `preload=hit`、file index loaded。
然后：

```bash
python -I tools/m25_ab.py --profile miko-lite --rounds 3 \
  --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
  --out build/m25/ab-result.json
```

Expected：6 轮都 ok；treatment 的 lazy summary `skipped≈45,785、proxies≈45,785、materialized≈7.3k、failed=0、disabled=0`；control 无 lazy 行。记录每轮 `starsector.log` 快照（`build/m25/logs/ab-cN.log`/`ab-tN.log`）并统计 0 Failed/0 Verify。

- [ ] **Step 6: 正确性（Base 运行期 mod）**

用 Base + `-Dhypernova.textures.lazy=true` 启动，用户手动：进主菜单 → 读档 → 进一场战斗/开百科；检查无白块/错位/缺失；日志 0 `Failed to load texture`；agent `failed=0`。若用户不在，记录“待用户手动验证”，不把它标 PASS。

- [ ] **Step 7: 结果判读（呈现给用户，不自行改默认）**

输出三项：① 菜单前非 L1 skip（`skipped`/`wouldSkip`/`Loading image`）；② 菜单中位差（control vs treatment）；③ working set/GPU（`ws_menu_mb`/`gpu_menu_mb`）；正确性单独列。若菜单/VRAM 无改善或更差：M2.5 默认保持 off，写限制；若改善且正确性通过：Task 5 再决定是否默认开（用户裁决）。

- [ ] **Step 8: 提交**

```bash
git add tools/smoke_run.py tests/tools/test_smoke_run.py tools/m25_ab.py tests/tools/test_m25_ab.py
git commit -m "feat(m25): add same-boot lazy A/B and VRAM sampling" \
    -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: 结果、规格、ADR、记忆、终审

- **结果**：`docs/m25-results.md`：Task 2 内部 gate、Task 4 三项指标、正确性（自动 + 用户手动）、DDS/PNG VRAM 口径、失败/偏差、回滚。
- **规格**：`技术笔记-纹理按需加载.md` 增加 M2.5 生产段；更新 REQ-R2-01（结构指标 = agent queue/skip；`Loading image` 是 PNG 计数）、REQ-R2-03（agent 在 FR 前；预置同名 donor 方法；不改 `_vanilla`）；INV-06/10 的实装证据；ADR-05 补记 6。
- **默认值**：仅当 Task 4 证明收益且正确性通过，由用户裁决是否 `textures.lazy.enabled=true`；否则保持 false。**不要**在 Task 5 自行改默认。
- **回滚**：`textures.lazy.enabled=false` / `-Dhypernova.textures.lazy=false` / 删 agent 行；skip 文件可留。
- **记忆**：`hn-m25-complete.md`（结果/默认/回滚/风险）；`hn-next-session.md` 更新；`MEMORY.md` 索引。
- **终审**：`review-package <plan> <BASE> HEAD` → opus 全分支 review；deferred minors 三档 triage；must-fix 由一个 fix agent 修 + scoped re-review。
- **提交**：`docs(m25): close the lazy-textures milestone` + 文档/规格/记忆。

---

## Self-Review

1. **Spec 覆盖**：REQ-R2-01（Task 2/4）、R2-02（代理 + 按需；一帧剪影）、R2-03（agent 前 + 不碰 `_vanilla`）、R2-04（默认 off/回滚）、INV-06（形状 gate/fail-open）、INV-10（manifest 尺寸）均有任务。R-M25-1..10 记录裁决。
2. **占位符**：Task 2 代码完整；Task 3/4 给出完整改动函数/脚本；Task 5 为文档/流程步骤（无代码）。
3. **类型一致**：`LazyTextureConfig(boolean,boolean,Path)` ↔ 测试/agent；`ProxyShape.resolve/newProxy/copy` ↔ LazyTextures/测试；`eligible(boolean,boolean,boolean,LazySkipIndex,String,String)` ↔ 测试；`InstallResult.skip_file/skip_count` ↔ 测试；`smoke` 的 `ws_menu_mb` ↔ `m25_ab`。
4. **Review Focus 测试归属**：主线程捕获 → `LazyGameThreadTransformTest` + 内部 gate；代理字段/UV → `ProxyShapeTest`；物化同一 id → 内部 gate + Task 4 正确性；engine hit/path cache → 代码 + Task 4；skip 口径 → `LazyTexturesEligibleTest`；默认/回滚 → Task 4/5；post-menu burst → Task 4。
5. **比例**：生产代码集中 5 个小类；Task 3/4 只给改动；Task 5 流程。无 TBD。

## Exit criteria（M2.5）

- Task 2 内部 gate 通过（Base/260mods lazy=true：captures、materialized>0、failed=0、无 Failed/Verify）。
- Task 3：安装器/发行包含 M2 manifest + skip 文件；smoke 脚本幂等。
- Task 4：A/B 三项指标 + 正确性（含用户手动）有数据；默认值由用户裁决；无改善则默认保持 off 并写限制。
- Task 5：docs/spec/ADR/memory/终审闭环；所有 must-fix 关闭或明确 deferred。
