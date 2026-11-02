# M2.7 手动验收清单（战斗/读档/分辨率/长会话）

> 2026-11-02：已执行一次用户任务战斗（Valkyrie「为天堂之门而战」），lazy+DDS+eviction
> 默认预算下正常、0 五类纹理错误，但 `evictPasses=0`（无淘汰压力）；其余项目未完成。
> 本文件是验收步骤 + 实测记录，不是完整 PASS。只有在全部通过后才可讨论 default-on；
> 任何一项失败先记录再修。自动化菜单证据见 `docs/m27-results.md`。

## 前置

1. 两侧安装最新 agent（`tools/install_agent.py`），并确认
   `mods/hypernova_infinite_engine/jars/hypernova.agent.jar` 与 `build/agent/hypernova.agent.jar`
   一致；`starsector-core/graphics/hypernova/blank.png` 存在且非空（70 B）。
2. 开启 lazy + DDS + eviction（默认预算 256 MB）：

   ```text
   -Dhypernova.textures.lazy=true
   -Dhypernova.textures.lazy.dds=true
   -Dhypernova.textures.lazy.eviction=true
   ```

   默认：`budget_mb=256`、`grace_ms=10000`、`scene_delay_ms=2000`、`max_per_pass=64`。
   `-Dhypernova.textures.lazy.eviction.budgetBytes=<bytes>` 是内部诊断旋钮，
   **不要**写进用户配置或发行说明。
3. 每次会话结束后记录：
   - `saves/hypernova/scripts-agent.log` 的**最后一条** `lazy probe: summary`；
   - `starsector-core/starsector.log` 的最后 session 切片；
   - 逐进程 GPU dedicated/shared（任务管理器或 `nvidia-smi` 旁证）。

## 2026-11-02 实测记录（用户）

- **任务战斗**：Valkyrie「为天堂之门而战」；lazy+DDS+eviction on、默认 256 MB。
  用户主观“一切正常”；`materialized=724`、`ddsHit=655`、`ddsFallback=3`（META）、
  `failed=disabled=dimMismatch=failedParked=0`、`evictPasses=0`、`evicted=0`；
  `starsector.log` 五类纹理错误 0。**没有触发淘汰**，所以不是淘汰路径的 PASS。
- **与 Hypernova 无关的 260mods 问题**（no-Hypernova 对照复现/堆栈定位）：
  Star Wars 开局 + 大量顶级舰 → 新建存档 `NameAssigner` NPE；超大舰队旧档严重卡顿；
  “舰队改装” → Exotica `RefitButtonAdder.advance` 的 `UIComponentAPI` 空 cast。
  不要把这些记成 Hypernova 失败；用干净存档/小舰队/禁用 Exotica refit 按钮再测。
- **仍未完成**：campaign 战斗（带 `evictPasses>0`）、读档/存档、分辨率/全屏/alt-tab、
  A→B 长会话、逐帧/P99 stutter。

## 可选诊断淘汰（战斗步骤前）

可选诊断淘汰：启动参数加内部诊断 `-Dhypernova.textures.lazy.eviction.budgetBytes=262144`
（**不是用户配置**），确认 `budgetBytes=262144`、`evictPasses>0`、`evicted>0`、
`failedParked=0`。默认 256 MB 下 `evictPasses=0` 是预期；只跑默认预算不能判定淘汰路径已验证。

## 1. 战斗（5–10 分钟）

- 进入一场 5–10 分钟战斗；观察并记录：
  - 0 `Failed to load texture`；0 `VerifyError` / `ClassFormatError` / `AsyncException` /
    `isStateCorrupted`。
  - `evictPasses`、`evicted`、`rematerialized`、`evictPassMsMax`、`failedParked`、
    `ddsFallback` 及 `ddsFb*` 原因分解。
  - 主观记录 >200 ms 卡顿次数/场景（跃迁、开火、导弹、爆炸、打开战术地图）。
- 读法：
  - `evictPass` 日志 `live=` 是**可淘汰字节**，不是总 `liveBytes`。
  - `oldIdDeleted` 包含成功的淘汰删除；`evicted` 是代理复位成功条数，不是“VRAM 已释放量”。
  - `emptyEvictPasses` 不统计 `live <= budget` 的早退；但删除失败的 pass（`evictOne` 已复位
    代理/扣 `LIVE_BYTES`，`GlBridge.deleteTexture` 失败返回 false）也会计为空 pass，尽管已有
    代理被淘汰。
  - `evictPassMsMax` 只是主线程 pass 耗时，不是逐帧 P99；>200 ms 以主观/帧时间为准。
  - `ddsFallback` 的 sum(`ddsFb*`) 应在最后稳定 summary 相等（瞬时快照可差 1）；
    `BRIDGE` 自 M2.7 起计入总数，和 M2.6 比较时必须 `ddsDisabled=0`。

## 2. 读档 / 存档

- 读档两次、存档一次；确认无白块、错位、崩溃、贴图串位。
- 记录 `dimMismatch`、`reregistered`、`failed`、`failedParked`、`ddsDimMismatch`。
- 若 lazy 因 `dimMismatch` 自动禁用（fail-open），记录为**降级**，不是崩溃；保留日志。

## 3. 分辨率 / 全屏 / alt-tab

- 1707×1067 → 2560×1440 → 返回 1707×1067；再试全屏/窗口化与 alt-tab。
- 确认占位纹理不残留、不闪白、不崩溃（W-2：GL context 重建可能作废占位 id；
  当前没有检测/重解析逻辑，预期表现是不可见/未定义，不是恢复）。
- 若 lazy 因 `dimMismatch` 自动禁用，记录为 fail-open，不是崩溃。
- 记录 `dimMismatch`、`placeholder`、`reregistered`、`evictPasses`。

## 4. A→B 长会话（各 10 分钟）

- A 场景 10 分钟 → B 场景 10 分钟；尽量覆盖不同星系/战斗/市场/百科。
- 记录逐进程 GPU dedicated 曲线（菜单 / 战斗 / 退出）与
  `liveBytes` / `evictableBytes` / `startupBytes` / `foreignBytes` 漂移。
- 目标：B 场景不应持续逼近 baseline；若 `evictableBytes` 持续增长且 `evictPasses` 不触发，
  记录预算/场景延迟/战斗门禁状态。
- 本轮自动化只有菜单时刻快照，**不能替代**本项。

## 5. 回滚

- 配置 `textures.lazy.enabled=false`（或单独 `textures.lazy.eviction.enabled=false`），
  或加 `-Dhypernova.textures.lazy=false`，或删除启动文件中的
  `-javaagent:.../hypernova.agent.jar` 行。
- 确认行为回到 M2（不跳过、不代理、不注册 lazy）；skip v1/v2 可保留。

## 6. 判定

- 全部通过才可讨论 default-on；任何一项失败先记录再修，不得把菜单门禁通过当成
  战斗/长会话通过。
- 记录模板：日期/宿主/分辨率/场景/会话时长/最后 summary/错误计数/主观卡顿/GPU 曲线。
- W-10 残余：`blank.png` 缺失时失败代理仍可能绑定 id 0；安装器已断言两侧 `blank.png`
  非空，运行期仍需保持该文件存在。
