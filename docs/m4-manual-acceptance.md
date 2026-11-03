# M4 手动验收：A→B 长会话与 >200 ms stutter

> 本文件只写步骤与判定，不预填结果。frame-time probe 默认关闭，只有
> 显式加 `-Dhypernova.frameProbe=true` 才采样。A→B 与 stutter 必须由
> 真实游戏进程 + 真实存档完成；菜单快照、单轮 smoke、`sceneEvictMsMax`
> 都不能替代。

## 1. 前置

1. **先确认主 mod（textures 模块）已启用**。`HYPERNOVA_FRAME` 由主 mod 的
   `HypernovaPlugin` 构造 `FrameTimeProbe` 后产生；只加载 agent 不会产生帧行。
   `Starsector-098-260mods/mods/enabled_mods.json` 默认**不启用**
   `hypernova_infinite_engine`，先备份再临时追加：

   ```bash
   cp Starsector-098-260mods/mods/enabled_mods.json \
      Starsector-098-260mods/mods/enabled_mods.json.bak-m4
   python -I - <<'PY'
   import json
   from pathlib import Path
   p = Path("Starsector-098-260mods/mods/enabled_mods.json")
   data = json.loads(p.read_text(encoding="utf-8"))
   ids = data["enabledMods"]
   if "hypernova_infinite_engine" not in ids:
       ids.append("hypernova_infinite_engine")
   p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
   PY
   ```

   验收结束后恢复原配置：

   ```bash
   cp Starsector-098-260mods/mods/enabled_mods.json.bak-m4 \
      Starsector-098-260mods/mods/enabled_mods.json
   ```

   > **口径**：启用主 mod 会同时激活 `HypernovaPlugin` 的 manifest/prefetch
   > 路径，所以本验收测的是“**textures 模块 + agent**”，不是 agent-only。
   > 若必须保留 agent-only 数据，probe 无法运行；此时只能用外部帧时间工具
   > （如 RTSS / MSI Afterburner）观察 stutter，**不能**填
   > `frame_probe.present=true`，也不能替代 Hypernova probe。
   >
   > **替代环境（高级）**：`Starsector-098-Base` 已启用该模块，但它使用
   > `starsector-core/fr.vmparams` 作为启动参数文件。必须：
   > 1. `bash tools/java/install-manifest.sh Starsector-098-Base` 刷新主 jar；
   > 2. `python tools/install_agent.py --game Starsector-098-Base --env base`
   >    刷新 agent（`--env base` 对应 `starsector-core/fr.vmparams`）；
   > 3. 用 §2 的脚本把 `fr.vmparams` 派生成
   >    `Starsector-098-Base/starsector-core/fr_m4_probe.vmparams`
   >    （只改 src/dst；保持 `-D` 在主类之前；需要 lazy/DDS 时也在主类前加）；
   > 4. 报告命令改用 Base 路径：
   >    `Starsector-098-Base/saves/hypernova/scripts-agent.log` 与
   >    `Starsector-098-Base/starsector-core/starsector.log`。
   > 缺点：Base 的 mod 数远少于 260mods。

2. 构建并安装（主 jar + agent jar 都要刷新，否则 probe 仍是旧 class）：
   `bash tools/java/build-mod.sh` →
   `bash tools/java/install-manifest.sh Starsector-098-260mods` →
   `python tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite`
3. 确认 `Starsector-098-260mods/starsector-core/graphics/hypernova/blank.png` 非空。
4. 每组开始前清空或改名：
   - `Starsector-098-260mods/saves/hypernova/scripts-agent.log`
   - `Starsector-098-260mods/starsector-core/starsector.log`
5. 使用干净存档 / 小舰队；不要用 260mods 生涯大地图、Star Wars 新开局、
   超大舰队或 Exotica 改装 UI（这些是已知 mod 环境问题，不归因 Hypernova）。
6. 默认开关不动；本验收只用启动参数临时开启。

## 2. 启动参数（probe + 当前 LRU）

**`-D` 必须写在 `com.fs.starfarer.StarfarerLauncher` 之前。** argfile 里主类
之后的 token 会被 JVM 当作应用参数，不再是 JVM 选项；在文件末尾追加 `-D`
不会生效。不要手工往 `Miko_Lite.txt` 末尾追加。

以 `Miko_Lite_m28_treatment.txt` 为模板（它的 lazy flags 已在主类之前），
用下面的脚本生成 `Miko_Lite_m4_probe.txt`：

```bash
python -I - <<'PY'
from pathlib import Path
src = Path("Starsector-098-260mods/Miko_Lite_m28_treatment.txt")
dst = Path("Starsector-098-260mods/Miko_Lite_m4_probe.txt")
lines = src.read_text(encoding="utf-8").splitlines()
out = []
for line in lines:
    s = line.strip()
    if s.startswith("-Dhypernova.textures.lazy.eviction.sceneUnload="):
        out.append("-Dhypernova.textures.lazy.eviction.sceneUnload=false")
    elif s == "com.fs.starfarer.StarfarerLauncher":
        if "-Dhypernova.frameProbe=true" not in out:
            out.append("-Dhypernova.frameProbe=true")
        out.append(line)
    else:
        out.append(line)
dst.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
```

