# Java 脚本预编译缓存 — 调研与方案

> **状态**：**实施规格（2026-10-29，M-1d 立项；ADR-03）**。本文是 `scripts` 模块的规格与可行性依据；实现计划走 `/SDD`。
> **关系**：独立于《纹理按需加载 — 规格说明》。两者共享启动时间预算，但改动面、交付形态、风险完全不同。
> **结论一句话**：15,070 个脚本类每次启动重编约 25 s；FR 0.9.5 的脚本 loader 已有进程内 `bytecodeCache`，在构造函数末尾 preload 即可跨启动复用，**类加载器身份问题在正确实现下不存在**。

## 0. 裁决与可行性结论（2026-10-29）

- **可行性：高**。拦截点已由反编译 + javap 核实：`com.genir.renderer.overrides.loading.MultiThreadedJaninoClassLoader` 的构造函数创建共享 `bytecodeCache`；`JavaSourceCompiler.getBytecode` 先查该 map，未命中才编译。把磁盘缓存 `putAll` 进 map 即可跳过全部 Janino 编译。
- **难度：中**。一个 agent transformer + 内容寻址缓存 + 指纹/失效 + 安装/回退；不碰渲染、GL、纹理。
- **收益：20–25 s**（verbose 实测 15,070 条、约 25 s）；86.5 s → ~62–66 s。与 M-1b（法线缓存 29.6 s）组合的乐观上界 ~32–37 s，但并行关系需复测，不作为承诺。
- **为什么先做（ADR-03）**：启动期最大单一固定成本，改动面最小、失败可回退；M3 的代理纹理工作量大、风险高；M-1d 还先落地 agent 基础设施（Form B）。
- **不做什么**：不改 FR 的编译逻辑；不引入第二个脚本 loader；不把 class 打进发布包；不缓存运行时动态生成的源码（走原路径）。
- **证据边界**：机制来自反编译 + javap，**尚未实机 spike**；S3 单类命中是开工门禁。

---

## 1. 问题与实测

| 项 | 数值 | 证据 |
|---|---|---|
| 唯一 `Compiling script` 目标 | **15,070** | `starsector.log.verbose` |
| 编译墙钟 | **约 25 s**（3 条脚本线程，CPU 约 75 s） | 详细日志相位：267,941–292,808 ms |
| 启用 mod 中带 `.java` | 168 个，合计 13,707 个源文件 | 本机遍历 |
| 同时带 jar | 140 个 | 同上 |
| 同 mod 内"jar 已有同类" | 911 个（6%），其中 54 个源码更新 | 本机按 `mod_info.json` 的 `jars` 重算 |
| 全局跨 mod 同类 | 12,859 个（85%） | 仅作参考，**不能**据此跳过本 mod 编译 |

**要点**：主成本不是"jar + 源码双份"（只有 6%），而是 15,070 个源类本身。删源码/打回 jar 最多省 1.5 s，不值得优先做。

## 2. 机制

- `ScriptStore` 负责 mod 脚本加载：先尝试 `Class.forName`（已加载则跳过编译），否则用 Janino 的 `JavaSourceClassLoader` / `CachingJavaSourceClassLoader` 编译。
- **FR 0.9.5 覆盖了 vanilla `ScriptStore`**（`com.genir.renderer.overrides.loading.ScriptStore`）：`initScriptClassLoader()` 构造 `MultiThreadedJaninoClassLoader(jarLoader)`；`findClass` → `findBytecode` → 每线程 `JavaSourceCompiler.getBytecode`，后者先查共享 `bytecodeCache`（`ConcurrentHashMap`），未命中才 `generateBytecodes`。这是本方案的拦截点（详见 §4.1）。
- vanilla 的内置 `enableScriptCaching`（`CachingJavaSourceClassLoader`）只在**未装 FR** 时生效；FR 覆盖后该分支不再执行，默认 false；不作为本模块依赖。
- vanilla 的内置 `enableScriptCaching=true` 会启用 `CachingJavaSourceClassLoader` 的**磁盘**缓存（写到 `saves/cache` 一类目录，默认 false）；FR 覆盖后该分支不再执行，改用只带进程内 `bytecodeCache` 的 `MultiThreadedJaninoClassLoader`，所以每次启动重编。
- 编译输入：源文件内容 + classpath（jar 顺序与内容）+ Janino 版本 + 游戏版本 + 编译器指令（`compiler_directives.txt`）。
- 编译是确定性的：同一组输入应产生同一组 class（Janino 版本固定时）。
- 编译跑在 3 条 `FR-Script-Loader` 线程上；与主线程的 DDS 句柄登记并行。

