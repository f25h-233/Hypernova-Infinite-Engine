# 远行星号 0.98a-RC8 性能优化部署指南

面向想自己搭一套的人。**不提供任何整合包**，只提供「去哪拿、放哪里、怎么配、怎么验」的步骤。

全部内容基于 2026-10-25 的论坛与上游仓库实况核对，链接均可自行访问。

---

## 0. 先看清一件事：你不需要分发任何东西

这条路能成立，靠的不是"我打包给你"，而是**所有组件本来就有公开且允许再分发的来源**：

| 层 | 组件 | 发布方 | 拿到的方式 |
|---|---|---|---|
| 游戏本体 | Starsector 0.98a-RC8 | Fractal Softworks | 自行购买 |
| 汉化 | 远星汉化组 v2026-10-15 | 远星汉化组，**仅论坛发布** | 论坛帖 `thread-19430` 附件 |
| 渲染 | Fast Rendering 0.9.5 | genir，**Unlicense（公共领域）** | GitHub `Halke1986/starsector-render` |
| 显存 | VramOptimizer 1.0.45 | DeCell，**MIT** | GitHub `DeCEll-1/VramOptimizer` |
| 运行时 | Mikohime Configurator v0.8.1 | Gaius Cassius 分叉（原作者 Yue/Himemiko 已批准再分发） | GitHub `GaiusCassiusL/...` |
| Java | Temurin JDK 28+13-ea | Eclipse Adoptium，**GPLv2+CE** | GitHub 预发布标签；配置器可代下并校验 SHA-256 |

> **JDK 是这里唯一没有"稳定版"的组件。** 28 目前是 EA（预发布），Adoptium 正式通道只到 27。细节见 §2.4 和 §5.2.1。GPLv2+CE 允许自由再分发，但没必要——让读者自己下或者让配置器代下即可。

**关键点：你写的是教程，不是整合包。** 论坛《Mod 区规定》2.6.1 的「整合包发布」章节要求整合包内**每一个** Mod 都拿到作者许可。教程不触发这条——读者自己在论坛点附件、自己在 GitHub 下 zip，你的帖子只是告诉他们按什么顺序点。

所以下面这份指南，你可以原样发成论坛帖子。

---

## 1. 四条必须知道的论坛规矩

写帖子前先看这四条，能省掉后面被删帖的麻烦。

### 1.1 汉化包只能从论坛下（硬约束）

`localization_license.txt` 第 1 条：

> 本汉化包仅允许由远星汉化组直接进行发布，不允许其它任何组织或个人进行任何形式的转载或发布。

第 6 条更明确：

> 本汉化包唯一指定的发布地点为远行星号中文论坛（https://www.fossic.org/）。

**所以：教程里只能写"去 `thread-19430` 下附件"，不能给汉化包的直链，也不能把汉化包塞进你自己的包里。** 这一条和 FR/VOpt 的宽松许可完全不同，是最容易踩的。

### 1.2 整合包条目要求逐个授权（绕开它）

同章节：

> 整合包内的**每个** Mod 必须获得其作者关于允许使用该 Mod 制作整合包的许可。

这条是"大道磨灭"的根源。**绕法就是不发整合包。** 你发教程，读者自己下，授权链条各自成立。

### 1.3 帖子发在哪个版块

- 教程类 → **游戏指南**（`forum-65`），帖子类型选「教程」
- 不要发到「游戏资源」（`forum-39`），那是放整合包和游戏下载的

### 1.4 附件优先用论坛自带、少用网盘

管理规定第 2 条：

> 请不要使用中国大陆无法访问的下载来源……请减少使用百度云。论坛鼓励使用自带的附件上传功能来存储与游戏相关的各种资源。

你的教程里指向 GitHub Release 是可以的（FR 和 VOpt 在论坛索引里就是这么登记的），但如果能同时给出论坛帖附件链接更好。

---

## 2. 部署流程（读者照着做）

### 2.0 准备

| 项 | 要求 | 说明 |
|---|---|---|
| 操作系统 | Windows 10/11 64 位 | FR 的 Windows 版绑 0.98a-RC8；Linux 有独立分叉但落后 |
| 内存 | ≥ 16 GB 物理内存 | 8 GB 堆 + 预触碰会先占住 8 GB；边跑游戏边开浏览器会挤 |
| 磁盘 | ≥ 15 GB 空闲 | 游戏本体 + DDS 缓存(数百 MB～数 GB) + 法线缓存 |
| 权限 | 无管理员要求 | 只要不装在 `Program Files` 下 |

