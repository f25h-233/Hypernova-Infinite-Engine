# Java 脚本预编译缓存 — 调研与方案

> **状态**：调研稿（2026-10-25），不是实现计划；等 OD-08 裁决后再走 `/SDD`。
> **关系**：独立于《纹理按需加载 — 规格说明》。两者共享启动时间预算，但改动面、交付形态、风险完全不同。
> **结论一句话**：15,070 个脚本类每次启动重编约 25 s；编译输入是确定的，做内容寻址缓存理论上可省 20–25 s，但必须解决类加载器身份、失效判定和交付形态三个问题。

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
- `CachingJavaSourceClassLoader` 的缓存是**进程内**的，进程退出即丢；没有磁盘缓存。
- 编译输入：源文件内容 + classpath（jar 顺序与内容）+ Janino 版本 + 游戏版本 + 编译器指令（`compiler_directives.txt`）。
- 编译是确定性的：同一组输入应产生同一组 class（Janino 版本固定时）。
- 编译跑在 3 条 `FR-Script-Loader` 线程上；与主线程的 DDS 句柄登记并行。

## 3. 三条可行路线

| 路线 | 做法 | 预期收益 | 代价 | 版本耦合 |
|---|---|---|---|---|
| **A. agent + 内容寻址缓存** | premain/agent 在 `ScriptStore` 编译前按 key 查磁盘缓存；命中直接 defineClass；未命中回退 Janino | 省 20–25 s | 需改启动参数；类加载器身份必须与原编译路径一致 | 高（FR/游戏/Janino 版本） |
| **B. 离线预编译成 jar** | 工具把 mod 的 `.java` 离线编译，按原包结构写进 jar；游戏走 jar 类 | 省全部编译时间 | 改 mod 分发/授权；mod 更新需重编；类加载器仍要一致 | 中（只依赖 API 版本） |
| **C. fork/patch `ScriptStore`** | 换成持久化 `CachingJavaSourceClassLoader` 或自建 loader | 同 A | 维护 fork；与 FR 的脚本类加载链冲突需处理 | 高 |

**推荐先验证 A 的最小闭环**：单类命中 → 单 mod 命中 → 全量；B 作为"无 agent 时的打包方案"。

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

## 5. 类加载器约束（最大的坑）

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

## 7. Spike 计划（建议顺序）

1. **S1（已完成）**：统计编译目标、耗时、来源分布。
2. **S2**：用 Janino 在独立进程里编译 1 个 mod 的全部类，记录耗时与 class 字节；验证确定性（两次编译字节一致）。
3. **S3**：写一个最小 agent，只拦截 1 个类的编译，命中时 `defineClass`，未命中回退；在 Base 包验证。
4. **S4**：扩到 1 个内容 mod（如 CRSIDtest，1,196 个目标），测命中率与启动时间。
5. **S5**：全量 260mods，测 25 s 能降到多少；同时记录失败/回退数。

## 8. 开放问题

| ID | 问题 | 影响 |
|---|---|---|
| PC-01 | 缓存 class 由哪个 loader define 才能与 Janino 路径完全等价？ | 决定 A 是否可行 |
| PC-02 | Janino 两次编译同一源是否字节级一致？ | 决定缓存能否跨机器复用 |
| PC-03 | classpath 指纹要不要包含每个 jar 的哈希（成本 vs 正确性）？ | 失效精度 |
| PC-04 | 运行时生成/修改的源码占比多少？ | 缓存命中率上限 |
| PC-05 | 与 FR 的 `ScriptStore` 改写如何共存？ | 版本耦合 |
| PC-06 | 交付形态：agent / 离线 jar / fork（对应 OD-08） | 谁来承担安装与维护 |

## 9. 证据索引

- `Starsector-098-260mods/starsector-core/starsector.log.verbose`（15,070 条编译行、相位时间）
- `.research/decomp/src/com/fs/starfarer/loading/scripts/ScriptStore.java`
- `.research/decomp/fr-src/com/genir/renderer/overrides/loading/ScriptStore.java`
- Janino `CachingJavaSourceClassLoader`（`mikohime/janino-3.0.12.jar`）
- 本机盘点脚本输出（168/140/911/54）