## 3. 三条可行路线

| 路线 | 做法 | 预期收益 | 代价 | 版本耦合 |
|---|---|---|---|---|
| **A. agent + 内容寻址缓存** | agent 在 FR loader 构造时 preload 共享 `bytecodeCache`；命中免编译，未命中回退 Janino | 省 20–25 s | 需改启动参数；类加载器身份由原 loader 保证 | 高（FR/游戏/Janino 版本） |
| **B. 离线预编译成 jar** | 工具把 mod 的 `.java` 离线编译，按原包结构写进 jar；游戏走 jar 类 | 省全部编译时间 | 改 mod 分发/授权；mod 更新需重编；**系统 classpath 的 class 由 app loader 定义，看不到子脚本 loader 的 mod jar**，除非把全部 mod jar 也塞进系统 classpath（隔离破坏） | 中（只依赖 API 版本） |
| **C. fork/patch `ScriptStore`** | 换成持久化 `CachingJavaSourceClassLoader` 或自建 loader | 同 A | 维护 fork；与 FR 的脚本类加载链冲突需处理 | 高 |

**2026-10-29 裁决（OD-08 / ADR-03）**：选 A（agent + 内容寻址缓存）。理由：FR 已有共享 `bytecodeCache`，preload 即可复用；不改 mod 分发、不 fork FR；失败可回退。B 只作为无 agent 环境的备选；C 排除。

**最小闭环顺序**：单类命中 → 单 mod 命中 → 全量；每一级都是门禁（见 §7）。

### 3.1 与既有方案的关系（2026-10-30，回答"是否重复造轮子"）

社区常见质疑："原版 `settings.json` 里就有 `enableScriptCaching`，你们是不是做了同样的东西？" 结论是**否**，三条证据：

**① 原版开关当前是关的，且作者自己说明它有问题。**
`starsector-core/data/config/settings.json` 原文（非本项目修改）：

```json
# disabled for now, causes issues with subsequent runs if game is shut down during startup
"enableScriptCaching":false, # caches compiled scripts in saves/cache, faster startup time after first run
```

实证：`starsector-core/cache/` 为空目录，`saves/` 下无 `cache/`，0 个 `.class`——该开关从未在任何一轮实测中生效。

**② FR 覆盖了整个 `ScriptStore`，该分支在装 FR 的环境里根本不存在。**
vanilla `com/fs/starfarer/loading/scripts/ScriptStore.java:135` 有 `enableScriptCaching` 判断，else 分支用 `CachingJavaSourceClassLoader`（磁盘缓存到 `saves/cache/<hash>/`）。FR 0.9.5 的 `com/genir/renderer/overrides/loading/ScriptStore.java:116` 直接构造 `MultiThreadedJaninoClassLoader`，**没有该判断，也没有 `CachingJavaSourceClassLoader`**。所以装了 FR 的用户把开关设成 `true` 也无效。

**③ FR 放弃磁盘缓存的原因，正是原版注释里那个 bug。**
vanilla 的 `ResourceCreator.createResource` 是：
```java
File file = new File(ScriptStore.o00000(string), string);
file.getParentFile().mkdirs();
return new FileOutputStream(file);          // 直接写最终路径，无原子性
```
进程在写一半时被杀 → 留下**截断的 `.class`** → 下次启动读到坏文件。这与 settings.json 的 "causes issues with subsequent runs if game is shut down during startup" 完全对应。FR 为了多线程编译重写了 loader，顺带丢掉了磁盘缓存。

**本项目与三者的定位差异**：

| | vanilla `enableScriptCaching` | FR `MultiThreadedJaninoClassLoader` | M-1d（本 agent） |
|---|---|---|---|
| 缓存位置 | 磁盘 `saves/cache/` | 无（仅进程内 `bytecodeCache`） | 磁盘 `saves/hypernova/scripts-cache/` |
| 写入原子性 | ❌ 裸 `FileOutputStream` | — | ✅ tmp + `ATOMIC_MOVE` + CRC32 |
| 坏文件处理 | ❌ 原地读坏 | — | ✅ 校验失败返回 null，回退 Janino |
| 编译并发 | ❌ 单线程 | ✅ 3 线程 | ✅ 不介入编译，只 preload |
| 失效判定 | 仅 mtime | — | sha256 + classpath + java 版本 + 启用集 |
| 官方状态 | **已禁用（作者注明会坏）** | 覆盖后该分支失效 | 使用中 |