**建议安装路径**：任意非系统盘、不含空格与 `!` 的目录（Mikohime 配置器明确检测 `!` 并拒绝运行，因为 cmd 延迟展开会吃掉它）。

---

### 2.1 装游戏本体 + 汉化

1. 购买并安装 Starsector 0.98a-RC8
2. 打开论坛帖 `https://www.fossic.org/thread-19430-1-1.html`
3. 下载 **「独立汉化包 · 黑体版」** 的 `.exe`（约 36.9 MB）
   - 选「独立汉化包」而不是「中文汉化版」，是因为后者自带游戏本体，你可能已经买了
   - 选「黑体版」而不是「优化测试版」，原因见 §4
4. 运行安装器，指向游戏根目录

> 汉化包会覆盖 `starsector-core` 下若干文件。**装之前先备份整个 `starsector-core`**，出问题能整体还原。

---

### 2.2 装 Fast Rendering（渲染层）

**为什么要这一层**：原版是"游戏线程调一次 GL 就等一次驱动"，FR 把 GL 调用改成命令队列丢给独立渲染线程；加载期还开 3 纹理线程 + 3 脚本线程 + 2 声音线程并行。

1. 打开 `https://github.com/Halke1986/starsector-render/releases/tag/v0.9.5`
2. 下载 `fast-rendering-0.9.5.zip`（约 680 KB）
3. 解压，把里面的 **7 个文件**全部复制到 `starsector-core/`：

```
fr.jar
fr.agent.jar
fr.bat
fr.noterminal.bat
fr.vmparams
fr.readme.txt
FR_SS.ico
```

4. **版本选择**：本指南用 **0.9.5**。理由有两条 -
   - 论坛搬运帖 `thread-21060` 登记的是 0.9.4，而 0.9.5 的更新日志只有一句"新增 glBindAttribLocation / glBindFragDataLocation 支持，BoxUtil 1.6.x 需要"——即 0.9.5 是让 BoxUtil 能跑的最小版本
   - 上游最新是 0.9.6（2026-10-24），改动为"修复 Combat Chatter 头像不渲染"和"新增 fr.version.txt"，非破坏性；想用也行，但要自己冒烟

**不要**用 `fr.bat` 启动——那是给原版 JRE 用的。后面会用 Mikohime 生成的启动器替代它。

---

### 2.3 装 VramOptimizer（显存 + 加载层）

**为什么要这一层**：它把 PNG 离线压成 BC7 格式的 DDS。显存从 ~12 GB 降到 ~3.7 GB，加载时跳过 PNG 解码。

1. 打开 `https://www.fossic.org/thread-21395-1-1.html`（论坛搬运帖，附件在帖内）
   或 `https://github.com/DeCEll-1/VramOptimizer/releases/tag/v1.0.45`
2. 下载 **`VramOptimizer-win-x64-sc.zip`**（约 44.7 MB）
   - `-sc` = self-contained，自带 .NET 运行时，不需要额外装 .NET
   - 不选 `-sc` 的版本需要本机装 .NET 8
3. 解压，把 `VramOptimizer` 文件夹整个放进 `mods/`

此时先**不要**跑 DDSCreator——要等 mod 列表定下来再烘焙，否则白烤。

---

### 2.4 装 JDK 28

**先说清楚一件事**：JDK 28 目前仍是 **EA（Early Access，预发布）版本**，不是正式版。Adoptium 的 stable 通道里查不到它（`available_releases` 只到 27），只能从 GitHub 的预发布标签下载。

**为什么还是用它**：28 的 `UseCompactObjectHeaders` 是**默认开启**的（27 需要手动加参数，更早版本根本没有）。这一项把对象头从 16 字节压到 8 字节，是加载期几百万个小对象的真实收益来源。

#### 下载

**方式 A（推荐）：让 Mikohime 配置器代下**

配好 §2.5 的配置器后，在主菜单选 `J`（下载并安装 Java），它会：

- 从 Adoptium 官方链接拉取 **28+13-ea**
- 用内置的 SHA-256 校验完整性
- 解压到游戏根目录，文件夹名固定为 `jdk-28+13`

