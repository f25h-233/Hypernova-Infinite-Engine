# M6 实机验收 runbook：汉化 / ChineseInputFix / 字体 UI 纹理

> 本文件只写步骤与判定，不预填结果。M6 的实机 gate 必须由真实游戏进程 +
> 真实存档完成；菜单 smoke、单轮启动、`m6_session.py end` 的自动汇总都不能
> 替代战役/战斗/读档/中文输入验收。
>
> Hypernova 在 260mods 上是 **agent-only**（`enabled_mods.json` 不含
> `hypernova_infinite_engine`）；本 runbook 不启用主 mod，不改发行默认值，
> 只通过临时 `-D` 启动参数打开 probe/lazy 以便收集证据。
>
> 任一项失败：先按 §5 做 no-Hypernova 对照，再决定是否归因 Hypernova；
> 未执行或未对照的项在判定表写 `pending` / `fail`，不得写 `pass`。

## 1. 前置

### 1.1 构建与安装

```bash
bash tools/java/build-mod.sh
bash tools/java/install-manifest.sh Starsector-098-260mods
python tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite
```

### 1.2 环境基线快照（只备份，不改源文件）

在启用 ChineseInputFix、改任何设置之前做一份快照，作为唯一回滚点：

```bash
python -I tools/m6_env_snapshot.py snapshot \
  --game-root Starsector-098-260mods \
  --dest SS098_Hypernova_Compat_AuditTest/backups \
  --label baseline-2026-11-03
```

若 `backups/baseline-2026-11-03/` 已存在（Task 2 已做过），直接复用它，
不要覆盖；`backups/` 不入库。快照覆盖 4 个文件：

- `mods/enabled_mods.json`
- `mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json`
- `Miko_Lite.txt`
- `starsector-core/data/config/settings.json`

### 1.3 确认基线状态

```bash
python -I - <<'PY'
import json
from pathlib import Path
path = Path("Starsector-098-260mods/mods/enabled_mods.json")
mods = json.loads(path.read_text(encoding="utf-8"))["enabledMods"]
print("enabled_count:", len(mods))
print("hypernova_infinite_engine:", "hypernova_infinite_engine" in mods)
print("ChineseInputFix:", "ChineseInputFix" in mods)
PY
```

期望：`hypernova_infinite_engine: False`（agent-only）；`ChineseInputFix: False`
（尚未启用，§2 临时启用）。任一不符先停下核对环境，不要继续。

再用矩阵工具确认默认值与字体/UI/纹理覆盖面：

```bash
python -I tools/m6_audit_matrix.py \
  --game-root Starsector-098-260mods \
  --out SS098_Hypernova_Compat_AuditTest/evidence/matrix-acceptance.json --text
```

记录：`mods.enabled_count`、`chinese_input_fix.present/version/enabled`、
`hypernova.lazy` / `eviction` / `scene_unload`（必须为 false）、
`font_ui_mods` 中 `fonts=true` / `ui=true` 的 mod、`strings.cjk_ratio`。
2026-11-03 基线读数（供对照，不写死）：256 mods、ChineseInputFix 2.0.0
存在但未启用、`lazy=false`、`eviction=false`、`scene_unload=false`、
`cjk_ratio=1.0`；字体 mod 含 `ApproLight`/`BoxUtil`/`lw_console`/`szb`，
UI mod 含 `BoxUtil`/`CjyToyBox`/`aotd_*`/`exoticatechnologies`/`lunalib` 等。

### 1.4 生成审计专用启动档（临时 probe + lazy）

`-D` 必须写在 `com.fs.starfarer.StarfarerLauncher` **之前**；不要修改
`Miko_Lite.txt` 本身。下面生成 `SS098_Hypernova_Compat_AuditTest/vmparams/`
下的副本（该目录不入库）：

```bash
python -I - <<'PY'
from pathlib import Path

src = Path("Starsector-098-260mods/Miko_Lite.txt")
dst = Path("SS098_Hypernova_Compat_AuditTest/vmparams/Miko_Lite_m6_probe.txt")
main_class = "com.fs.starfarer.StarfarerLauncher"
flags = [
    "-Dhypernova.frameProbe=true",
    "-Dhypernova.textures.lazy=true",
    "-Dhypernova.textures.lazy.dds=true",
    "-Dhypernova.textures.lazy.eviction=true",
    "-Dhypernova.textures.lazy.eviction.sceneUnload=false",
]
lines = src.read_text(encoding="utf-8").splitlines()
out = []
for line in lines:
    stripped = line.strip()
    if stripped.startswith("-Dhypernova."):
        continue  # 去掉旧临时开关，统一由本次 runbook 控制
    if stripped == main_class:
        out.extend(flags)
    out.append(line)
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text("\n".join(out) + "\n", encoding="utf-8")
print(dst)
PY
grep -n "com.fs.starfarer.StarfarerLauncher" \
  SS098_Hypernova_Compat_AuditTest/vmparams/Miko_Lite_m6_probe.txt
```

