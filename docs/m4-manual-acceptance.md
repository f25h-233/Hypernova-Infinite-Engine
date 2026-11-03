# M4 手动验收：A→B 长会话与 >200 ms stutter

> 本文件只写步骤与判定，不预填结果。frame-time probe 默认关闭，只有
> 显式加 `-Dhypernova.frameProbe=true` 才采样。A→B 与 stutter 必须由
> 真实游戏进程 + 真实存档完成；菜单快照、单轮 smoke、`sceneEvictMsMax`
> 都不能替代。
>
> **M4.1 起 probe 在 agent 侧**：`-javaagent` 的 `FrameProbeTransformer` 只在
> `org.lwjgl.opengl.Display.update(Z)V` 入口采样；`update()V` 内部委托到
> `update(Z)V`，只 patch 后者可避免同一帧重复采样。
> `Display.update` 是 title/campaign/combat 循环里的每帧 buffer swap，所以
> 260mods 的 **agent-only** 配置即可产帧，不需要启用
> `hypernova_infinite_engine`，也不需要改 `enabled_mods.json`。主 mod 的
> `FrameTimeProbe` 保留给完整产品环境；一份报告只能来自一个 source，不能混用。

## 1. 前置

1. **构建并安装**（agent 承载 probe，必须刷新，否则跑的还是旧 class）：
   `bash tools/java/build-mod.sh` →
   `bash tools/java/install-manifest.sh Starsector-098-260mods` →
   `python tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite`
2. 确认 `Starsector-098-260mods/starsector-core/graphics/hypernova/blank.png` 非空。
3. 每组开始前清空或改名：
   - `Starsector-098-260mods/saves/hypernova/scripts-agent.log`
   - `Starsector-098-260mods/starsector-core/starsector.log`
4. 使用干净存档 / 小舰队；不要用 260mods 生涯大地图、Star Wars 新开局、
   超大舰队或 Exotica 改装 UI（这些是已知 mod 环境问题，不归因 Hypernova）。
5. 默认开关不动；本验收只用启动参数临时开启。
6. **不需要**启用主 mod，**不需要**备份/修改 `enabled_mods.json`。
   260mods 默认 agent-only 就是本验收的主路径。

**可选完整产品环境（Base）**：`Starsector-098-Base` 已启用主 mod，mod 数少，
可作为完整产品环境。probe 仍是 agent 侧：

1. 刷新主 jar：`bash tools/java/install-manifest.sh Starsector-098-Base`
2. 刷新 agent：`python tools/install_agent.py --game Starsector-098-Base --env base`
3. 在 `Starsector-098-Base/starsector-core/fr.vmparams` 的
   `com.fs.starfarer.StarfarerLauncher` **之前**插入下面五行
   （argfile 中主类之后不生效）：

   ```text
   -Dhypernova.textures.lazy=true
   -Dhypernova.textures.lazy.dds=true
   -Dhypernova.textures.lazy.eviction=true
   -Dhypernova.textures.lazy.eviction.sceneUnload=false
   -Dhypernova.frameProbe=true
   ```

`fr.vmparams` 本身没有 lazy flags；**必须**补上，否则
`m4_session_report.py` 会 fail-closed，报 `no valid lazy probe summary`。
报告命令改用 `Starsector-098-Base/saves/hypernova/scripts-agent.log` 与
`Starsector-098-Base/starsector-core/starsector.log`。主 mod probe 与 agent
probe 不能混成一份报告。

## 2. 启动参数（probe + 当前 LRU）

**`-D` 必须写在 `com.fs.starfarer.StarfarerLauncher` 之前。** argfile 里主类
之后的 token 会被 JVM 当作应用参数，不再是 JVM 选项；在文件末尾追加 `-D`
不会生效。不要手工往 `Miko_Lite.txt` 末尾追加。

以 `Miko_Lite_m28_treatment.txt` 为模板（`lazy=true` / `lazy.dds=true` /
`eviction=true` 已在主类之前；模板里 M2.8 实验的 `sceneUnload=true` 会被脚本
归一化为 `false`），用下面的脚本生成 `Miko_Lite_m4_probe.txt`。生成的文件是
**probe + 当前 LRU**（`sceneUnload=false`），不是 M2.8 treatment：