这一步不需要你自己找链接。

**方式 B：手动下载**

| 项 | 值 |
|---|---|
| 版本 | **28+13-ea**（2026-08-28 发布） |
| 直链 | `https://github.com/adoptium/temurin28-binaries/releases/download/jdk-28%2B13-ea-beta/OpenJDK-jdk_x64_windows_hotspot_28_13-ea.zip` |
| 大小 | 153.2 MB |
| SHA-256 | `7059d3b49fea21d9546676bc766555990f209e9e11a61fd7763483a159a47a4c` |

**为什么是 +13 而不是最新的 +21**：Adoptium 每周出一个 build，现在最新是 **28+21-ea**（2026-10-23）。但 Mikohime 配置器把它 pin 死在 **28+13**，SHA-256 也是按这个算的。用配置器的自动下载就只能拿 +13。手动装 +21 也行，见下面的注意事项。

#### 装在哪个目录（硬性要求）

**必须解压到游戏根目录，且文件夹名必须以 `jdk-28` 开头。**

配置器靠这个模式识别 Java 安装：

```powershell
Get-SafeComponentDirectories -Patterns @('jdk-27*', 'jdk-28*')
```

也就是说：

```
你的游戏目录/
├── starsector.exe
├── jdk-28+13/          ← 名字必须是 jdk-28 开头
│   └── bin/java.exe
├── mods/
└── starsector-core/
```

名字不对（比如 `jdk-28`、`jdk28`、`openjdk-28`）配置器就看不见它，菜单里会显示 `Java 27 or 28: Not found`。

> 顺带：配置器也会扫描 `jre\bin\java.exe`（游戏自带的 Java 17），所以哪怕不装 JDK 28 也能跑，只是拿不到 28 的收益。

#### 手动装 +21 的注意事项

1. 解压后把文件夹**改名成 `jdk-28+21`**（同样要 `jdk-28` 前缀）
2. 配置器会检测到它并列为可选项
3. 但配置器里 pin 的 SHA-256 是 +13 的，**自动下载路径不会给你 +21**
4. 能不能跑通那套调优参数，取决于 +21 是否还支持这些 flag。见 §5 的兼容性说明

---

### 2.5 装 Mikohime 配置器

**为什么要这一层**：一套经过调整的 JVM 参数，包括大堆预触碰、异步日志、给 C2 的编译指令表、以及 Java 28 专属的 compact headers 组合。

1. 打开 `https://github.com/GaiusCassiusL/Starsector_Mikohime-Unofficial-Java28-Configurator/releases/tag/v0.8.1`
2. 下载 `Mikohime.Unofficial.Configurator.-.Java.28+-v0.8.1-Windows.zip`（约 7 MB）
3. 解压到**游戏根目录**（和 `starsector.exe` 同级）：

```
你的游戏目录/
├── starsector.exe
├── Configure_Me.cmd      ← 解压出来的
├── mikohime/             ← 解压出来的
├── mods/
├── starsector-core/
└── ...
```

4. 运行 `Configure_Me.cmd`

**菜单里这么选**：

| 步骤 | 选择 | 理由 |
|---|---|---|
| Java 版本 | **Java 28**；如果菜单显示 `Not found`，先选 `J` 下载安装 | 见 §2.4。装好的文件夹必须叫 `jdk-28...` 才会被识别 |
| 内存 | 按它推荐值（16 GB 机器一般给 10 GB） | 别手填超过物理内存的一半 |
| Fast Rendering | **Enabled** | 它会自动检测 `starsector-core/fr.jar` 是否存在 |
| FR Resource Cache | **可以不装** | 见下方说明 |
| Prepatcher | **不装** | 与 0.98a-RC8 兼容性未验证 |
| 大页内存 | **关闭** | 需要 `SeLockMemoryPrivilege` 权限，不开就必然警告 |
| 日志 | **Reduced** | 加载期日志能少几万行 |
| 启动器背景 | 随意 | 纯装饰 |

> **FR Resource Cache 是什么**：加速资源文件索引的附加 agent，最新 v0.4（2026-09-06）。它对 FR 版本有白名单校验，遇到不认识的版本会进"兼容模式"并打警告。**如果你用的是 0.9.5（我们锁的版本），它可能不在白名单里。** 不确定就先不装，装 FR 本身已经拿到主要收益。

