# M7 实验根环境基线（optimized-2026.10.15）

盘点日期：2026-11-03。唯一实验根：

```
SS098_Hypernova_Compat_AuditTest/install/optimized-2026.10.15
```

本文件只记录只读事实，不代表任何路线已安装或已实机验证。机器可读证据见
`SS098_Hypernova_Compat_AuditTest/evidence/m7-env.json`，由以下命令生成：

```bash
python -I tools/m7_stack.py inspect \
  --root SS098_Hypernova_Compat_AuditTest/install/optimized-2026.10.15 \
  --out SS098_Hypernova_Compat_AuditTest/evidence/m7-env.json --text
```

## 汉化包

`starsector-core/localization_version.json`：

| 字段 | 值 |
|---|---|
| name | 远行星号中文汉化包 |
| author | 远星汉化组 |
| version | 2026.10.15 |
| branch | startup-optimization |
| language | zh-Hans |
| game_version | 0.98a-RC8 |

## Java 运行时

`jre/release`：

| 字段 | 值 |
|---|---|
| JAVA_VERSION | 17.0.10 |
| JAVA_RUNTIME_VERSION | 17.0.10+7-LTS |
| IMPLEMENTOR | Azul Systems, Inc. |
| IMPLEMENTOR_VERSION | Zulu17.48+15-CA |
| OS_NAME / OS_ARCH | Windows / x86_64 |

## 字体与输入法

- `starsector-core/graphics/fonts/dyn_font/chars.txt`：33,472 bytes。
- `starsector-core/graphics/fonts/dyn_font/typefaces.dat`：9,195,573 bytes。
- `starsector-core/native/windows/ssime.dll`：274,944 bytes。
- `dyn_font=true`、`ssime_dll=true`（`inspect_root` 读数）。

`starsector-core/data/config/settings.json` 相关项：

| 设置 | 值 |
|---|---|
| localeOverride | `en_US` |
| cjkMode | `true` |
| enableScriptCaching | `false` |

## mods 目录

- `mods/` 为空目录。
- `mods/enabled_mods.json` **不存在**（不是空数组）。`inspect_root` 将其视为
  `enabled_count=0`、三个 `has_*` 均为 `false`；后续任务迁移 mod 时需自行创建
  该文件。

## vmparams

- 单行文件（3,306 bytes，无结尾换行）。
- `has_main_class=true`（含 `com.fs.starfarer.StarfarerLauncher`）。
- `has_agent=false`；`agents=[]`。
- `hypernova_flags=[]`：未注入任何 `-Dhypernova.*`，Hypernova 默认 off。

这是未安装任何路线组件的干净基线；路线 A/B 的注入顺序与幂等性由后续任务保证。

## 安装体积

- 实验根总计约 **395 MB**（`du -sh`）。

## inspect_root 关键读数

| 键 | 值 |
|---|---|
| localization.version | 2026.10.15 |
| localization.branch | startup-optimization |
| localization.language | zh-Hans |
| localization.game_version | 0.98a-RC8 |
| jre_version | 17.0.10 |
| dyn_font | true |
| ssime_dll | true |
| vmparams.has_main_class | true |
| vmparams.has_agent | false |
| vmparams.hypernova_flags | `[]` |
| mods.enabled_count | 0 |
| mods.has_hypernova / has_mixinfr / has_parallel | false / false / false |

## 备注

- 本安装根由汉化优化测试版安装器生成，第三方组件不随仓库分发。
- `SS098_Hypernova_Compat_AuditTest/install/` 已被 `.gitignore` 排除，只提交
  上述证据 JSON。
