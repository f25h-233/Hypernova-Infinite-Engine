# Changelog

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