启动（`VmParams` 由 java 以 `starsector-core` 为工作目录解析）：

```bash
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden \
  -File "Starsector-098-260mods/tools/LaunchMiko.ps1" \
  "jdk-28+13" "..\..\SS098_Hypernova_Compat_AuditTest\vmparams\Miko_Lite_m6_probe.txt"
```

启动后到主菜单，按 M4 的 §3 确认 agent probe 已生效（`scripts-agent.log`）：

```bash
LOG=Starsector-098-260mods/saves/hypernova/scripts-agent.log
grep -c "frame probe: enabled" "$LOG"
grep -c "frame probe: hook added to Display.update" "$LOG"
grep -c "frame probe: samples started from Display.update" "$LOG"
grep -c "HYPERNOVA_FRAME" "$LOG"
```

任一为 0：agent 没加载、agent jar 是旧包或 `-D` 位置不对；停止本组，
不要拿空证据填判定表。

## 2. 临时启用 ChineseInputFix

**只在 §1.2 快照成功之后做。** 结束必须按 §7 恢复。

```bash
python -I - <<'PY'
import json
from pathlib import Path

path = Path("Starsector-098-260mods/mods/enabled_mods.json")
data = json.loads(path.read_text(encoding="utf-8"))
mods = data["enabledMods"]
if "ChineseInputFix" not in mods:
    mods.append("ChineseInputFix")
path.write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print("enabled_count:", len(mods))
print("ChineseInputFix:", "ChineseInputFix" in mods)
PY
```

确认矩阵中已生效（`chinese_input_fix.enabled` 必须为 true）：

```bash
python -I tools/m6_audit_matrix.py --game-root Starsector-098-260mods --text \
  | grep -A4 '"chinese_input_fix"'
```

记录到 `SS098_Hypernova_Compat_AuditTest/D-ime/env.md`（或本组
`session-meta.json` 旁边）：

- 输入法（如 微软拼音 / 搜狗 / 小狼毫）
- 系统语言（如 中文（简体，中国））
- 游戏分辨率与窗口模式（窗口/全屏/无边框）
- ChineseInputFix 版本（矩阵 `chinese_input_fix.version`）

> **约束口径**：M6 的自动化工具（`m6_session.py`、`m6_audit_matrix.py`、
> `m6_env_snapshot.py`）**从不写** `enabled_mods.json` / `hypernova.json` /
> `Miko_Lite.txt` / `settings.json`；上面的修改只由操作者按 brief 手动
> 执行，且必须用 §1.2 快照 + §7 `restore --force` 回滚。

## 3. 会话分组

每组开始前**先完全退出游戏**，再执行 `start`（`start` 会把旧日志复制到
审计目录后移走；游戏占用日志时移动会失败）。组内只跑本组场景，
结束后退出游戏，再执行 `end`。`end` 要求同 label 的
`SS098_Hypernova_Compat_AuditTest/<label>/session-meta.json` 存在；漏跑
`start` 或 label 拼错会 `FATAL` 且不写 `session.json`。`start` 之后没有
产生新日志（或日志仍是 `start` 之前的旧文件）时，`end` 会给出 `ok=false`，
`problems` 含 `no new logs since start`，不会把旧日志记成本组证据。

通用命令（把 `<label>` 换成下表的值）：

```bash
python -I tools/m6_session.py start \
  --game-root Starsector-098-260mods \
  --evidence-root SS098_Hypernova_Compat_AuditTest \
  --label <label>

# 正常启动（§1.4）→ 执行本组场景 → 完全退出游戏

python -I tools/m6_session.py end \
  --game-root Starsector-098-260mods \
  --evidence-root SS098_Hypernova_Compat_AuditTest \
  --label <label>
```

