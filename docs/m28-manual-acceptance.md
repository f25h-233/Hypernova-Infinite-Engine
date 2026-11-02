# M2.8 手动验收清单（场景切换强制 LRU：控制组 / 处理组）

> 本文件只写步骤与判定，不预填任何实机结果或数字。M2.8 的
> `scene_unload` 默认关闭（experimental）；只有两组都完成、全部判定通过后，
> 才可讨论是否保留或改变默认值。任何一项失败先记录，再修或回退。
> `scenePasses` 是 scene pass 的 chunk 数，不是纹理张数；
> `sceneEvictions` 是复位且 GL 删除成功的条数；`evicted` 是包含 scene pass
> 在内的复位总数（删除失败的也会计入）。
> gate 工具 fail-closed：缺 agent session anchor、缺 summary、summary 缺
> scene 键或值不是整数时明确报错，不输出全零 JSON。

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
   `sceneUnload`、`scenePasses`、`sceneEvictions`、`sceneEvictMsTotal`、
   `sceneEvictMsMax`、`scenePending`、`evicted`、`rematerialized`、
   `failedParked`、`liveBytes`。
2. `starsector.log` 最后 session 切片中五类纹理错误各自的出现次数：
   `Failed to load texture`、`VerifyError`、`ClassFormatError`、
   `AsyncException`、`isStateCorrupted`。
3. 战斗第 2 分钟的任务管理器“专用 GPU 内存”（Dedicated GPU memory）读数。
4. 主观检查：白块、贴图错位、明显卡顿、崩溃。

指标口径：

- `sceneEvictions` 只统计代理复位后 GL 旧纹理删除成功的条数；
  `evicted` 是复位总数，GL 删除失败也会计入（可能留下 VRAM 泄漏）。
- `sceneEvictMsMax` 是 scene pass 内单个 chunk 的墙钟耗时，不是帧时间 P99；
  >200 ms 的卡顿仍以主观/外部帧时间工具为准。
- `scenePasses=0` 时，先在 agent log 搜 `lazy: scene unload armed`：
  没有该行说明未 arm；有该行但淘汰为 0，说明 armed 后没有可淘汰候选
  （例如都被保护或已 touch）。

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
  --out build/m28/control.json --strict
```

说明：

- `--out` 把同一份 JSON 证据写入文件，stdout 也会输出。
- `--require-scene` 隐含 `--strict`，并在 `sceneEvictions <= 0` 时返回 1。
- `--strict`：五类纹理错误总数或 `failedParked` 大于 0 时返回 1；
  `starsector.log` 没有 `Fast Rendering: v0.9.` anchor 时也返回 1。
- 退出码：0 通过；1 证据/解析/严格门禁失败；2 给了 `--gpu-csv` 但没有
  任何有效 GPU 行。
- 缺少 agent session anchor、缺少有效 summary、summary 缺 scene 键时，
  stderr 输出一行 `m28_scene_gate: ...` 并返回非零，不会输出全零 JSON，
  也不会写 `--out`。

## 6. 判定

控制组（配置生效的自检）：

- summary 必须包含 scene 键，且 `sceneUnload=0`；
- 预期 `scenePasses=0`、`sceneEvictions=0`；若不是，说明
  `sceneUnload=false` 未生效，先排查启动参数。

处理组（全部满足才算通过）：

- summary 必须包含 scene 键，且 `sceneUnload=1`；
- `sceneEvictions > 0`；
- `failedParked = 0`；
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
