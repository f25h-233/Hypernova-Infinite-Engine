# Changelog

## [1.9.6] - 2026-11-07

### Added

- agent 支持 **Fast Rendering 0.9.8**：
  - 文件索引按版本选择 handle 形状：0.9.7 的嵌套
    `ResourceHandle$FileHandle` 与 0.9.8 的顶层
    `ResourceHandle(File, ResourceLocation, String)`；0.9.8 replay 传空
    extension，避免在 `FR-Main-Loader` 上串行预读约 275 MB 文本。
  - 旧索引按 `frVersion` / `shapeStamp` 自动失效；不需要手动清缓存。
  - lazy/DDS 在 0.9.8 上使用 `ResourceLoaderLock.executorLock`，避免绕过
    FR 的纹理提交锁；lazy 仍默认关闭。

### Fixed

- 拆分 file index 与 lazy 的 FR 版本门禁，防止 0.9.8 上误开未适配的 lazy。

## [1.9.5] - 2026-11-05

### Fixed

- manifest 生成工具对玩家侧脏数据的健壮性（线上反馈：单条失效缓存导致整份
  清单不写盘）：
  - DDSCache 是持久缓存，记录可能指向 mod 更新/改名后已不存在的原图。
    `manifest_builder` 现在以磁盘为准解析记录：原图找不到的按失效缓存跳过，
    并从 baked 覆盖率分母中剔除；DDS 文件丢失但原图仍在的条目降级为未烘焙，
    不再触发 `missing_dds` 失败。
  - 重复 ModID（原版 + 汉化两份同名 id）按「文件实际所在目录」落位，不再
    只认排序后的第一个文件夹。
  - 标题闭包里磁盘上不存在的贴图引用跳过并计入 `unresolved_refs`，不再因
    `missing_file` 拒绝写 manifest。
  - 新增统计：`stale_metadata_count`、`dds_missing_count`、
    `unresolved_refs_count`；玩家侧日志会打印对应 `[注意]` 行。

## [1.9.4] - 2026-11-05

### Fixed

- agent 纹理补丁支持 **GraphicsLib 1.12.2**（此前只认 1.12.1 的
  `TextureData.class` SHA-256，1.12.2 上直接
  `TextureData sha mismatch, not patching`，懒加载静默失效）。
  - 构建改为多版本变体：每个受支持版本从它自己的 `Graphics.jar` 取原始
    class 做 SHA 钉死、编译一份补丁类，运行期按 SHA 选择变体。
  - 1.12.2 的 jar 不再内嵌 `.java`，补丁源从上游源码取，并已验证
    用 JDK 17 编译该源码可**逐字节复现**官方 `TextureData.class`
    （`3b939e21…`）。
  - 未识别版本仍 fail-closed：只记一条
    `unsupported GraphicsLib TextureData (sha256=…)`，不猜测、不崩溃。
  - 构建期新增守卫：补丁编译产生的 `TextureData$*.class`（switch 映射
    合成类）必须与厂商 jar 语义一致，否则构建失败。

## [1.9.3] - 2026-11-04

当前版本。`1.0.0`（功能完善可用，M2.8）之后累计 **9 个 minor**
（`1.1.0`–`1.9.0`）和最后一条 minor 线上的 **3 个 patch**
（`1.9.1`–`1.9.3`）。

### Added

- `1.1.0`–`1.2.0`：主线程 frame-time probe、会话报告工具。
- `1.3.0`–`1.4.0`：agent-side frame probe、从 agent 日志读取帧数据。
- `1.5.0`–`1.9.0`：环境矩阵审计、环境快照/恢复、manifest/skip generation
  审计、兼容性日志审计、会话包装与手动验收 runbook。

### Fixed

- `1.2.1`–`1.2.9`、`1.4.1`–`1.4.2`、`1.7.1`–`1.7.3`、`1.8.1`、
  `1.9.1`–`1.9.3`：会话报告导入、A/B stats 抓取、帧采样去重、release
  check、timeout 清理、PID 确认、torn summary、snapshot 路径安全、
  manifest fail-closed/fail-open、日志 observation/error 分离、session
  evidence pairing 等。

### Tests

- main 115/115；agent 211/210/1（1 个已知 Windows symlink 用例跳过）；
  pytest 492。

### Known limitations

- 用户实机 gate（战役 / 战斗 / 读档 / 中文输入 / 字体视觉）仍 **pending**。
- `lazy` / `eviction` / `sceneUnload` / `frame probe` 默认关闭；
  不宣称显存/启动收益。

## [1.0.0] - 2026-11-02

功能完善可用（M2.8）：主 mod（运行期纹理预取 + 兜底）+ 可选 agent
（FR 文件索引、Janino 脚本预编译缓存、法线图缓存补丁）+ manifest +
lazy/DDS/LRU。

- 锚点提交：`9f4946e`（M2.8，2026-11-02）。
- 证据采集于 `0.1.0` 构建；`1.0.0` 仅版本号/文档更新，运行代码未改。

## [0.1.0] - 2026-10-25 .. 2026-11-02

内部开发版本（M0–M2.7）。历史里程碑 tag：`m0`…`m2.7`。未公开发行。