5. 配置完成后会生成两个文件：
   - `Miko_Simple.txt`（JVM 参数）
   - `Miko_Rouge.bat`（启动器）

**每改一次配置，这两个文件就会被重写。** 所以自定义参数要改在配置器的"高级配置"里，别直接改 `Miko_Simple.txt`——下次跑配置器就没了。

---

### 2.6 加你要玩的内容 Mod

1. 把 mod 文件夹放进 `mods/`
2. 打开游戏启动器，在 Mod 管理里勾选启用
3. 用启动器正常进一次游戏，确认能进主菜单

> **注意**：FR 与某些 Mod 冲突。已知的坑见 §5。

---

### 2.7 烘焙 DDS 缓存（关键一步，顺序不能错）

mod 列表定下来之后才做这步。

1. 关闭游戏
2. 进 `mods/VramOptimizer/bin/`，双击 **`DDSCreator.exe`**
3. 它会读 `mods/enabled_mods.json`，列出你启用的 mod
4. 菜单操作：
   - **`EditMods`**：确认要处理的 mod（默认全选，可以排除）
   - **`Change the compression quality`**：选 `Default` 或 `Fast`
     - 编码质量档：`Creative (Slow speed)` / `Slow` / `Default` / `Fast` / `Faster` / `Fastest`
     - 质量越高烘焙越久，纹理质量越好。Mod 多的话先用 `Fast` 试
   - **`ProcessMods`**：开始烘焙
5. 等它跑完。**基座级别（几个前置 mod）几分钟；几百个 mod 要 10–40 分钟**
6. 完成后 `mods/` 下会生成 `DDSCache/` 目录

**DDSCreator 是交互式的**，命令行跑会报错：

```
System.NotSupportedException: Cannot show selection prompt since the current terminal isn't interactive.
```

必须在真正的终端窗口里双击运行。

**烘焙完再启动游戏。** 顺序反了的话，游戏会用 PNG 加载，DDS 缓存白做。

---

### 2.8 启动

双击 **`Miko_Rouge.bat`**。

不要用：
- `starsector.exe`（走原版 JRE 17，没有 FR，没有 Java 28）
- `fr.bat`（走原版 JRE 17，没有 Java 28 的调优）
- 论坛汉化优化测试版附带的 exe（见 §4）

---

### 2.9 验证生效

启动进主菜单后，打开 `starsector-core/starsector.log`，搜这几行：

| 搜什么 | 应该看到 | 说明 |
|---|---|---|
| `Java version:` | `28-beta (64-bit)` | 确认走的是 JDK 28 |
| `Max memory:` | `10240MB` 或你设的值 | 确认堆大小生效 |
| `Fast Rendering: v` | `Fast Rendering: v0.9.5` | 确认 FR agent 挂上了 |
| `SHA-256 checksum` | 0.98a-RC8 应为 `2e207732388bfb82...` | FR 记录了游戏 jar 的哈希。**换游戏版本后这串会变**，出问题先对这里 |
| `Created new virtual main OpenGL context` | 出现 2 次左右 | FR 的虚拟 GL 上下文建起来了 |

如果 `Java version` 显示 17，说明启动器没走对——检查是不是双击错了 bat。

---

## 3. 三层各管什么（写帖子时的原理段落）

这三层解决的是**不同的瓶颈**，不是重复劳动。

### 3.1 JVM 层（Mikohime + JDK 28）

| 机制 | 效果 |
|---|---|
| `-XX:+UseCompactObjectHeaders`（28 默认开） | 对象头 16 字节 → 8 字节。加载期几百万个小对象，累计省几百 MB，且对象排得更密、CPU 缓存命中率更高 |
| `-Xms8g -Xmx16g + AlwaysPreTouch` | 启动时就把内存真实分配并清零，避免加载中反复缺页中断 |
| `-XX:UseG1GC` | 停顿控制在毫秒级（实测 3–13 ms） |
| log4j2 + disruptor 异步日志 | 原版 log4j 1.2.9 是同步写盘，几万行日志每行都等 IO |
| `.rouge_owo` 编译指令表 | 战斗类只用 C1 快速编译，图形/工具类交给 C2 并开向量化 |
| `LaunchMiko.ps1`（可选的自定义脚本） | 每 10 秒把进程从 Windows 效率模式拉出来 + 提优先级 |