```bash
python -I - <<'PY'
from pathlib import Path
src = Path("Starsector-098-260mods/Miko_Lite_m28_treatment.txt")
dst = Path("Starsector-098-260mods/Miko_Lite_m4_probe.txt")
SCENE = "-Dhypernova.textures.lazy.eviction.sceneUnload=false"
FS = "-Dhypernova.frameProbe=true"
lines = src.read_text(encoding="utf-8").splitlines()
out = []
for line in lines:
    s = line.strip()
    if s == "com.fs.starfarer.StarfarerLauncher":
        if SCENE not in out:
            out.append(SCENE)
        if FS not in out:
            out.append(FS)
        out.append(line)
    elif s.startswith("-Dhypernova.textures.lazy.eviction.sceneUnload="):
        if SCENE not in out:
            out.append(SCENE)
    elif not s.startswith("-Dhypernova.frameProbe="):
        out.append(line)
dst.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
```

> `sceneUnload=true` 是 M2.8 实验开关。若要测它，单独记录为 M2.8 session，
> 不要把结果归因于当前 LRU，也不要把它算进默认 M4.1 gate。

**报告工具要求 lazy summary（fail-closed）**：A→B 会话保持生成文件的 lazy
开关（`lazy=true` / `lazy.dds=true` / `eviction=true` / `sceneUnload=false`），
不要为了只测 probe 关掉 lazy。若只想快速确认 probe 是否工作，可以临时关 lazy
只看日志，但**不要**用这种 probe-only 会话跑 `m4_session_report.py`，也不要
把它填进验收表。

启动（把下面保存为 `Starsector-098-260mods\run_m4.bat` 后双击/执行；
`%~dp0` 只在 .bat 中展开，直接粘进 PowerShell/cmd 会解析错路径）：

```bat
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0tools\LaunchMiko.ps1" "jdk-28+13" "..\Miko_Lite_m4_probe.txt"
```

不要改 `hypernova.json`，不要设置 `budgetBytes`。

## 3. 启动检查（agent 日志）

到达主菜单后、开始 A 场景前，在 `scripts-agent.log` 检查。`Display.update`
覆盖 title/campaign/combat，**主菜单就会产帧**；不要沿用旧主 mod probe 的
“菜单 0 帧是预期”的口径。

```bash
LOG=Starsector-098-260mods/saves/hypernova/scripts-agent.log
grep -c "frame probe: enabled" "$LOG"                          # >= 1
grep -c "frame probe: hook added to Display.update" "$LOG"     # >= 1
grep -c "frame probe: samples started from Display.update" "$LOG"  # >= 1
grep -c "HYPERNOVA_FRAME" "$LOG"                               # 约 600 帧后 >= 1
```

- `frame probe: enabled` 为 0：agent 没加载、`hypernova.agent.jar` 是旧包，
  或 `-D` 写在了主类之后。**停止**，否则只会得到空帧报告。
- `hook added to Display.update` 为 0：transform 没命中（旧 agent 或
  Display 类版本不符）。停止并记录日志。
- `samples started from Display.update` 为 0：hook 没执行；停止。
- `HYPERNOVA_FRAME` 从 JVM 启动后的第一帧开始累计（含 title/menu/load）。
  20 s linger 在 60 fps 下应 ≥600 帧；若菜单停留太短，可能还不够一条线，
  延长停留或进入战役后再看。
- **战斗覆盖**：`Display.update` 在战斗循环里同样每帧调用，但菜单 smoke
  不能证明战斗帧；必须由用户真正进入战斗后确认帧行继续增长。

## 4. GPU 曲线（A/B 各自独立采样）

**不要用同一个累计 CSV 生成 A/B 两份报告。** 如果从进程启动一直写到 B 结束，
B 的 `gpu.dedicated_mb.median` 会包含“启动 + 菜单 + A + B”，把 A→B 差值稀释。

A 场景开始时取游戏 PID，另开一个 shell 采样到 `build/m4/gpu-a.csv`：

