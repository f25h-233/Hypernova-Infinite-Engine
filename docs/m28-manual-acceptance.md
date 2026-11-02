# M2.8 手动验收清单（场景切换强制 LRU：控制组 / 处理组）

> 本文件只写步骤与判定，不预填任何实机结果或数字。M2.8 的
> `scene_unload` 默认关闭（experimental）；只有两组都完成、全部判定通过后，
> 才可讨论是否保留或改变默认值。任何一项失败先记录，再修或回退。
> `scenePasses` 是 scene pass 的 chunk 数，不是纹理张数；
> `sceneEvictions` 是复位且 GL 删除成功的条数；`evicted` 是包含 scene pass
> 在内的复位总数（删除失败的也会计入）。
> gate 工具 fail-closed：缺 agent session anchor、缺 summary、summary 缺
> scene/健康键或值类型不对时明确报错，不输出全零 JSON；strict 还会在
> lazy fail-open（`failed`/`disabled`/`dimMismatch` 非 0 或 `main=none`）
> 时失败。
>
> **2026-11-02 收口：Task 4 实机 gate 由用户跳过**（260mods 生涯大地图移动
> 严重卡顿，不作为 Hypernova 结论）。M2.8 默认 off，不宣称显存收益；本清单
> 保留为将来环境允许时的可选复跑步骤。详见 `docs/m28-results.md`。

## 1. 前置

1. 构建并安装最新 agent：

   ```bash
   bash tools/java/build-mod.sh
   python tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite
   ```

2. 确认占位纹理存在且非空：
   `Starsector-098-260mods/starsector-core/graphics/hypernova/blank.png`。
3. 确认默认预算为 256 MB；本清单不使用 `budgetBytes` 诊断属性。
4. 每组运行前清空或改名以下日志，或使用该组专属副本：

   - `Starsector-098-260mods/saves/hypernova/scripts-agent.log`
   - `Starsector-098-260mods/starsector-core/starsector.log`

   工具只认最后一个 `hypernova agent premain` 之后的 summary；
   `starsector.log` 必须包含 `Fast Rendering: v0.9.` session anchor。
   没有 anchor 或没有有效 summary 时，`--strict` 会返回非零而不是给出零值报告。

## 2. 两组开关（vmparams 配方）

以 `Starsector-098-260mods/Miko_Lite_m27_diag_4m.txt` 为模板：

1. 删除 `-Dhypernova.textures.lazy.eviction.budgetBytes=...` 行。
2. 保留以下行（若模板已有则原样保留）：

   ```text
   -Dhypernova.textures.lazy=true
   -Dhypernova.textures.lazy.dds=true
   -Dhypernova.textures.lazy.eviction=true
   -javaagent:../mods/hypernova_infinite_engine/jars/hypernova.agent.jar
   ```

3. 另存为两份，放在 `Starsector-098-260mods/` 根目录：

   - 控制组 `Miko_Lite_m28_control.txt`：加入
     `-Dhypernova.textures.lazy.eviction.sceneUnload=false`；
   - 处理组 `Miko_Lite_m28_treatment.txt`：加入
     `-Dhypernova.textures.lazy.eviction.sceneUnload=true`。

4. 用 `Starsector-098-260mods/tools/LaunchMiko.ps1` 启动对应文件。可照抄
   `启动-M27-诊断-4MiB.bat`，只改传给 `LaunchMiko.ps1` 的 vmparams 文件名，例如：

   ```bat
   powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0tools\LaunchMiko.ps1" "jdk-28+13" "..\Miko_Lite_m28_control.txt"
   ```

   处理组把文件名换成 `..\Miko_Lite_m28_treatment.txt`。
5. 不要设置 `-Dhypernova.textures.lazy.eviction.budgetBytes`。

## 3. 场景

- 使用干净存档 / 小舰队。
- 战役场景停留至少 60 s。
- 进入一场战斗并打至少 3 min，然后返回战役。
- 两组尽量使用同一存档、同一舰队、同一战斗，减少场景差异。

## 4. 记录

每个组各记录一份：

1. 最后一条有效 `lazy probe: summary` 中的：
   `failed`、`disabled`、`dimMismatch`、`failedParked`、`main`、`ddsDisabled`、
   `sceneUnload`、`scenePasses`、`sceneEvictions`、`sceneEvictMsTotal`、
   `sceneEvictMsMax`、`scenePending`、`evicted`、`rematerialized`、`liveBytes`。
2. `starsector.log` 最后 session 切片中五类纹理错误各自的出现次数：
   `Failed to load texture`、`VerifyError`、`ClassFormatError`、
   `AsyncException`、`isStateCorrupted`。
3. 战斗第 2 分钟的任务管理器“专用 GPU 内存”（Dedicated GPU memory）读数。
4. 主观检查：白块、贴图错位、明显卡顿、崩溃。

指标口径：

- `sceneEvictions` 只统计代理复位后 GL 旧纹理删除成功的条数；
  `evicted` 是复位总数，GL 删除失败也会计入（可能留下 VRAM 泄漏）。
