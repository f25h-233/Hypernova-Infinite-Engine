# M6 兼容性审计工作区

本目录只放 M6 兼容性审计的脚本清单、证据摘要与用户实机记录。
游戏资源、mod 副本、启动档副本、原始日志、截图与导出数据不入库。

| 子目录/文件 | 内容 | 入库 |
|---|---|---|
| `evidence/` | 自动证据摘要 `.json`（`matrix.json`、`manifest-audit.json`、`fail-open.json`、`log-audit-current.json`、`menu-smoke.json`） | 是 |
| `<label>/` | `m6_session.py` 会话目录：`session.json`、`session-meta.json`、人工记录 `notes.md`/`env.md` | 是（仅 `.json`/`.md`） |
| `<label>/screens/` | 实机截图 | 否（已 gitignore） |
| `<label>/logs/` | `pre-*`/`rotated-*` 轮转日志 | 否（已 gitignore） |
| `SS098.../**/*.csv`、`**/*.dump` | 导出的采样/内存数据 | 否（已 gitignore） |
| `scripts/` | 本目录专用的一键命令清单 | 是 |
| `mods/` | 测试 mod 副本/链接 | 否 |
| `vmparams/` | 审计专用启动档副本 | 否 |
| `backups/` | `m6_env_snapshot.py` 生成的快照 | 否 |
| `install/`、`vendor/` | 本地实验安装与第三方工件 | 否 |

口径：`m6_session.py` 的会话产物在 `<audit-root>/<label>/`，不是
`evidence/<label>/`；`evidence/` 只放自动审计摘要。
