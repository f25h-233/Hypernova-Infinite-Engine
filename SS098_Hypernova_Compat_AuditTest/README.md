# M6 兼容性审计工作区

本目录只放 M6 兼容性审计的脚本清单、证据摘要与用户实机记录。
游戏资源、mod 副本、启动档副本、原始日志不入库。

| 子目录 | 内容 | 入库 |
|---|---|---|
| `evidence/` | `matrix.json`、`manifest-audit.json`、`fail-open.json`、`menu-smoke.json`、会话摘要 | 是（仅 `.json`） |
| `scripts/` | 本目录专用的一键命令清单 | 是 |
| `mods/` | 测试 mod 副本/链接 | 否 |
| `vmparams/` | 审计专用启动档副本 | 否 |
| `backups/` | `m6_env_snapshot.py` 生成的快照 | 否 |