- `scenePasses` 是 chunk 数；`scenePending` 是本次切换剩余的 chunk 数
  （0–8，最多 8 个 chunk，每个默认最多 64 张）。
- `sceneEvictMsTotal` 是各 chunk 墙钟耗时之和；`sceneEvictMsMax` 是单个
  chunk 的墙钟耗时，不是帧时间 P99。>200 ms 的卡顿仍以主观/外部帧时间
  工具为准。
- `scenePasses=0` 时，先在 agent log 搜 `lazy: scene unload armed`：
  没有该行说明未 arm；有该行但 `scenePasses=0` 说明没有任何 chunk 真正执行
  （例如首个 chunk 的 2 s 延迟前已离开战斗，或 scene pass 窗口过期）。
  如果 chunk 执行了但没淘汰，`scenePasses` 会 ≥1（空候选/全失败也会计一次
  chunk），此时再看 `sceneEvictions=0` 与候选原因；不能把“无候选”当成
  `scenePasses=0` 的解释。
- `disabled=1` 表示 lazy 已 fail-open（自动禁用）；此时控制组不是有效
  基线，两组都需要恢复 lazy 健康后重跑。`ddsDisabled=1` 只记录、不作为
  strict 失败条件（DDS 不可用不等于 lazy 失效）。

可选 GPU 曲线（gate 工具不强制）。把 `PID` 换成游戏进程 PID，运行到战斗结束，
Ctrl-C 停止；输出可直接作为 `--gpu-csv`：

```bash
mkdir -p build/m28
python -I - "$PID" > build/m28/gpu-treatment.csv <<'PY'
import sys
import time

sys.path.insert(0, "tools")
import smoke_run

print("timestamp,dedicated_mb,shared_mb")
start = time.monotonic()
while True:
    dedicated, shared = smoke_run.process_gpu_memory_mb(int(sys.argv[1]))
    stamp = f"{time.monotonic() - start:.1f}"
    print(f"{stamp},{'' if dedicated is None else dedicated},"
          f"{'' if shared is None else shared}", flush=True)
    time.sleep(2)
PY
```

## 5. 门禁命令

处理组：

```bash
python tools/m28_scene_gate.py \
  --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
  --starsector-log Starsector-098-260mods/starsector-core/starsector.log \
  --out build/m28/treatment.json --require-scene --strict
```

控制组：

```bash
python tools/m28_scene_gate.py \
  --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
  --starsector-log Starsector-098-260mods/starsector-core/starsector.log \
  --out build/m28/control.json --require-control --strict
```

说明：

- `--out` 把同一份 JSON 证据写入文件，stdout 也会输出。
- `--require-scene` 隐含 `--strict`，并在 `sceneEvictions <= 0` 时返回 1。
- `--require-control` 隐含 `--strict`，要求 `sceneUnload=0`、
  `scenePasses=0`、`sceneEvictions=0`；与 `--require-scene` 互斥，
  同时使用会由 argparse 报错（exit 2）。
- `--strict` 的健康门：`failed` / `disabled` / `dimMismatch` /
  `failedParked` 任一非 0，或 `main` 缺失/为 `none`，返回 1；
  五类纹理错误总数非 0、`starsector.log` 没有 `Fast Rendering: v0.9.`
  anchor 也返回 1。
- 退出码：0 通过；1 证据/解析/严格门禁失败；2 给了 `--gpu-csv` 但没有
  任何有效 GPU 行，或控制/处理互斥参数同时出现。
- 缺少 agent session anchor、缺少有效 summary、summary 缺 scene 或健康键
  时，stderr 输出一行 `m28_scene_gate: ...` 并返回非零，不会输出全零
  JSON，也不会写 `--out`。

## 6. 判定

控制组（配置生效的自检）：

- summary 必须包含 scene 键与健康键，且 `sceneUnload=0`；
- `failed=disabled=dimMismatch=failedParked=0`，`main != none`；
- `scenePasses=0`、`sceneEvictions=0`；若不是，说明
  `sceneUnload=false` 未生效，先排查启动参数；
- 若 `disabled=1`，说明 lazy 已 fail-open，本组不是有效基线，恢复 lazy
  健康后重跑。

处理组（全部满足才算通过）：

- summary 必须包含 scene 键与健康键，且 `sceneUnload=1`；
- `failed=disabled=dimMismatch=failedParked=0`，`main != none`；
- `sceneEvictions > 0`；
- 五类纹理错误总数为 0；
- 无白块、贴图错位、崩溃；
- 战斗第 2 分钟的进程 GPU dedicated 低于控制组。

任一项失败：记录日志与读数，关闭 `scene_unload`，回退到当前 LRU 行为：

- 配置文件
  `mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json`
  中设 `textures.lazy.eviction.scene_unload.enabled=false`；或
- 启动参数加
  `-Dhypernova.textures.lazy.eviction.sceneUnload=false`。

不要用单组或部分字段通过代替整组判定。
