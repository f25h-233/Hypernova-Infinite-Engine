# Changelog

## [1.0.0] - 2026-11-04

首个公开发行。

### Added

- 主 mod：运行期纹理预取 + 兜底（Form A）。
- 可选 agent：FR 文件索引、Janino 脚本预编译缓存、法线图缓存补丁。
- M6 兼容性审计：汉化测试版 / ChineseInputFix / 字体 / UI 的兼容性与
  manifest 正确性。
- Apache-2.0 许可证（代码）、CC BY 4.0（公开文档）、第三方 `NOTICE`。

### Changed

- 内部研究笔记、反编译资料、混淆映射与补丁二进制移出公开仓库。
- 版本号从 `0.1.0` 提升到 `1.0.0`；M6 证据采集于 `0.1.0` 构建，
  **运行代码未改**。

### Tests

- main 115/115；agent 211/210/1（1 个已知 Windows symlink 用例跳过）；
  pytest 492。

### Known limitations

- 用户实机 gate（战役 / 战斗 / 读档 / 中文输入 / 字体视觉）仍 **pending**。
- `lazy` / `eviction` / `sceneUnload` / `frame probe` 默认关闭；
  不宣称显存/启动收益。

## [0.1.0] - 2026-10-25 .. 2026-11-03

内部开发版本（M0–M4.1）。历史里程碑 tag：`m0`…`m4.1`。未公开发行。
