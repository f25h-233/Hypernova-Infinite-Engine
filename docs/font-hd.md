# 高清字体桥（DynFont HD）

> 适用：远星汉化优化测试版（`startup-optimization` 分支）+ Fast Rendering。
> 版本：1.9.9（2026-11-12）。

## 背景

优化版汉化把高清矢量字体生成到
`starsector-core/graphics/fonts/dyn_font/cache/s<比例>-<哈希>/`，再由
`org.fossic.starsector.dynfont.DynFontOverrides.openStream` 把
`graphics/fonts/*.fnt` 重定向到这些高清图集。

Fast Rendering 覆写后的贴图加载链是
`TextureLoader(FR) → FileLoader → FileLoaderFast`，不经过
`com.fs.util.C`，因此 `DynFontOverrides.openStream` 不会执行：

- `graphics/fonts/dyn_font/cache/` 永远不会生成；
- 游戏按原路径读到的仍是 2048 宽的低清位图；
- MixinFR 的 `FrFontHd` 只负责把路径 remap 到已有缓存，不负责生成缓存，
  所以路线 A 在 M7 审计里也全是 `cache dir = (none)` / `FONT-PATH no-hd`。

## 做法

1. **premain 生成缓存**：agent 在游戏加载字体之前反射调用
   `DynFontOverrides.initialize()`（优化版自己的初始化入口，加载
   `native/windows/ss_dyn_font.dll`、探测缩放、生成/复用缓存）。
2. **配对扫描**：只接受同时满足以下条件的字体：
   - `common scaleW/scaleH` 与 PNG IHDR 尺寸一致；
   - `pages=1`，且 fnt 自己声明的 page 图存在；
   - 目标 `graphics/fonts/<name>.fnt` 与目标 page 都存在；
   - 跳过 `_exact`（优化版渲染器专用的 26.6 定点布局）。
3. **资产覆盖**：把成对的 `*.fnt` / `*_0.png` 复制到 `graphics/fonts/`，
   原文件首次备份为 `*.bak-hypernova-hd`；重复启动按 SHA-256 跳过。
4. **不改 FR 字节码**：FR 之后按原路径读到的就是高清图集，因此对
   0.9.7rc2 / 0.9.7 / 0.9.8 / 1.0.0 都不挑版本。

## 开关

| 项 | 说明 |
|---|---|
| 默认 | 检测到优化版 `DynFontOverrides` 且 FR 存在时开启 |
| 关闭 | `-Dhypernova.fontHd=false` |
| 只观察不写盘 | `-Dhypernova.fontHd.dryRun=true` |
| 还原 | `hypernova-tools/restore-font-hd.bat`（恢复 `*.bak-hypernova-hd`） |

日志：`saves/hypernova/scripts-agent.log` 搜 `fontHd`。

## 证据（2026-11-12）

- POC（独立 JVM，Temurin 28，真实 `starsector-core` settings/native）：
  `DynFontOverrides.initialize()` 生成 11 个真实 HD 字体（+ `_exact` 等共
  55 个文件），首次 2.46 s，第二次 0.17 s；HD `common scaleW=4096`，
  PNG 4096×512 / 4096×1024；原版对应页宽 2048。
- 集成测试（假游戏根 + 真实 `DynFontOverrides` + 真实缓存）：
  `fontHd: cache=s1.50-... fonts=11 applied=11 already=0 failed=0`；
  第二次 `applied=0 already=11`。
- 单元测试：`DynFontHdTest`（配对/`_exact`/尺寸不符/目标缺失/备份/幂等/dry-run/
  最新缓存选择）；`test_manage_font_hd.py`（还原/干跑/嵌套目录）。

## 风险与边界

- **写游戏文件**：只写 `graphics/fonts/` 下的 11 对 fnt/page；原文件有备份，
  `restore-font-hd.bat` 可逆。
- **首次启动 +2–3 s**：生成缓存；之后复用约 0.2 s。
- **分辨率/缩放变化**：`DynFontOverrides` 会生成新的 `s*` 缓存目录；下次启动
  agent 取最新完整缓存重新覆盖。
- **汉化更新**：原文件被安装器替换后，下次启动按哈希重新覆盖；旧备份保留。
- **失败 fail-open**：任何异常只记日志，游戏继续走原版位图，不阻断启动。
- **用户视觉 gate 仍 pending**：本文不宣称字体视觉/战斗/读档已验收。