| 组 | label | 场景 |
|---|---|---|
| A | `A-campaign` | 主菜单 → 新战役 → 星系内移动 → 打开舰队/改装 → 保存 → 读档 |
| B | `B-combat` | 进入一场战斗（小舰队）→ 返回战役 → 保存 → 读档 |
| C | `C-resolution` | 分辨率切换（窗口 ↔ 全屏）→ alt-tab 切出/切回 → 返回战机 |
| D | `D-ime` | 中文输入：改名、搜索、对话/文本输入框；每个场景至少输入 2 个中文字 |
| E | `E-visual` | 字体/UI 视觉检查：菜单、战役 HUD、对话、改装界面、战斗 HUD |

分组注意：

- **A/B**：使用干净的小舰队存档；不要用 260mods 已知问题场景（Star Wars
  新开局、超大舰队旧档、Exotica 改装空 cast、生涯大地图长时间移动）作为
  Hypernova 判定依据。
- **B**：必须真正进入战斗（不是菜单/加载画面），返回战役后再保存/读档。
- **C**：每次切换后至少停留 10 秒并观察画面；alt-tab 后确认能切回且不崩。
- **D**：ChineseInputFix 已在 §2 启用；输入中文后确认文本真正进入输入框，
  不只是候选框出现。截图留给 §4。
- **E**：重点看豆腐块（□□）、缺字、文字重叠/错位、按钮文字截断；每个
  界面至少截一张图。

### 3.1 `start` 失败后的恢复

`start` 在复制/移动/写 meta 任一步失败时会：

- 删除本次创建的 `logs/pre-*.log`；
- 把已经移动的 `logs/rotated-*.log` 移回原路径；
- 只有在回滚完整时才删除空的 `logs/`；
- 向 stderr 打一行 `FATAL: ...` 并返回 rc=1。

恢复步骤：

1. 若 stderr **没有** `rollback incomplete`：原日志已回到
   `starsector-core/starsector.log` / `saves/hypernova/scripts-agent.log`，
   直接重跑同一 label 即可（不会再有 `FileExistsError`）。
2. 若进程在“日志已移动、`session-meta.json` 未写”之间崩溃（目录无 meta，
   但有 `rotated-*.log`）：
   - 对应源日志缺失：`start` 会先把 `rotated-<name>.log` 移回源路径，再
     正常轮转；不会删除 `pre-*`/`rotated-*`。
   - 源日志和 `rotated-*.log` 同时存在：`start` 拒绝重跑并报
     `FATAL: incomplete previous start ...`，保留所有
     `pre-*`/`rotated-*`。先人工确认哪份是原始现场（必要时把 rotated
     移回源路径或另存），再重跑；无法判断就换 label。
   - 只有 `pre-*` 而源日志缺失：同样拒绝（`pre` 可能是唯一副本），
     不得手工删除。
   - 源日志存在但与 `pre-*` 内容不同，或 `pre-*` 与 `rotated-*` 内容
     不同：`start` 拒绝并报
     `FATAL: previous pre-* differs from source/rotated; refuse to overwrite`。
     `pre-*` 可能是上一组失败现场的唯一副本，**不要覆盖或删除**；先另存
     （或人工确认哪份是原始现场）再重跑。
3. 若 `session-meta.json` 已存在（完整旧会话）：`start` 一律拒绝
   （`session already started`）。只有确认旧证据已另存后，才可手工删除
   `SS098_Hypernova_Compat_AuditTest/<label>/` 来重用该 label。
4. 若出现 `rollback incomplete`：不要删除任何日志。先确认游戏已完全退出、
   日志句柄已释放，再把
   `SS098_Hypernova_Compat_AuditTest/<label>/logs/rotated-*.log` 手工移回
   原路径；确认原日志恢复后删除该 `logs/` 目录，再重跑。仍被占用就换
   label（如 `A-campaign-r2`），旧目录保留为失败现场。
5. `logs/` 里若有非本工具命名的文件，`start` 会拒绝删除并抛
   `FileExistsError`；这是防止误删，不是轮转成功。换 label，或确认文件
   无用后手工处理。
6. 跨盘 evidence root 已用 `shutil.move` 回退（必要时先复制再删除），
   不需要手工处理 WinError 17。
7. `start` 找不到任何日志时仍 rc=0（首次运行合法），但会向 stderr 打一行
   `WARNING: no logs found under ...`；看到它说明 `--game-root` 指错或
   游戏还没产生日志，本组不能作为证据。

## 4. 证据检查

每组 `end` 后检查 `session.json`（实际路径是
`SS098_Hypernova_Compat_AuditTest/<label>/session.json`，不是
`evidence/<label>/`）：

