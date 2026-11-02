# M2.8 结果：更激进场景淘汰（experimental / 默认 off）

- **日期**：2026-11-02
- **状态**：**代码侧完成；Task 4 实机 gate 由用户跳过**。默认 off，实验性；
  **不宣称能降低显存占用**，也没有足够证据否定它。对外只描述为“实验性功能”。
- **宿主**：Windows 11 中国区；`Starsector-098-260mods`（260 mods，Miko Lite / JDK 28）。
- **范围**：`e7baa9c..20baded` 的 7 个提交（实现 + 两轮 review fix + gate 修复）。

## 1. 结论

1. **实现完成**：`CAMPAIGN → COMBAT` 时对 `owned=true`、非 `startup`、非
   basic/backgrounds 的已物化代理执行有界强制 LRU（8 chunk × 默认 64，
   100 ms 间隔，10 s 窗口），忽略 256 MB 预算；战斗中不跑普通 `evictPass`。
2. **默认 off**：`textures.lazy.enabled=false`、
   `textures.lazy.eviction.enabled=false`、
   `textures.lazy.eviction.scene_unload.enabled=false`。发行配置未改。
3. **Task 4 实机 gate 未执行**：用户报告 260mods 生涯大地图移动“绝对的灾难，
   太卡了”，决定跳过控制/处理两组战斗验收。该卡顿来自用户会话环境，
   **没有对照证据归因于 Hypernova**；不能写成 M2.8 的失败或收益。
4. **不宣称显存收益**：没有有效的 `sceneEvictions`、战斗 GPU dedicated 或
   视觉验收数据。唯一一次探索性 control 启动器会话记录了
   `build/m28/gpu-control.csv`（202 行），但它不是配对的 control/treatment
   gate，**不作为证据**。
5. **保留为实验性功能**：代码、gate 工具和手动验收清单保留；将来若环境允许，
   可按 `docs/m28-manual-acceptance.md` 复跑 Task 4。

## 2. 代码与测试

| Task | Commit | 内容 | 测试 |
|---|---|---|---|
| 1 | `09bf870` | `scene_unload` 配置键；`graphics/backgrounds/` 加入 `isBasicPath` | config 7/7；LazyEviction 24/24 |
| 2 | `33e6eac` | scene 触发/选择/调度/pass/summary 6 键 | LazyEviction 32/32；full 192/191/1 |
| 2 fix1 | `4675257` | 接线测试、force 采样、M-1/M-2/M-4/M-5 | LazyEviction 36/36；full 196/195/1 |
| 3 | `98e7249` | `tools/m28_scene_gate.py` + 手动验收 | pytest 306 |
| 3 fix | `d05b199` | summary 会话作用域 + fail-closed | gate 31；pytest 330 |
| 2 fix2 | `11bf44a` | campaign 重入 force（真实 hook 形状） | LazyEviction 37/37；full 197/196/1 |
| 3 fix3 | `20baded` | lazy 健康门 + `--require-control` | gate 51；pytest 350 |

最终验证（2026-11-02）：

- agent：**197 found / 196 pass / 1 known Windows symlink abort / 0 fail**
- tools：**350 passed**
- `bash tools/java/build-mod.sh`：OK；`install_agent.py --game
  Starsector-098-260mods --env 260mods-lite`：installed，无 vmparams 变更；
  安装 jar 与 `build/agent/hypernova.agent.jar` SHA256 一致
  （`87e7eff27740c62b44f8e6eb93533d7612e5a34536543a6f758c1843b75d322a`）。

## 3. 实现边界（供未来复跑时解释）

- 只淘汰 `owned=true`、`ready`、`glId>0`、`bytes>0` 的代理；`startup`、
  `owned=false`、UI/fonts/intro/backgrounds、未 ready 永不淘汰。
