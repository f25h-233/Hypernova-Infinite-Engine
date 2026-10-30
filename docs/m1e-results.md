# M-1e 发布前验证结果

> 日期：2026-10-31
> 环境：Starsector 0.98a + 260mods、Miko Lite（JDK 28）、`Miko_Lite.txt`（FR 0.9.5）
> 结论：no-FR 臂 / OS 缓存 / Java 17 三门禁的判定见 §1。

## 1. 结论

| 门禁 | 结果 | 证据 |
|---|---|---|
| no-FR 臂 | 通过 | §2；`build/m1e-nofr-on-measure.json` |
| OS 缓存测量 | 观察（`cache_control=none`） | §3；`build/m1e-rounds-warm.json` |
| Java 17 审计 | 通过 | §4；`build/m1e-java-audit.json` |

- 菜单时间：3 轮 warm 中位数 **70.1 s**（**68.6–83.1**），其中 2 轮低于历史 76.9–98.2 s 的下沿；**不宣称收益**——OS 缓存未受控（`cache_control=none`，§3.3），这只是观察，不是净收益结论。
- no-FR 法线：`normal_before_menu` **0**（臂 B 基线 **30,378**），下降 **100%**；`textures patched` = 是；`FR missing` = 是；`Failed to load texture` = **0**。
- JRE17：agent **64 found / 63 successful / 1 aborted / 0 failed**；mod **95/95**；runtime 首行 = `openjdk version "17.0.10" 2024-01-16 LTS`。
- **收益的宿主依赖**：no-FR 臂证明 **textures 补丁本身不依赖 FR**（真无 FR 下仍 `patched`、法线 30,378→0、无失败纹理），但**整体启动速度依赖 FR**：同一 no-FR 环境到主菜单 1,239.5–1,305.8 s，而 FR-on 本轮 68.6–83.1 s。no-FR 下主线程仍在做 vanilla 文件枚举/spec 加载（Task 1 jstack），以及 vanilla `com.fs.graphics.L` 的 `LinkedList.contains` 轮询（按纹理累计 O(n²)）与每纹理 `Thread.sleep(10)`（`.research/decomp/src/com/fs/graphics/L.java:30-77`）；这些主线程成本在 FR 缺席时不再被并行化。

## 2. no-FR 臂

### 2.1 环境构造

- 源档：`Starsector-098-260mods/Miko_Lite.txt`（**未修改**；sha256=`0bebe88e730aadcb421209b74bbde47024adc9deaa7cdf6ab55901fa5b45b3e6`）。
- 派生档：`Starsector-098-260mods/Miko_Lite_nofr.txt`（sha256=`809ce82538bb1871954661a33bac24ef3f1c8d5bfe07d06d8b5ee345c693d80c`），由 `tools/m1e_profile.py` 生成：
  - 移除 `-javaagent:fr.agent.jar` 1 行；
  - 从 `-classpath` 移除 `fr.jar` 1 个 token；
  - 保留 `-javaagent:../mods/hypernova_infinite_engine/jars/hypernova.agent.jar`；
  - 主类仍为最后一行；CRLF 保留。
- 真无 FR 的定义：classpath 无 `fr.jar` **且** agent 未加载 FR javaagent；`HypernovaAgent.frPresent()` 用 `Class.forName("com.genir.renderer.Version")` 正向验证。只删 `-javaagent` 不算。
- `install_agent.py` 只刷新了 `Miko_Lite.txt.bak-hypernova` 备份，启动档本身内容未变（sha256 如上）。

### 2.2 证据

| 检查 | 命令/来源 | 实测 |
|---|---|---|
| 日志无 FR | `grep -ac "Fast Rendering: v" build/m1e-nofr-on.log` | **0**（要求 0） |
| agent 记 FR missing | `build/m1e-nofr-on.json` → `agent.fr_missing` | `2026-10-30T18:48:51.592664800Z INFO FR missing; scripts cache disabled` |
| textures 仍 patched | `build/m1e-nofr-on.json` → `agent.textures_patched` | `2026-10-30T18:49:08.615907900Z INFO textures: patched org/dark/shaders/util/TextureData (shaderLib 1.12.1 lazy normal cache)` |
| 无失败纹理 | `m1b_measure.failed_texture_lines` | **0**（要求 0） |
| 到主菜单 | `build/m1e-nofr-on.json` → `menu_s` | **1239.5 s** |
| VOpt 回退 | `grep -m1 -a "FR not enabled, handling DDS files manually" build/m1e-nofr-on.log` | `1181121 [main] INFO  DeCell.VOpt.VOpt  - FR not enabled, handling DDS files manually`（出现；不失败） |