```bash
# 把 A-campaign 换成当前组的 label（作为 stdin 脚本的第一个参数传入）
python -I - A-campaign <<'PY'
import json
import sys
from pathlib import Path

label = sys.argv[1]
path = Path("SS098_Hypernova_Compat_AuditTest") / label / "session.json"
data = json.loads(path.read_text(encoding="utf-8"))
keys = {
    "ok": data["ok"],
    "problems": data["problems"],
    "anchor_found": data["starsector_session"]["anchor_found"],
    "frame_present": data["frame_probe"]["present"],
    "frame_source": data["frame_probe"].get("source"),
    "frame_complete": data["health"]["frame_probe_complete"],
    "lazy_present": data["lazy"]["present"],
    "lazy_main_bound": data["health"]["lazy_main_bound"],
    "lazy_failed_zero": data["health"]["lazy_failed_zero"],
    "lazy_disabled_zero": data["health"]["lazy_disabled_zero"],
    "lazy_dim_mismatch_zero": data["health"]["lazy_dim_mismatch_zero"],
    "lazy_failed_parked_zero": data["health"]["lazy_failed_parked_zero"],
    "new_logs_ok": data["new_logs_ok"],
    "texture_errors_total": data["texture_errors_total"],
    "log_audit_total": data["log_audit"]["total"],
    "log_audit_complete": data["log_audit"]["complete"],
}
print(json.dumps(keys, ensure_ascii=False, indent=2))
sys.exit(0 if data["ok"] else 1)
PY
```

- 通过条件：`ok=true`，即 `anchor_found=true`、`frame_probe.present=true`、
  `frame_probe.source="agent"`、`health.frame_probe_complete=true`、
  `lazy.present=true`、`health.lazy_main_bound=true`、lazy
  `failed/disabled/dimMismatch/failedParked` 全为 0、`new_logs_ok=true`、
  `texture_errors_total=0`、`log_audit.complete=true`、`log_audit.total=0`；
  `problems` 为空。
- `end` 失败（rc=1）时会同时向 stderr 打一行 `m6_session: session not ok:
  label=...: <problems>`；把这行和 `session.json` 一起留档。
- `frame_probe.source` 在 agent-only 会话必须是 `agent`；出现 `game` 说明
  主 mod probe 也在跑，不要混用两条来源（`end` 会判 `ok=false`）。
- `log_audit.observations`（ChineseInputFix / 独立词 IME 命中）是存在性
  观察，**不参与失败判定**；不要因为出现观察词就把 `ok` 判成 false，也
  不要用 0 次命中反推“中文输入正常”（以 D 组实际输入结果为准）。
- `start` 会把旧日志复制为 `logs/pre-*.log`，移走的现场是
  `logs/rotated-*.log`；两者都保留，便于追上一组失败。
- 截图放 `SS098_Hypernova_Compat_AuditTest/<label>/screens/`。
  **截图不入库**：`.gitignore` 已忽略
  `SS098_Hypernova_Compat_AuditTest/**/screens/`、`**/logs/`、`*.csv`、
  `*.dump`；只提交 `.json`/`.md` 摘要。
- 手动观察（豆腐块/缺字/错位/输入失败）按组记在
  `SS098_Hypernova_Compat_AuditTest/<label>/notes.md`，并汇总到
  `docs/m6-results.md` §4。

## 5. no-Hypernova 对照

任何一组失败（崩溃、纹理错误、中文输入失败、明显 UI 破损）先做对照，
再决定归因：

1. 用现成对照启动档重跑同一场景：
   `Starsector-098-260mods\启动-M27-对照-无Hypernova.bat`
   （`Miko_Lite_noagent.txt`，无 Hypernova agent）。
2. 对照同样可用 `m6_session.py start/end` 轮转日志；但对照会话没有
   Hypernova，`frame_probe`/`lazy` 按设计会缺失，`end` 的 `ok` 会是
   false（`problems` 会含 no frame probe / source 不是 agent 等）。
   **对照只看 `texture_errors_total` 与 `log_audit.total`**，不套用 §4 的
   `ok=true` 判定，并与 Hypernova 组的日志切片逐条比对。
3. 判定：
   - 对照也复现 → 260mods/汉化/字体/UI 既有问题，标注“非 Hypernova”；
   - 只有 Hypernova 组复现 → 记录最小复现步骤、日志行号、对应注入点，
     交回 M6 结果文档 §5。
4. 不要为了“让对照通过”临时改 mod 列表或安装内容；对照必须与实验组
   同 mod 集、同存档、同分辨率（只差 Hypernova agent）。

