Hypernova 无限引擎 1.9.7 —— 安装说明
======================================

这个包里有两半东西。主 mod 放进 mods 就能用；可选的 Java agent 需要改启动参数，
拿出来以后，启动阶段的优化才会生效。主 mod 不依赖 agent，agent 不装也不会出问题。


一、主 mod（先做这个）
----------------------

1. 解压。压缩包解开以后本来就是一个 hypernova_infinite_engine 文件夹
2. 把这个文件夹整个放进游戏的 mods\ 目录（不要再套一层）
3. 启动器里 Mod 管理勾上它
4. 重启游戏

最终路径应该长这样： 游戏目录\mods\hypernova_infinite_engine\mod_info.json

如果你解压出来的是 hypernova-1.9.7\hypernova_infinite_engine\ 这种两层，
把里面那层 hypernova_infinite_engine 拖到 mods\ 下面，否则游戏扫不到它。

默认配置就能跑，不用改任何文件。


二、让它在你自己的环境里真正生效（重要）
----------------------------------------

主 mod 的预取靠 data\config\hypernova\manifest-v1.json 决定哪些贴图值得提前加载。
发行包里这份是拿纯原版（Base）纹理集扫出来的，只有三千多条记录。你要是装了几十上百
个 mod，里面的舰船和武器贴图它一条都不认识，预取基本落空——不会报错，只是没效果。

想让它在你的环境里出力，跑一次重新生成：

  Windows：双击 hypernova-tools\generate-manifest.bat
  Git Bash / Linux：bash hypernova-tools/generate-manifest.sh

脚本会往上找三层，自动认出游戏目录，扫描 mods\ 里所有 mod 的贴图，把新的
manifest-v1.json 和 lazy-skip 写回本 mod 的 data\config\hypernova\。

Windows 上不用装任何东西，那个批处理会用包里自带的 Python 运行时。
只有 Git Bash / Linux 那条才需要系统里有 Python 3.8 或更新版本。

它要扫一遍 mods\ 里所有贴图。原版规模十几秒，两三百个 mod 大概一两分钟
（硬盘慢、杀软实时扫描开着会更久）。第一次跑、或者刚加了一大批新贴图时，
要逐张读图片文件头，会慢一些；生成器会把尺寸记进 manifest-probe-cache-v1.json，
以后再跑只处理新增或改动过的图片，只加一个 mod 不会重扫全量。窗口里会一直刷
进度行，屏幕不动是在干活，别急着关。

跑完重启游戏。以后加了新 mod，再跑一次。


三、可选 agent
--------------

agent 管启动阶段，包括 Fast Rendering 的文件索引、Janino 脚本的预编译缓存、
GraphicsLib 法线图的缓存补丁。可选，不装也能玩。

装法：双击 hypernova-tools\install-agent.bat，按一次回车。

它会自己找到你的启动文件（starsector-core\fr.vmparams、Miko_Simple.txt、
Miko_Lite.txt 这几个都认），把 -javaagent 那一行插在 Fast Rendering 的 agent
之前，每改一个文件都留 .bak-hypernova-时间戳 备份。重复双击不会插出第二行。

【游戏起不来就双击这个】
  hypernova-tools\rollback-agent.bat

它会把所有启动文件里的 Hypernova agent 行删干净，不弹确认，不问参数，做完直接
就能启动游戏。这是给"手一点不敢动"的人准备的，别自己改文件。

那一行长这样，想手动删也认得出来：
  -javaagent:../mods/hypernova_infinite_engine/jars/hypernova.agent.jar

注意：改了 mod 文件夹的名字，这一行就指向不存在的路径，游戏会起不来。
改名字之前先跑一次 rollback-agent.bat。

装完打开 starsector.log 搜 hypernova，能看到启动行就是装上了。


四、默认值与开关
----------------

主 mod 运行期预取        开    hypernova.json 里的 enabled
agent 文件索引           开    fileIndex.enabled
agent Janino 脚本缓存    开    scripts.enabled
agent 法线图缓存补丁     开    textures.enabled
纹理懒加载               关    textures.lazy.enabled
DDS 懒加载               跟随懒加载    textures.lazy.dds
显存淘汰和 LRU           关    textures.lazy.eviction.enabled
场景卸载                 关    textures.lazy.eviction.sceneUnload
帧时间探针               关    -Dhypernova.frameProbe=true

配置文件在 data\config\hypernova\hypernova.json。


五、出问题怎么退
----------------

主 mod    把 hypernova.json 里的 enabled 改成 false，或在 Mod 管理里取消勾选
agent     删掉启动文件里 -javaagent:...hypernova.agent.jar 那一行
懒加载    把对应的 enabled 改回 false，或加 -D...=false

所有路径都是 fail-open，配置或清单对不上时退回原版加载，不会崩。


六、日志
--------

游戏日志        starsector-core\starsector.log
agent 日志      saves\hypernova\scripts-agent.log


七、许可
--------

代码 Apache-2.0，文档 CC BY 4.0。包里没有游戏本体，也没有任何第三方 mod 的内容。