- 触发只认 `CAMPAIGN → COMBAT`，只用 `Global.getCurrentState()`；不按路径/
  类名猜状态。`CombatState.traverse` 不调用 `BaseGameState.traverse`，
  战斗进入依赖 `lookup`/`onProxyUse` 的 250 ms 主线程轮询；campaign 重入由
  `captureMainThread` force 采样。
- 有效 grace = arm 后经过时间 + `scene_unload.grace_ms`（默认 0）；战斗期间
  被 touch 的纹理不会被本场 scene pass 淘汰。
- 执行复用 `evictOne`：代理复位到 `blank.png` 占位，旧 GL id 走
  `glDeleteTextures`；占位不可用时 fail-open，不把 lazy 整体禁用。
- 指标：`scenePasses` 是 chunk 数；`sceneEvictions` 是复位且 GL 删除成功；
  `evicted` 含删除失败；`sceneEvictMsMax` 是 chunk 墙钟，不是帧 P99；
  `scenePending` 是剩余 chunk 数。

## 4. 为什么没有实机结论

- 260mods 生涯大地图在用户会话中移动严重卡顿；控制/处理两场同存档、小舰队
  战斗无法在可接受时间内完成。用户决定跳过 Task 4。
- 探索性 control 启动器会话（`build/m28/gpu-control.csv`）不是配对 A/B；
  没有 treatment 对照、没有确定的战斗窗口、没有视觉验收，因此不用于
  “降低/不降低显存”的结论。
- 没有 `sceneEvictions>0` 的实机证据，也没有 `failedParked`/五类纹理错误/
  白块/错位/GPU dedicated 的战斗验收证据。M2.8 只能标为“代码完成，
  实机未验证”。

## 5. 默认 / 回滚

- 默认：`textures.lazy.enabled=false`、`textures.lazy.eviction.enabled=false`、
  `textures.lazy.eviction.scene_unload.enabled=false`。
- 回退（任一）：配置 `textures.lazy.eviction.scene_unload.enabled=false`；
  `-Dhypernova.textures.lazy.eviction.sceneUnload=false`；
  `textures.lazy.eviction.enabled=false`；`textures.lazy.enabled=false`；
  删除 `-javaagent:.../hypernova.agent.jar` 行。
- 配置文件：`mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json`。
- 发行默认值未改；M2.8 不改变 `hypernova.json` / `enabled_mods.json`。

## 6. 限制与残余

- **无全局 Sprite 注册表/refcount**：无法证明“无人引用”；scene pass 只对
  owned 代理安全。engine-owned/mod-owned 纹理不在范围内。
- **触发依赖主线程纹理活动**：战斗进入靠 250 ms 轮询；如果战斗渲染完全不
  触达 lazy 代理，`scenePasses=0`。复跑时先搜 `lazy: scene unload armed`。
- **grace 从 arm 起算**：战斗开始到 arm 之间被 touch 的纹理不受本场保护；
  首次使用时可能同步重物化。
- **W-2/W-3 残余**：GL context 重建占位、第三方 id 缓存仍 open；不做
  refcount/REQ-R1-10。
- **`sceneEvictions` 口径**：复位且 GL 删除成功；删除失败会计入 `evicted`
  但不计入 `sceneEvictions`，可能留下 VRAM 泄漏。
- **`sceneEvictMsMax` 不是帧 P99**：>200 ms 卡顿仍需 M4 的 frame-time probe。
- **260mods 大地图卡顿**：用户报告；没有 no-Hypernova 对照切片，不作为
  Hypernova 结论，也不影响默认 off/发行决策。

## 7. 下一步

1. **M4**（验收 & 发布硬化）：frame-time probe（默认 off）、A→B/stutter、
   A/B/release 工具修复；M2.8 默认 off 也要验。
2. **M2.8 后的系统级 spike**（用户已同意）：只测量、不改行为——记录
   owned/foreign/startup 字节与数量、路径/星系可归属性、星系切换次数、
   重物化成本；回答“星系级 owned 淘汰值不值得做”。
3. **M6 → M5**：按 roadmap；M2.8 不阻塞后续。
