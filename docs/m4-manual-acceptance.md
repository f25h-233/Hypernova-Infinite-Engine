# M4 手动验收：A→B 长会话与 >200 ms stutter

> 本文件只写步骤与判定，不预填结果。frame-time probe 默认关闭，只有
> 显式加 `-Dhypernova.frameProbe=true` 才采样。A→B 与 stutter 必须由
> 真实游戏进程 + 真实存档完成；菜单快照、单轮 smoke、`sceneEvictMsMax`
> 都不能替代。

## 1. 前置

1. 构建并安装（主 jar + agent jar 都要刷新，否则 probe 仍是旧 class）：
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

## 2. 启动参数（probe + 当前 LRU）

复制 `Starsector-098-260mods/Miko_Lite.txt` 为
`Starsector-098-260mods/Miko_Lite_m4_probe.txt`，追加：

```text
-Dhypernova.frameProbe=true
-Dhypernova.textures.lazy=true
-Dhypernova.textures.lazy.dds=true
-Dhypernova.textures.lazy.eviction=true
-Dhypernova.textures.lazy.eviction.sceneUnload=false
```

启动：

```bat
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0tools\LaunchMiko.ps1" "jdk-28+13" "..\Miko_Lite_m4_probe.txt"
```

不要改 `hypernova.json`，不要设置 `budgetBytes`。

## 3. GPU 曲线

进程启动后取游戏 PID，另开一个 shell 采样到 `build/m4/gpu-ab.csv`：

```bash
mkdir -p build/m4
python -I - "$PID" > build/m4/gpu-ab.csv <<'PY'
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

Ctrl-C 结束采样。采样期间不要最小化窗口或长时间暂停。

## 4. A→B 会话

1. **A 场景 10 min**：同一星系内正常活动（移动、开舰队/改装、接触对话），
   不进战斗或只打一场短战斗；不要暂停。
2. A 结束立即生成报告（此时 agent summary 是 A 的最后一轮）：
   ```bash
   python -I tools/m4_session_report.py \
     --agent-log Starsector-098-260mods/saves/hypernova/scripts-agent.log \
     --starsector-log Starsector-098-260mods/starsector-core/starsector.log \
     --gpu-csv build/m4/gpu-ab.csv \
     --out build/m4/session-a.json --require-frame --text
   ```
3. **B 场景 10 min**：跳跃到另一个星系，重复类似活动。
4. B 结束再跑一次同命令，`--out build/m4/session-b.json`。
5. 对比 A/B 的 `gpu.dedicated_mb.median`、`liveBytes`、`evictableBytes`；
   记录差值，不把单点当净 VRAM。

## 5. >200 ms stutter 判定

报告里的 `frame_probe`：

- `over200`：严格大于 200 ms 的帧数；
- `maxMs`：最大帧时间；
- `p99Ms`：1 ms 直方图估算的 P99；
- `longGaps`：大于 5 s 的间隔（暂停/读档/alt-tab），不计入帧统计。

判定：

- **帧行合理性**：`frames` 应接近“会话时长 × 帧率”（例如 10 min × 60 fps ≈ 36,000）。
  如果明显只有一半，说明两个入口收到的 `amount` 不一致、探针按 amount 去重时误丢帧；
  这是首次实机必须确认的假设（`FrameTimeProbe` 用 `amount` 作为引擎帧身份）。
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
| 崩溃/白块/错位 | 无 | 待填 |

任一项失败：记录日志与读数，关闭临时参数，回退到默认 off；不要修改发行默认值。