**注意**：`LaunchMiko.ps1` 不是 Mikohime 自带的，是自定义脚本。你不用它也能跑，只是少了"抑制 EcoQoS"那层。

### 3.2 引擎层（Fast Rendering）

| 机制 | 效果 |
|---|---|
| GL 调用变命令队列 + 独立渲染线程 | 游戏线程不再等显卡驱动返回 |
| 加载期线程池：3 纹理 + 3 脚本 + 2 声音 + 1 资源 | 纹理解码、Janino 编译、音频、目录枚举四路并行 |
| `FileLoaderFast` 文件索引 | 一次性爬目录建"路径 → 句柄"表，之后全是 Map 查询，替掉几万次逐目录查找 |
| `DDSIntegration` | 读 `DDSCache/*/dds_metadata.json`，有 DDS 就直接用；4 线程后台读盘，渲染线程提交 |

### 3.3 资产层（VramOptimizer + GraphicsLib 法线缓存）

| 机制 | 效果 |
|---|---|
| BC7 压缩的 DDS | 每像素 4 字节 → 约 1 字节，显存降 75%+；GPU 硬件解压，不经 CPU |
| GraphicsLib 法线图缓存 | 每张舰船贴图的法线图只算一次，存进 `mods/shaderLib/cache/`（实测 11,803 张、447 MB） |

**代价**：改任何 mod 都要重烘 DDS；法线缓存也会部分失效，下一次启动会慢一次。

---

## 4. 陷阱：论坛汉化的「优化测试版」不要和 FR 一起用

论坛汉化帖 `thread-19430` 有两个分支：

| 分支 | 说明 |
|---|---|
| 🧪 **优化测试版**（推荐） | 自带高清矢量字体、中文输入支持、**热启动加速（非首次启动加速 50%–80%）** |
| **传统版本**（黑体/宋体/综艺体） | 不包含优化 |

汉化帖自己的 FAQ 写着：

> **汉化后支不支持使用 Java 26 优化？**
> 传统版本：理论上可以支持。但由于没有经过详细测试，所以可能存在报错风险。
> 🧪优化测试版：理论上可以支持，但高清矢量字体和其它部分优化可能不生效。**新的版本本身启动很快，不建议一同使用！**

**这就是你踩过的那个坑的来源。** 优化测试版自己已经做了启动加速，再叠 FR 会互相干扰。

社区里已有专门的兼容层 —— **MixinFR**（论坛 `thread-21705`，作者 GerBeria）：

> MixinFR 把 MixinLib 与 Fast Rendering 打包成一个 mod……内置 MixinLib 1.1.0 + Fast Rendering **0.9.5**
> 1.2.1 修复「优化版 + FR + LunaLib」全新初始化时的启动崩溃
> 1.2.1 修复装 MixinFR 后 HD 矢量字体回退成模糊位图（优化版）

也就是说：**优化测试版 + FR 的组合，社区是专门做了一层补丁才跑通的。**

**本指南的选择：传统版本 + FR + Mikohime。** 理由：

1. 传统版本的变量少，出问题好定位
2. 优化测试版本质上是在和 FR 抢同一个收益（启动加速），叠加收益递减
3. MixinFR 虽然解决了兼容问题，但它自己也承认"游戏版本更新会使整合失效，直到上游混淆映射刷新"

**如果你坚持要用优化测试版**，那么正确做法是装 MixinFR 而不是裸装 FR，并且接受它的维护成本。

---

## 5. 已知冲突与边界

### 5.1 Mod 冲突

| Mod | 情况 |
|---|---|
| **UIUtil 6.0.0** | **硬冲突，会崩**。它用 `GL15.glBufferData(int, IntBuffer, int)` 上传索引缓冲，而 FR 0.9.5 对该重载的实现就是一句 `throw new UnsupportedOperationException(...)`（已反编译确认）。一进战役就 fatal。**别装** |
| Combat Misc Utilities (CMUtils) | FR 官方声明不兼容 |
| Particle Engine | FR 官方声明：超大规模战斗下偶发崩溃，正常游戏可忽略 |
| 带 Mixin 的 Mod | FR 会重写 29 个游戏类，Mixin 织入不到被重写的类。MixinFR 会打 `WARN target is rewritten by Fast Rendering` |