## 6. 判定表

结果列只允许 `pass` / `fail` / `pending`；未执行的保持 `pending`，不得
预填 `pass`。出口 1–5 对应 M6 kickoff 的出口定义。

| 出口 | 场景/证据 | 通过条件 | 结果 | 证据路径 |
|---|---|---|---|---|
| 1. 汉化测试版可用 | A/B/D/E 组菜单、战役、战斗、读档画面 | 无豆腐块、无缺字、无错位；A/B `session.json` `ok=true` | pending | `SS098_Hypernova_Compat_AuditTest/A-campaign/`、`.../B-combat/`、`.../E-visual/screens/` |
| 2. ChineseInputFix 中文输入 | D 组改名/搜索/对话输入 | 每个场景至少 2 个中文字成功输入，不失败、不崩；`session.json` `ok=true` | pending | `SS098_Hypernova_Compat_AuditTest/D-ime/`、`.../D-ime/env.md` |
| 3. 字体/UI/纹理 mod 无五类错误 | A–E 全部 `session.json` | `texture_errors_total=0` 且 `log_audit.total=0`（五类：`Failed to load texture` / `VerifyError` / `ClassFormatError` / `AsyncException` / `isStateCorrupted`） | pending | `SS098_Hypernova_Compat_AuditTest/<label>/session.json` |
| 4. manifest/skip generation 与 fail-open | `m6_manifest_audit.py` 自动证据 | `installed.ok=true`、skip v1/v2 generation 与 manifest 一致、无宿主 `starsector-core/lazy-skip-*`、`defaults.lazy/eviction/scene_unload=false`；`fail_open.ok=true` | pending | `SS098_Hypernova_Compat_AuditTest/evidence/manifest-audit.json`、`.../evidence/fail-open.json` |
| 5. 分辨率/全屏/alt-tab | C 组 | 切换与 alt-tab 后不崩、可继续操作、无纹理错误；`session.json` `ok=true` | pending | `SS098_Hypernova_Compat_AuditTest/C-resolution/` |

出口 6（默认仍 off）与出口 7（结果为 `docs/m6-results.md`）由自动化
证据与 Task 6 结果文档覆盖，不在此表重复判定；`docs/m6-results.md` §6
必须明确 `hypernova.json` 发行默认未改。

每组另外记录：

| 组 | 结果（pass/fail/pending） | 备注（场景/异常/对照） |
|---|---|---|
| A 战役 | pending | |
| B 战斗 | pending | |
| C 分辨率/alt-tab | pending | |
| D 中文输入 | pending | |
| E 字体/UI 视觉 | pending | |

## 7. 回滚

1. 恢复 4 个环境文件（含临时启用的 ChineseInputFix）：

   ```bash
   python -I tools/m6_env_snapshot.py restore \
     --snapshot SS098_Hypernova_Compat_AuditTest/backups/baseline-2026-11-03 \
     --force
   ```

   > 威胁模型：manifest 里的 sha256 视为本机可信输入（快照目录本身不在
   > 攻击面内）；`game_root` 取自 manifest，restore 只保证写入目标不逃逸
   > 该 root。`files` 为空、manifest 记录了 `missing`，或文件数与预期不符
   > 的 partial 快照会被拒绝（一行 `FATAL` + rc1），不会假成功；遇到时
   > 补齐文件后重做快照，不要手工只恢复一部分。

2. 复核：

   ```bash
   python -I - <<'PY'
   import json
   from pathlib import Path
   mods = json.loads(Path(
       "Starsector-098-260mods/mods/enabled_mods.json"
   ).read_text(encoding="utf-8"))["enabledMods"]
   print("ChineseInputFix:", "ChineseInputFix" in mods)
   print("hypernova_infinite_engine:", "hypernova_infinite_engine" in mods)
   PY
   ```

   期望两者都为 False。

3. 关闭临时 `-D` 参数：删除
   `SS098_Hypernova_Compat_AuditTest/vmparams/Miko_Lite_m6_probe.txt`
   或直接不再使用；`Miko_Lite.txt` 未被修改（快照可恢复）。
4. **不改发行默认**：`hypernova.json`（发行版）的
   `textures.lazy.enabled`、`eviction.enabled`、`sceneUnload.enabled`
   与 frame probe 默认值保持 off；M6 不改变任何默认开关。
5. `restore --force` 会把 `settings.json` 一并恢复；若验收期间在游戏内
   主动改过分辨率并希望保留，先单独记录再恢复，避免误覆盖。