补充说明：

- **agent 日志是跨会话追加的**：`build/m1e-nofr-on-agent.log` / `build/m1e-nofr-off-agent.log` 都含更早会话的 `FR missing` / `textures: patched` 行，`grep -m1` 会命中旧行。上表取 smoke JSON 记录的**最后一次 premain 会话**行；arm B 对应行为 `2026-10-30T18:20:20.151866500Z INFO FR missing; scripts cache disabled`。
- **arm B 的测量日志有轮转**：arm B 运行期间 `starsector.log` 发生轮转，测量日志由 `starsector.log.3` 头部 + `starsector.log` 尾部按时间顺序拼接（`session_source=rollover`）。该拼接片段里含 **7 条**更早 FR-on 会话的 `Fast Rendering: v0.9.5` 行；`m1b_measure._select_session` 只取最后一个会话，所选会话 `fr_anchor=0`。因此 arm B 的 FR 证据来自“所选末段会话”，不是整份拼接文件。arm A 运行期间未轮转，只复制 current `starsector.log`，整份文件的 `Fast Rendering: v` 计数为 0。
- `.log.1` / `.log.2` 为 10-30 旧会话，未参与测量。
- `--normal-metric cleaned` 是必需的：vanilla no-FR 不写 `Loading image [cache/*_normal.png]`（两臂 `loading_normal_before_menu/after_menu` 均为 0），等价信号是 `Cleaned buffer for texture cache/*_normal.png`。正则 `cache/.*?_normal\.png` 计入文件名含空格的 10 行，才得到精确的 30,378（旧正则 `[^\s]*` 会得到 30,368）。

### 2.3 A/B 法线

| 臂 | `textures.enabled` | `normal_before_menu` | `patched` | `fr_present` | `failed_texture_lines` | `menu_s` |
|---|---|---:|---|---|---:|---:|
| B（基线） | false | 30,378 | false | false | 0 | 1305.8 |
| A（门禁） | true | 0 | true | false | 0 | 1239.5 |

- 下降 = 1 − A/B = **100%**（门禁 ≥80%）。
- 绝对行数 A = **0**（门禁 ≤50）。
- 两臂 `fr_missing_disabled=true`；arm B `gate_ok=false`（textures off，`patched=false`，预期），arm A `gate_ok=true`。
- 会话级复核（`m1b_measure._select_session`，对已落盘日志离线复算）：
  - arm B：`session_source=rollover`，`fr_anchor=0`、`menu_anchor=1`、`loading_image=0`、`cleaned_normal=30,385`、`failed=0`、VOpt 回退 1；`first_ts=554 ms`、`last_ts=1,329,357 ms`。主菜单前的 cleaned 法线为 30,378（主菜单后剩余 7）。
  - arm A：`session_source=rollover`，`fr_anchor=0`、`menu_anchor=1`、`loading_image=0`、`cleaned_normal=0`、`failed=0`、VOpt 回退 1；`first_ts=634 ms`、`last_ts=1,263,238 ms`。
- `menu_s` 有两套：smoke JSON 的 1305.8 / 1239.5（smoke 主菜单锚点），`m1b_measure` 的 1305.3 / 1239.4（日志 `Playing music` 锚点）；差异为锚点口径，不影响门禁。

### 2.4 门禁判定

| 项 | 要求 | 实测 | 结果 |
|---|---|---|---|
| 正常到主菜单 | 是 | 是（1239.5 s） | 通过 |
| 日志无 `Fast Rendering: v0.9.5` | 0 | 0（arm A 整份；arm B 所选会话 0） | 通过 |
| agent `FR missing; scripts cache disabled` | 出现且不崩 | 出现 | 通过 |
| `textures: patched` | 出现 | 出现 | 通过 |
| `normal_before_menu` 相对 B 组 | ≥80% 下降 | 100% | 通过 |
| `normal_before_menu` 绝对 | ≤50 | 0 | 通过 |
| `Failed to load texture` | 0 | 0 | 通过 |
| VOpt 回退 | 出现 | `FR not enabled, handling DDS files manually` | 通过 |