### 5.2 版本边界

| 场景 | 后果 |
|---|---|
| 游戏本体更新（0.98a-RC8 → 更高） | FR 的字节码改写靠**混淆后的类名/方法名**定位目标。游戏一更新，混淆映射就变了，改写会落空或改错地方。FR 启动时会把 `starfarer_obf.jar` 的 SHA-256 **记进日志**（不是校验失败就拒绝），所以出问题时第一件事是对比这个哈希 |
| FR 升级到 0.9.6 | 上游已发布（2026-10-24），但论坛索引登记的仍是 0.9.4，本指南基线是无 UIUtil 冲突且玩家实测过的 0.9.5。0.9.6 的改动只有"Combat Chatter 头像不渲染修复"和"新增 fr.version.txt"，理论上无破坏性，但需自行冒烟 |
| 增删内容 Mod | 必须重跑 DDSCreator，否则新纹理走 PNG；法线缓存也会部分重建 |
| 首次冷缓存启动 | 比热缓存慢数倍，这是预期行为 |
| JDK 换到 28+21 或更新 | **未验证**。配置器的参数表是按 28+13 写的。EA 版每周出 build，JVM flag 可能增删。换版本后第一件事是看启动有没有 `Unrecognized VM option` 报错 |

### 5.2.1 关于 JDK 28 的 EA 状态

这是整条链路里**唯一没有稳定版本承诺**的一环：

- Adoptium 的 stable 通道只到 27，28 只能从 GitHub 的 `-ea-beta` 预发布标签拿
- 从 +2 到 +21 一共 20 个 build，节奏是每周一个（2026-06-16 至 2026-10-23）
- 每个 build 之间 JVM flag 可能有变动，EA 期不保证兼容
- 配置器 pin 在 **+13**（2026-08-28），比最新落后 8 个 build

**写教程时建议原话照搬**：

> JDK 28 是预发布版本。本指南基于 28+13-ea 验证。如果你用更新的 build 出现启动报错，先换回 28+13 再排查。

如果你不想碰 EA 版，**退到 Java 27 也能拿到大部分收益**，但注意 27 的配置器版本也是 EA（`jdk-27+22-ea-beta`，2026-05-16，同样是 prerelease）。真正稳定的选择只有 Java 17（游戏自带），代价是没有 compact headers。

**版本对照速查**：

| 版本 | 状态 | 配置器支持 | compact headers |
|---|---|---|---|
| Java 17.0.10 | 正式（游戏自带 `jre/`） | 是 | 无 |
| Java 27+22-ea | EA，2026-05-16 | 是 | 需手动开 |
| Java 28+13-ea | EA，2026-08-28 | 是（**pin 死这个**） | **默认开** |
| Java 28+21-ea | EA，2026-10-23（最新） | 能识别，参数未验证 | 默认开 |

### 5.3 性能预期（别写死数字）

论坛搬运帖 `thread-21395` 给的数据：

> 测试一共 79 个 mod，常规启动时间需要 1 分 20 ~ 2 分钟，优化后启动在 15 ~ 25 秒
> 显存从 11.8 G → 3.7 G
> 帧数从 18 → 34（前提是显存爆了）

**这些是别人机器上的数字。** 你的教程里应该写成"量级参考"，并明确标注：冷缓存 vs 热缓存差异极大，只看第一次启动会误判。

---

## 6. 写帖子时的建议结构

```
标题：【0.98a-RC8】性能优化三层部署指南（Java 28 + Fast Rendering + DDS）

0. 先说清楚：本文不给整合包，只给步骤。所有组件请自行从原发布方下载。
1. 你能得到什么（量级描述，不写死秒数）
2. 前置要求（系统/内存/磁盘/路径）
3. 步骤
   3.1 游戏本体 + 汉化（指向 thread-19430）
   3.2 Fast Rendering（指向 GitHub 0.9.5）
   3.3 VramOptimizer（指向 thread-21395 或 GitHub）
   3.4 Mikohime 配置器（指向 GitHub v0.8.1）
   3.5 加内容 Mod
   3.6 烘焙 DDS（强调顺序）
   3.7 启动（强调用 Miko_Rouge.bat）
4. 验证生效（给出要搜的日志行）
5. 三层原理（简版）
6. 已知冲突（UIUtil、CMUtils、优化测试版）
7. 常见问题
   - 进不去 / 卡启动器
   - 启动变慢了（多半是冷缓存）
   - 中文不显示
   - 闪退
```

