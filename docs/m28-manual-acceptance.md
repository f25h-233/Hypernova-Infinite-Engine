# M2.8 手动验收清单（场景切换强制 LRU：控制组 / 处理组）

> 本文件只写步骤与判定，不预填任何实机结果或数字。M2.8 的
> `scene_unload` 默认关闭（experimental）；只有两组都完成、全部判定通过后，
> 才可讨论是否保留或改变默认值。任何一项失败先记录，再修或回退。
> `scenePasses` 是 scene pass 的 chunk 数，不是纹理张数；
> `sceneEvictions` 是成功复位的条数；`evicted` 仍是包含 scene pass 在内的总数。

## 1. 前置

1. 构建并安装最新 agent：

   ```bash
   bash tools/java/build-mod.sh
   python tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite
   ```

2. 确认占位纹理存在且非空：
   `Starsector-098-260mods/starsector-core/graphics/hypernova/blank.png`。
3. 确认默认预算为 256 MB；本清单不使用 `budgetBytes` 诊断属性。
4. 每次会话结束后，读取：

   - `Starsector-098-260mods/saves/hypernova/scripts-agent.log` 的最后一条
     `lazy probe: summary`；
   - `Starsector-098-260mods/starsector-core/starsector.log` 的最后 session 切片（从
     `Fast Rendering: v0.9.` 开始）。

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

1. 最后一条 `lazy probe: summary` 中的：
   `sceneUnload`、`scenePasses`、`sceneEvictions`、`sceneEvictMsTotal`、
   `sceneEvictMsMax`、`scenePending`、`evicted`、`rematerialized`、
   `failedParked`、`liveBytes`。
2. `starsector.log` 最后 session 切片中五类纹理错误各自的出现次数：
   `Failed to load texture`、`VerifyError`、`ClassFormatError`、
   `AsyncException`、`isStateCorrupted`。
3. 战斗第 2 分钟的任务管理器“专用 GPU 内存”（Dedicated GPU memory）读数。
4. 主观检查：白块、贴图错位、明显卡顿、崩溃。

可选 GPU 曲线（gate 工具不强制）：每 2 s 采样一次并写成
`timestamp,dedicated_mb,shared_mb` CSV，例如：

```bash
python -I -c "import sys; sys.path.insert(0,'tools'); import smoke_run; print(smoke_run.process_gpu_memory_mb(PID))"
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
- `--strict`：五类纹理错误总数或 `failedParked` 大于 0 时返回 1。
- `--require-scene`：在 `--strict` 基础上，`sceneEvictions <= 0` 时返回 1。
- 缺少 `lazy probe: summary` 行时工具明确报错，不会输出全零报告。

## 6. 判定

控制组（配置生效的自检）：

- `sceneUnload=0`、`scenePasses=0`、`sceneEvictions=0`；若不是，说明
  `sceneUnload=false` 未生效，先排查启动参数。

处理组（全部满足才算通过）：

- `sceneEvictions > 0`；
- `failedParked = 0`；
- 五类纹理错误总数为 0；
- 无白块、贴图错位、崩溃；
- 战斗第 2 分钟的进程 GPU dedicated 低于控制组。

任一项失败：记录日志与读数，关闭 `scene_unload`（
`textures.lazy.eviction.scene_unload.enabled=false` 或
`-Dhypernova.textures.lazy.eviction.sceneUnload=false`），回退到当前 LRU 行为。
不要用单组或部分字段通过代替整组判定。