### 2.5 为什么“补丁不依赖 FR”而“启动速度依赖 FR”

- 补丁注入点是 `org.dark.shaders.util.TextureData` 的 normal-cache 路径，本身不引用 `com.genir.renderer`；真 no-FR 下仍 `textures: patched`、`cache probe ready, files=31627`，主菜单前 cleaned 法线从 30,378 降到 0，且无失败纹理。因此 **textures 模块的确定性收益是宿主无关的**。
- 但同一 no-FR 环境的整体启动是 1,239.5–1,305.8 s，说明 FR 提供的并行/跳过路径才是“短启动”的主要来源。Task 1 在 no-FR 会话约 195 s 时 jstack 到主线程 CPU 约 168 s 花在 `SpecStore → LoadingUtils → com.fs.util.C.new → File.exists/FileInputStream.read`（vanilla 文件枚举/spec 加载）；900 s 会话已有 33,796 条 `Cleaned buffer`、0 条 `Loading image`。此外 vanilla `com.fs.graphics.L` 用 `Collections.synchronizedList(new LinkedList())` + `contains` 轮询（按纹理累计 O(n²)）+ 每纹理 `Thread.sleep(10)` 等待加载，缺少 FR 的并行/异步后这些成本全部留在主线程。故：**textures 补丁 host-independent，整体启动 speed FR-dependent**。

## 3. OS 缓存测量

### 3.1 口径

- warm：连续 3 轮，不 purge；每轮记录 `ReadTransferCount`（进程累计从磁盘读的字节，Windows `GetProcessIoCounters`）。
- post-purge（若可用）：`tools/clear_standby.ps1` 清 standby list 后跑 3 轮；`cache_control=standby-purged`。
- 本机默认非管理员；`clear_standby.ps1` 返回 `NOT_ELEVATED`、exit 3，因此 **不跑** post-purge 臂，结论降级为“观察”。`build/m1e-rounds-cold.json` 不存在（未生成）。
- 3 轮 `stop` 均为 `forced`：`smoke_run` 对 Windows `java.exe` 无窗口消息循环，先非强制再升级 `/F`；shutdown hook 不执行，测量使用 8 s linger 稳定窗口。

### 3.2 warm 3 轮

`profile=miko-lite`（FR on，scripts cache 热）、`cache_control=none`、`purge_log=[]`、`jvm_args=[]`。

| 轮 | `menu_s` | `read_bytes_menu` | key `took` (ms) | `stop` |
|---:|---:|---:|---:|---|
| 1 | 83.1 | 802,244,323 | 706 | forced |
| 2 | 70.1 | 802,494,962 | 457 | forced |
| 3 | 68.6 | 802,021,751 | 545 | forced |
| 中位数 | **70.1** | **802,244,323** | **545** | — |
| min–max | 68.6–83.1 | 802,021,751–802,494,962 | 457–706 | — |

- `cache_control` = `none`。
- 每轮 `read_bytes_exit`：815,565,002 / 815,323,069 / 815,507,227 B。
- 每轮 `wall_s`：108.0 / 95.0 / 93.5 s。
- `read_bytes_menu` 为 null 的情况未发生：I/O 探针可用。
- 每轮 key breakdown total：702 / 455 / 541 ms（scan 496 / 274 / 337 ms）；preload 均命中（2,119 entries / 8,814,944 B / 6–13 ms），不是冷缓存。
- 每轮 `agent.textures_patched` 均出现；`miss breakdown: total=11264, sourceless=3, sourced=11261` 稳定。

### 3.3 post-purge（未跑）

- 提权检查 `clear_standby.ps1 -CheckOnly` 在本机非提权 shell 返回 `NOT_ELEVATED`（exit 3，无清缓存副作用），按规格停止条件未运行 post-purge 臂。
- 因此没有“清缓存后第 1 轮 read bytes 显著高于后两轮”的数据；结论只用 warm 分布，不用单轮差值。

### 3.4 与历史同口径对照