### 必须写进去的三句话

1. **「本文不含任何游戏文件、汉化文件或 Mod 文件。」**
2. **「汉化包仅可在远行星号中文论坛获取，请勿转载。」**
3. **「所有 Mod 请从原发布方下载，遵守各自授权。」**

---

## 7. 验证清单（发帖前自己跑一遍）

- [ ] 干净安装，只装汉化传统版 → 能进主菜单
- [ ] 加 FR → 日志出现 `Fast Rendering: v0.9.5`
- [ ] 加 VramOptimizer 但**不烘焙** → 能进游戏，只是没提速
- [ ] 跑 DDSCreator → `mods/DDSCache/` 生成，里面有 `dds_metadata.json`
- [ ] 加 Mikohime + JDK 28 → 日志 `Java version: 28-beta`
- [ ] 用 `Miko_Rouge.bat` 启动 → 日志 `Max memory: 10240MB`
- [ ] 第二次启动明显快于第一次（证明缓存生效）
- [ ] 加一个吃 GraphicsLib 的内容 Mod → 不崩
- [ ] 开新档进战役 → 不崩
- [ ] 打一场战斗 → 不崩
- [ ] 存档、退出、重进、读档 → 正常

---

## 8. 本目录里的文件

`_upstream/` 是核对用的上游包，**不要打包分发**，只用于本地验证版本与文件结构：

| 文件 | 来源 | 授权 |
|---|---|---|
| `fast-rendering-0.9.5.zip` | GitHub `Halke1986/starsector-render` | Unlicense（公共领域） |
| `VramOptimizer-win-x64-1.0.45.zip` | GitHub `DeCEll-1/VramOptimizer` | MIT |
| `Mikohime-Configurator-v0.8.1-Windows.zip` | GitHub `GaiusCassiusL/...` | 原作者已批准再分发 |

**未下载的**：JDK 28 太大（153 MB），本目录没存。按 §2.4 的链接或让配置器代下。

校验值（用于确认你下到的和这份一致）：

```
fr.jar          7ee51ee90e914c56fcd262087d7d65e712e767df2b7ba50ccf300afd4e742a29
fr.agent.jar    8b9c787134899e2027ca6023099838a11992de4c8aaab7974a3de1dda88f59a2
```

JDK 28+13-ea 的官方 SHA-256（来自 Adoptium API，与配置器内 pin 的值一致）：

```
OpenJDK-jdk_x64_windows_hotspot_28_13-ea.zip
7059d3b49fea21d9546676bc766555990f209e9e11a61fd7763483a159a47a4c
```

---

## 9. 参考链接

| 内容 | 地址 |
|---|---|
| **Temurin JDK 28+13-ea（本指南用的版本）** | `https://github.com/adoptium/temurin28-binaries/releases/tag/jdk-28%2B13-ea-beta` |
| Temurin JDK 28 全部 build | `https://github.com/adoptium/temurin28-binaries/releases` |
| Temurin JDK 27+22-ea（备选） | `https://github.com/adoptium/temurin27-binaries/releases/tag/jdk-27%2B22-ea-beta` |
| Adoptium API（查任意版本最新 build） | `https://api.adoptium.net/v3/info/available_releases` |
| 汉化发布帖 | `https://www.fossic.org/thread-19430-1-1.html` |
| Mod 区规定 2.6.1 | `https://www.fossic.org/thread-13-1-1.html` |
| 论坛管理规定 | `https://www.fossic.org/thread-4-1-1.html` |
| Fast Rendering 搬运帖 | `https://www.fossic.org/thread-21060-1-1.html` |
| VramOptimizer 搬运帖 | `https://www.fossic.org/thread-21395-1-1.html` |
| MixinFR（优化版兼容层） | `https://www.fossic.org/thread-21705-1-1.html` |
| FR 上游 | `https://github.com/Halke1986/starsector-render` |
| VOpt 上游 | `https://github.com/DeCEll-1/VramOptimizer` |
| Mikohime 配置器 | `https://github.com/GaiusCassiusL/Starsector_Mikohime-Unofficial-Java28-Configurator` |
| Temurin JDK 28 | `https://github.com/adoptium/temurin28-binaries` |