**一句话**：本项目不是重复原版的开关，而是**补上官方因写入不原子而放弃的那块**，且不改 FR 的编译路径——只往它已有的 `bytecodeCache` 里 `putAll`，因此不与任何"加速编译"类 mod（Miko 的 JDK/Janino 升级、FR 的多线程编译）冲突，可以叠加。

## 4. 缓存设计草案

```
cacheKey = SHA-256(
  sourceBytes ||
  janinoVersion ||
  gameVersion ||
  compilerDirectivesHash ||
  classpathFingerprint      // jar 列表顺序 + 每个 jar 的 SHA-256
)
cachePath = <cacheRoot>/<key[0:2]>/<key>.class
sidecar   = <cacheRoot>/<key[0:2]>/<key>.json   // 源路径、类名、依赖、生成时间
```

规则：

1. **逐类缓存**，不是逐 mod；改一个类只失效一个条目。
2. **命中失败自动回退**：缓存损坏/版本不符/依赖变化 → 走 Janino 重编，并覆盖缓存。
3. **原子写**：先写 `.tmp` 再 rename；3 条脚本线程并发安全。
4. **依赖指纹**：至少包含 classpath（mod jar 顺序）、Janino/游戏版本、编译器指令；可选包含被引用类的 key。
5. **不缓存运行时生成/修改的源码**：只缓存磁盘上稳定存在的 `.java`。
6. **清理策略**：按最近使用时间 + 总大小上限（例如 2 GB）。

### 4.1 与 FR 的实际结合（2026-10-29 修订）

- 不必改 `getBytecode`：在 `MultiThreadedJaninoClassLoader` 构造函数末尾注入 `preload(this)`，把本代缓存 `putAll` 进 `bytecodeCache`；`findBytecode` 的现有逻辑自动命中。
- 缓存按 **generation（fingerprint）** 分目录/分 pack；启动时只加载匹配 fingerprint 的代；不匹配 → 不 preload，正常编译并写新代。
- fingerprint 输入：所有 `.java` 的（路径、大小、mtime、内容哈希缓存）、所有相关 jar 的（路径、大小、mtime/哈希）、游戏/FR/Janino 版本、`enabled_mods.json`、编译配置。实测规模：260mods 启用集 14,228 个 `.java` / 80.7 MB，271 个 jar / 194.6 MB；指纹与预读必须有上限。
- 缓存体量估计：15,070 个类，约 75–300 MB；用单 pack 顺序读，避免 15k 次小文件 open。
- 写入：冷启动编译产生的新条目由后台线程/退出钩子落盘；原子替换；≤ 2 GB，按代 LRU 清理。

## 5. 类加载器约束（最大的坑）

**2026-10-29 结论（PC-01 已解）**：采用 preload 方案时，缓存字节进入 FR loader 的 `bytecodeCache`，最终由 `MultiThreadedJaninoClassLoader.findClass` 的 `defineClass` 定义——就是原本会定义它的 loader。不存在"缓存 loader vs Janino loader"两个身份。前提：只 preload map，不自己定义类；不在缓存里存"已经由别的 loader 加载"的类。

- 缓存里的 class 必须由**原本会加载它的那个 loader** define；不能一半来自缓存 loader、一半来自 Janino。
- mod 之间可能互相引用；classpath 顺序变化会改变解析结果，必须进 key。
- 开发模式热重载（F8）会重新编译；缓存要能识别并绕过。
- 与 FR 的关系：FR 的 agent 已改写 `ScriptStore`（`loadModClasses`/`initScriptClassLoader`），缓存钩子必须挂在其后，不能破坏 `_vanilla` 布局。

## 6. 失效与风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| key 漏掉输入（classpath 顺序、指令） | 加载旧类，行为诡异 | key 覆盖全部输入；启动时抽样校验 |
| 类加载器身份不一致 | `LinkageError`/`ClassCastException` | 缓存 class 交给原 loader define；单类 spike 先验证 |
| mod 更新但缓存未失效 | 旧逻辑 | 源哈希 + jar 哈希；miss 回退 |
| 授权/分发 | 不能把别人的 class 打进自己的包 | 缓存只存本机编译产物，随游戏目录删除 |
| 与反作弊/完整性检查冲突 | 未知 | 当前单机环境无此问题 |

## 7. Spike 计划（建议顺序，2026-10-29 更新）