- key：旧 15 次中位 **7,606 ms**（3,336–14,402） vs 新 3 次中位 **545 ms**（**457–706**）。
- 菜单：本轮 3 次 **68.6–83.1 s**（中位 70.1） vs 历史 **76.9–98.2 s**；2 轮低于历史下沿、1 轮 83.1 仍在区间内。由于 `cache_control=none`、单会话 3 轮、无 purge 对照，**不把低于历史区间解读为收益**；Task 1 的长时 no-FR 运行可能使 OS 缓存偏热，无法归因。
- `read_bytes_menu` 约 802.0–802.5 MB，极差约 0.47 MB（<0.06%）。这与“热 OS 缓存 + 稳定资源足迹”一致，但 `ReadTransferCount` 统计的是请求的传输字节，可由缓存满足，不是物理盘读取的完整证明；且无冷臂对照，只能作为启发式证据。

## 4. Java 17 审计

### 4.1 class major

| 目录/文件 | class 数 | majors | 非 61 |
|---|---:|---|---|
| `build/agent/classes` | 26 | `{"61": 26}` | 无（bad=[]） |
| `build/java/classes` | 42 | `{"61": 42}` | 无（bad=[]） |
| `build/agent/hypernova.agent.jar` | 63 | `{"49": 37, "61": 26}`（ASM 52 允许；实测 49） | 37 个为 bundled ASM 9.1 第三方类，仅报告，不影响 `ok` |
| `build/java/hypernova.jar` | 42 | `{"61": 42}` | 无 |

- `expected_major=61`，`ok=true`，审计工具 exit 0。

### 4.2 Java 21 API

- `java21_api_hits` = `[]`（要求空）。
- 扫描范围：`src/**/*.java` + 两个 classes 目录的全部 constant pool（`javap -verbose`）。

### 4.3 JRE17 全量

Base runtime：`D:/github/Hypernova-Infinite-Engine/Starsector-098-Base/jre/bin/java.exe`

| 套件 | runtime | 结果 | 日志 |
|---|---|---|---|
| agent | `openjdk 17.0.10` | 64 found / 64 started / **63 successful / 1 aborted / 0 failed**（17 containers successful） | `build/m1e-jre17-agent-tests.log` |
| mod | `openjdk 17.0.10` | 95 found / 95 started / **95 successful / 0 failed**（16 containers successful） | `build/m1e-jre17-mod-tests.log` |

- runtime 首行（两个日志）：`runtime: openjdk version "17.0.10" 2024-01-16 LTS`。
- 与系统 Java 21 的差异：结果无差异；审计保证所有 first-party class 为 major 61、无 21-only API。
- symlink assumption：**abort**（1 个 agent 测试 `symlinkToFileFollowsLegacySemantics`，原因 `symlinks unsupported here: ... 客户端没有所需的特权`），不是失败。
- 工具链测试：`python -m pytest tests/tools -q` → **183 passed, 2 failed**。2 个失败是既有 `test_smoke_check.py::{test_jar_provenance_detects_mismatch, test_provenance_mismatch_fails_without_skip}`（合成夹具仍写原始字节 `b"old"`/`b"new"`；自 `ea0a2c6` 起 provenance 改用 `zipfile` 内容哈希，任何 Python 版本都会抛 `BadZipFile`，与 Python 版本无关），**M-1e 前已存在、记为 known/deferred，不是新增失败**。

## 5. 回滚与重跑