脚本保证 `-Dhypernova.frameProbe=true` 在主类之前，并把
`textures.lazy.eviction.sceneUnload` 设为 `false`；template 里已有
`lazy=true` / `dds=true` / `eviction=true`。

启动（把下面保存为 `Starsector-098-260mods\run_m4.bat` 后双击/执行；
`%~dp0` 只在 .bat 中展开，直接粘进 PowerShell/cmd 会解析错路径。
PowerShell 内联可用 `$PSScriptRoot`）：

```bat
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0tools\LaunchMiko.ps1" "jdk-28+13" "..\Miko_Lite_m4_probe.txt"
```

不要改 `hypernova.json`，不要设置 `budgetBytes`。

## 3. GPU 曲线（A/B 各自独立采样）

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

A 结束立即 Ctrl-C 停止采样。进入 B 场景后，用新的游戏 PID 重新启动同一个
采样器，并把 `GPU_OUT` 改为 `build/m4/gpu-b.csv`；B 结束再 Ctrl-C。
采样期间不要最小化窗口或长时间暂停。

## 4. A→B 会话

1. **加载存档后先做启动检查**：在 `starsector.log` 里搜索
   `Hypernova frame probe enabled`：
   ```bash
   grep -c "Hypernova frame probe enabled" \
     Starsector-098-260mods/starsector-core/starsector.log
   ```
   输出必须 ≥1。若为 0，**停止**：主 mod 没加载或主 jar 是旧的，继续采样
   只会得到空帧报告。
   `HYPERNOVA_FRAME` 行只在**读档后**、主线程 `advance` 开始后才出现；
   主菜单没有 `Global.getSector()`，transient script 不挂载，菜单里 0 帧行
   是预期，不能据此判定 probe 失败。
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
7. **帧计数是累计值**：`session-a.json` 覆盖启动+A，`session-b.json` 覆盖
   启动+A+B。要得到 B-only 计数，必须做差：
   `B.frames - A.frames`、`B.over200 - A.over200`、`B.longGaps - A.longGaps`。
   `maxMs` / `p99Ms` 是累计会话统计，**不能相减**；两份都报，并把 B 的
   标为 cumulative，不能当作 B-only P99。GPU 同理必须用 §3 的独立 CSV。

## 5. >200 ms stutter 判定

> `HYPERNOVA_FRAME` 行只在加载存档后出现；主菜单里没有帧行是预期
> （菜单没有 `Global.getSector()`，transient script 不挂载）。

报告里的 `frame_probe`：

- `over200`：严格大于 200 ms 的帧数；
- `maxMs`：最大帧时间；
- `p99Ms`：1 ms 直方图估算的 P99；
- `longGaps`：大于 5 s 的间隔（暂停/读档/alt-tab），不计入帧统计。

判定：

- **帧行合理性**：`frames` 应接近“会话时长 × 帧率”（例如 10 min × 60 fps ≈ 36,000）。
  如果明显只有一半，先怀疑**相邻真实帧拿到相同的 `amount`**：`amount` 不是唯一
  帧身份，按 amount 去重会误丢帧。反过来，两个入口收到**不同** amount 会导致
  重复计数，而不是丢帧。这是首次实机必须确认的假设。
- `frames`/`over200`/`longGaps` 是探针启动以来的**累计值**；B 的读数包含 A，
  必须按 §4 第 7 步做差。`maxMs`/`p99Ms` 是累计统计，不能相减；B 的 P99
  不是 B-only。
- `longGaps` 应接近 0；若 >0，先说明是暂停/读档/alt-tab，还是真实冻结。
- `over200 > 0` 时必须结合时间点和场景说明；不能只报数字。
- 短于 5 s 的暂停仍会被计为一次大帧；验收期间不要暂停。

## 6. 判定表

| 项 | 通过条件 | 结果 |
|---|---|---|
| frame probe 存在 | `session.json` 中 `frame_probe.present=true` | 待填 |
| 纹理错误 | 五类总数 = 0 | 待填 |
| lazy 健康 | `failed/disabled/dimMismatch/failedParked=0`、`main != none` | 待填 |
| A→B GPU dedicated | 记录 A/B 中位与差；不宣称净收益除非有重复证据 | 待填 |
| A→B live/evictable | 记录漂移；`evictable` 恒等式成立 | 待填 |
| stutter | `over200`/`maxMs`/`p99Ms` 有数；异常需场景解释 | 待填 |
| 外部帧工具（仅 stutter 兜底） | 提供外部 `over200`/`maxMs` 读数；**不能**填 `frame_probe.present=true`，也不能替代 Hypernova probe | 待填 |
| 崩溃/白块/错位 | 无 | 待填 |

任一项失败：记录日志与读数，关闭临时参数，回退到默认 off；不要修改发行默认值。