```bash
mkdir -p build/m4
GPU_OUT=build/m4/gpu-a.csv   # B 场景改为 build/m4/gpu-b.csv
python -I - "$PID" > "$GPU_OUT" <<'PY'
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

A 结束立即 Ctrl-C 停止采样。进入 B 场景后，**不要重启游戏**：用**同一个游戏
进程 PID** 重新启动同一个采样器，只把 `GPU_OUT` 改为 `build/m4/gpu-b.csv`；
B 结束再 Ctrl-C。重启游戏会使 `frames`/`over200`/`longGaps` 的 B−A 累计差值
和 A→B 场景对比失效。
采样期间不要最小化窗口或长时间暂停。

## 5. A→B 会话

1. 启动后先按 §3 做启动检查；报告里的 `frame_probe.source` 必须是 `agent`
   （agent-only 验收）。若出现 `source=game`，说明主 mod 的 probe 也在跑，
   先确认环境；**不要混用两条来源**。
2. **A 场景 10 min**：同一星系内正常活动（移动、开舰队/改装、接触对话），
   不进战斗或只打一场短战斗；不要暂停。
3. A 结束立即生成报告（此时 agent summary 是 A 的最后一轮）：
   ```bash
   python -I tools/m4_session_report.py \
     --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
     --starsector-log Starsector-098-260mods/starsector-core/starsector.log \
     --gpu-csv build/m4/gpu-a.csv \
     --out build/m4/session-a.json --require-frame --text
   ```
4. **B 场景 10 min**：跳跃到另一个星系，重复类似活动。
5. B 结束再跑一次同命令（`--gpu-csv build/m4/gpu-b.csv`），
   `--out build/m4/session-b.json`。
6. 对比 A/B 的 `gpu.dedicated_mb.median`、`liveBytes`、`evictableBytes`；
   记录差值，不把单点当净 VRAM。
7. **帧计数是累计值**：计数器从 JVM 启动后的第一帧 `Display.update` 开始，
   包含 title/menu/load；`session-a.json` 覆盖启动+A，`session-b.json` 覆盖
   启动+A+B。要得到 B-only 计数，必须做差：
   `B.frames - A.frames`、`B.over200 - A.over200`、`B.longGaps - A.longGaps`。
   `HYPERNOVA_FRAME` 每 600 个有效帧才输出一条，所以 `B.frames − A.frames`
   有最多 **599 帧**的采样边界误差，不是精确的逐场景帧数。
   `maxMs` / `p99Ms` 是累计会话统计，**不能相减**；两份都报，并把 B 的
   标为累积（cumulative），不能当作 B-only P99。GPU 同理必须用 §4 的独立 CSV。
8. **报告读两份日志**：`--agent-log` 提供 `HYPERNOVA_FRAME` 与 lazy summary；
   `--starsector-log` 提供 FR session anchor 与五类纹理错误。帧行只认最后一个
   `hypernova agent premain` 之后的会话；`frame_probe.source` 由报告标明
   `agent|game|none`。

## 6. >200 ms stutter 判定

> `Display.update` 是每帧 buffer swap，title/campaign/combat 都会产帧；
> 帧行不再只在读档后出现。启动/菜单/读档阶段的帧也计入累计值。

报告里的 `frame_probe`：

- `over200`：严格大于 200 ms 的帧数；
- `maxMs`：最大帧时间；
- `p99Ms`：1 ms 直方图估算的 P99；
- `longGaps`：大于 5 s 的间隔（暂停/读档/alt-tab），不计入帧统计。

判定：

- **帧行合理性**：`frames` 应接近“会话时长 × 帧率”，但注意累计值包含
  title/menu/load；A/B 对比必须用第 5 节第 7 步的差值。
- `frames`/`over200`/`longGaps` 是探针启动以来的**累计值**；B 的读数包含 A，
  必须做差。`maxMs`/`p99Ms` 是累计统计，不能相减；B 的 P99 不是 B-only。
- `longGaps` 应接近 0；若 >0，先说明是暂停/读档/alt-tab，还是真实冻结。
  启动/菜单切换出现一次 >5 s 间隔属预期，不计入帧统计。
- `over200 > 0` 时必须结合时间点和场景说明；启动/加载阶段的长帧不是战斗
  stutter 证据，不能只报数字。
- 短于 5 s 的暂停仍会被计为一次大帧；验收期间不要暂停。

## 7. 判定表

| 项 | 通过条件 | 结果 |
|---|---|---|
| frame probe 存在 | `session.json` 中 `frame_probe.present=true`；agent-only 会话必须 `frame_probe.source=agent` | 待填 |
| probe 启动 | `scripts-agent.log` 有 `frame probe: enabled`、`hook added to Display.update`、`samples started from Display.update` | 待填 |
| 战斗帧 | 用户进入战斗后 `HYPERNOVA_FRAME` 继续增长（`Display.update` 覆盖战斗循环） | 待填 |
| 纹理错误 | 五类总数 = 0 | 待填 |
| lazy 健康 | `failed/disabled/dimMismatch/failedParked=0`、`main != none` | 待填 |
| A→B GPU dedicated | 记录 A/B 中位与差；不宣称净收益除非有重复证据 | 待填 |
| A→B live/evictable | 记录漂移；`evictable` 恒等式成立 | 待填 |
| stutter | `over200`/`maxMs`/`p99Ms` 有数；异常需场景解释 | 待填 |
| 外部帧工具（仅 stutter 兜底） | 提供外部 `over200`/`maxMs` 读数；**不能**填 `frame_probe.present=true`，也不能替代 Hypernova probe | 待填 |
| 崩溃/白块/错位 | 无 | 待填 |

任一项失败：记录日志与读数，关闭临时参数，回退到默认 off；不要修改发行默认值。