1. **S1（已完成）**：统计编译目标、耗时、来源分布。
2. **S0（可选，零代码）**：在**无 FR** 的 Base 上把 `enableScriptCaching` 设为 true，确认内置 `CachingJavaSourceClassLoader` 的行为与收益；仅作参考，不作为依赖。
3. **S2**：用 Janino 在独立进程里编译 1 个 mod 的全部类，记录耗时与 class 字节；记录两次编译的字节差异（不要求字节一致，只用于诊断）。
4. **S3（门禁）**：写一个最小 agent，在 `MultiThreadedJaninoClassLoader` 构造函数末尾注入 preload；先用手工构造的 1 个类缓存验证命中与 `defineClass`；在 Base 包验证。**不通过 → 停，回退 OD-08 路线 B 或放弃。**
5. **S4（门禁）**：扩到 1 个内容 mod（如 CRSIDtest，1,196 个目标），测命中率、启动时间、落盘/预读开销。**不通过 → 缩小范围或回退。**
6. **S5**：全量 260mods，测 25 s 能降到多少；同时记录失败/回退数、缓存体积、首屏中位数。

## 8. 开放问题

| ID | 问题 | 影响 |
|---|---|---|
| PC-01 | 缓存 class 由哪个 loader define 才能与 Janino 路径完全等价？ | **已解**：preload 进 FR 的 `bytecodeCache`，由原 `findClass` 的 `defineClass` 定义 |
| PC-02 | Janino 两次编译同一源是否字节级一致？ | **不再作为正确性前提**：缓存只要求语义等价；S2 仍记录字节差异用于诊断 |
| PC-03 | classpath 指纹要不要包含每个 jar 的哈希（成本 vs 正确性）？ | **已定**：源内容哈希 + jar 大小/mtime（可选哈希）；用 stat 清单缓存，避免每次全量读 |
| PC-04 | 运行时生成/修改的源码占比多少？ | 未测；本模块不缓存它们（miss 回退），不影响命中率上界 |
| PC-05 | 与 FR 的 `ScriptStore` 改写如何共存？ | **已解**：我们的 agent 在 FR agent 之后注册；transform 的是 FR 自己的 `MultiThreadedJaninoClassLoader`，不在 FR 的覆盖白名单里 |
| PC-06 | 交付形态：agent / 离线 jar / fork（对应 OD-08） | **已裁决**：agent（OD-08/ADR-03） |

## 9. 证据索引

- `Starsector-098-260mods/starsector-core/starsector.log.verbose`（15,070 条编译行、相位时间）
- `.research/decomp/src/com/fs/starfarer/loading/scripts/ScriptStore.java`
- `.research/decomp/fr-src/com/genir/renderer/overrides/loading/ScriptStore.java`
- Janino `CachingJavaSourceClassLoader`（`mikohime/janino-3.0.12.jar`）
- 本机盘点脚本输出（168/140/911/54）

## 10. M-1d 里程碑与验收（2026-10-29）

**目标**：热启动跳过 15,070 个脚本的 Janino 编译，首屏 86.5 s → ~62–66 s。

| ID | 需求 | 验收 |
|---|---|---|
| REQ-S-01 | 热启动命中率 ≥ 95% | 本组件计数；抽样 100 类 |
| REQ-S-02 | 首屏中位数下降 ≥ 15 s（目标 20–25 s） | 附录 A 锚点，三次中位数 |
| REQ-S-03 | 无缓存首跑不慢于基线 +5 s | 删缓存后三次 |
| REQ-S-04 | 坏缓存/版本不符/无 FR/结构探针失败 → 自动回退 Janino，不崩 | 三种场景各启动一次 |
| REQ-S-05 | `scripts.enabled=false` 完全 no-op | 事件集合 diff；缓存无写入 |
| REQ-S-06 | 键覆盖全部编译输入；任一变化 → miss | 逐项改动断言 |
| REQ-S-07 | 类由原脚本 loader 定义，无第二 loader | 运行时断言 |
| REQ-S-08 | 缓存 ≤ 2 GB；预读 ≤ 3 s 或移出主线程 | 实测 |
| REQ-S-09 | hit/miss/compile/fallback/首屏 JSONL | schema + 10 万行 |

**门禁**：S3 不过 → 停；S4 不过 → 缩小或回退。**出口**：Base 单类→单 mod→260mods 三级命中；删缓存自愈；禁 FR/禁用开关/坏缓存不崩。

**与主规格的关系**：主规格 §4.6 是同一组需求的摘要；以本节为准。