```bash
# 0) 构建并安装（重跑前）
bash tools/java/build-agent.sh
bash tools/java/build-mod.sh
python tools/install_agent.py --game Starsector-098-260mods --env 260mods-lite \
  --jar build/agent/hypernova.agent.jar

# 1) 重新生成 no-FR 档（不改源档）
python -I tools/m1e_profile.py --src Starsector-098-260mods/Miko_Lite.txt \
  --out Starsector-098-260mods/Miko_Lite_nofr.txt --force

# 2) no-FR 两臂（--jvm-arg 必须用等号形式；--wait-menu 3600 是本机实测所需）
# arm B（textures off，基线）
python -I tools/smoke_run.py --profile miko-lite-nofr --rounds 1 --wait-menu 3600 \
  --jvm-arg=-Dhypernova.textures=false --json-out build/m1e-nofr-off.json
# arm A（textures on，门禁）
python -I tools/smoke_run.py --profile miko-lite-nofr --rounds 1 --wait-menu 3600 \
  --jvm-arg=-Dhypernova.textures=true --json-out build/m1e-nofr-on.json

# 3) 测量（arm B 轮转：.3 头 + .log 尾，按时间顺序拼接）
cat Starsector-098-260mods/starsector-core/starsector.log.3 \
    Starsector-098-260mods/starsector-core/starsector.log > build/m1e-nofr-off.log
cp Starsector-098-260mods/saves/hypernova/scripts-agent.log build/m1e-nofr-off-agent.log
python -I tools/m1b_measure.py --log build/m1e-nofr-off.log \
  --agent-log build/m1e-nofr-off-agent.log --normal-metric cleaned \
  --baseline 30378 --json-out build/m1e-nofr-off-measure.json   # 预期 exit 1（textures off）
# arm A 无轮转：只复制 current log
cp Starsector-098-260mods/starsector-core/starsector.log build/m1e-nofr-on.log
cp Starsector-098-260mods/saves/hypernova/scripts-agent.log build/m1e-nofr-on-agent.log
python -I tools/m1b_measure.py --log build/m1e-nofr-on.log \
  --agent-log build/m1e-nofr-on-agent.log --expect-no-fr --normal-metric cleaned \
  --baseline 30378 --json-out build/m1e-nofr-on-measure.json  # 预期 exit 0

# 4) warm 3 轮（测前确认无残留 java.exe）
python -I tools/m1e_rounds.py --profile miko-lite --rounds 3 --tag warm \
  --json-out build/m1e-rounds-warm.json

# 5) 提权检查（-CheckOnly：只检查，不清 standby list）；仅当 ELEVATED 才跑 post-purge
powershell -NoProfile -ExecutionPolicy Bypass -File tools/clear_standby.ps1 -CheckOnly
# 若输出 ELEVATED：
python -I tools/m1e_rounds.py --profile miko-lite --rounds 3 --purge once --tag cold \
  --json-out build/m1e-rounds-cold.json

# 6) Java 审计
python -I tools/m1e_java_audit.py --classes build/agent/classes --classes build/java/classes \
  --jar build/agent/hypernova.agent.jar --jar build/java/hypernova.jar \
  --source src --json-out build/m1e-java-audit.json

# 7) JRE17 全量
JAVA_RUNTIME="D:/github/Hypernova-Infinite-Engine/Starsector-098-Base/jre/bin/java.exe" \
  bash tools/java/run-agent-tests.sh 2>&1 | tee build/m1e-jre17-agent-tests.log
JAVA_RUNTIME="D:/github/Hypernova-Infinite-Engine/Starsector-098-Base/jre/bin/java.exe" \
  bash tools/java/run-tests.sh 2>&1 | tee build/m1e-jre17-mod-tests.log
```

## 6. 已知限制

- OS 缓存未受控时，warm 数字只能作观察；`read_bytes_menu` 是启发式证据（`ReadTransferCount` 为请求字节），不是物理盘读取或内存映射的完整证明。
- 菜单时间只有单会话 3 轮、`stop=forced`、无 purge 对照；不宣称净收益，也不把低于历史区间归因于任何改动。
- arm B 的测量日志跨 `starsector.log.3` + `starsector.log` 轮转，且拼接片段含更早 FR-on 会话的 7 条 `Fast Rendering` 行；FR 判定依赖 `_select_session` 选中的最后一个会话（`fr_anchor=0`）。arm A 未轮转，只用 current log。
- 两个 agent 日志均为跨会话追加；引用 `FR missing` / `textures: patched` 时必须取最后一次 premain 会话（smoke JSON 已记录正确时间戳），不能直接用 `grep -m1`。
- no-FR 臂没有覆盖“FR 0.9.7rc2 + Hypernova”组合（那是后续独立任务）。
- 260mods 的 256 个启用 mod 中只有 VOpt 引用 `com/genir`；其它 mod 的反射/字节码未逐一证明。VOpt 在 no-FR 下走 `FR not enabled, handling DDS files manually`，两臂均正常。
- Java 审计的 API 列表是已知清单，不是 JDK 17/21 全量 diff；jar 内 49-major 类为 bundled ASM，属第三方。
- `tests/tools/test_smoke_check.py` 的 2 个失败为 M-1e 前既有问题（合成夹具 `b"old"`/`b"new"` 与 `ea0a2c6` 起的 `zipfile` 内容哈希不兼容，任何 Python 版本均失败），known/deferred，不是本轮新增。
- 本次验证不修改生产代码（`src/**` 零改动），不升级 FR（继续 pin 0.9.5）。
