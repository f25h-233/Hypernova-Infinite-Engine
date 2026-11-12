Hypernova 无限引擎 —— manifest 生成工具
=========================================

这个文件夹是给玩家在自己游戏目录里重新生成 manifest 用的。发行包自带的
manifest 只覆盖原版（Base）纹理集，装了其它 mod 的话等于没覆盖，需要跑一次。

用法
----

  generate-manifest.bat    Windows，双击。按你的游戏目录重新生成 manifest
  generate-manifest.sh     Git Bash / Linux 版，需要系统里有 Python 3.8+
  install-agent.bat        Windows，双击。安装可选的启动期 agent
  rollback-agent.bat       Windows，双击。**游戏起不来时用这个**

Windows 上什么都不用装。这些批处理会调用本文件夹里自带的 Python 运行时
（python\ 子目录），不会往你系统里装任何东西，也不改 PATH 和注册表。

关于 agent 和回滚
-----------------

install-agent.bat 会往启动文件里插一行 -javaagent。插错的话 JVM 会直接拒绝
启动，游戏连启动器都出不来。所以它旁边配了一个回滚脚本。

rollback-agent.bat 不弹确认、不问参数，双击就把所有启动文件里的 Hypernova
agent 行删干净，然后你直接启动游戏。改了 mod 文件夹名字之前，也先跑一次它。

两个脚本都会给改过的文件留 .bak-hypernova-时间戳 备份，想找回原样可以手动覆盖。

没有它会出现什么
----------------

游戏照常能玩。主 mod 的预取命中率会低——它靠 manifest 判断哪些贴图值得提前加载，
而发行包里那份只认识原版贴图。agent 那一半不受影响。

高清字体覆盖的还原
------------------

Hypernova agent 在远星汉化优化测试版（startup-optimization）上，会先让优化版
自己生成高清字体缓存，再把成对的 *.fnt / *_0.png 覆盖到
starsector-core\graphics\fonts\，原文件备份为 *.bak-hypernova-hd。

想把字体退回原版：

  restore-font-hd.bat    一键还原（不弹确认；还原后删除备份）

注意：只要 agent 还装着，下次启动会重新生成并覆盖。要永久退回，先运行
rollback-agent.bat 去掉 agent 行，再运行 restore-font-hd.bat。

清单和你的 mod 集对不上时，懒加载会 fail-open（不跳过也不代理），不会崩。

产物
----

  data\config\hypernova\manifest-v1.json
  data\config\hypernova\manifest-probe-cache-v1.json
  data\config\hypernova\lazy-skip-v1.txt
  data\config\hypernova\lazy-skip-v2.txt

游戏目录下还会补一张占位图：
  starsector-core\graphics\hypernova\blank.png

跑完重启游戏。以后装删了 mod，再跑一次就行。只改数值类 CSV、或者同尺寸替换
图片，不需要重跑：manifest 只记贴图路径和尺寸，不读舰船/武器/势力这些数据。
（改了图片尺寸，或者新增了贴图文件，才建议再跑一次。）

要跑多久
--------

第一次跑（或刚加了一大批新贴图）要逐张读图片文件头，会慢一些：原版规模十几秒，
两三百个 mod 在 SSD 上一般一两分钟；机械盘、杀软实时扫描开着会更久。窗口里会一直
有进度行（`[ 21.3s] 解析贴图头 12000/80594`），最底下一行还有条小鱼在游，游得慢
不代表卡住。

生成器会把读到的尺寸写进 manifest-probe-cache-v1.json。以后再跑，没变过的图片
直接复用缓存，只有新增/改动过的图片才重新读——只加一个 mod 不会再扫全量。如果
你装了 VramOptimizer，DDS 缓存已经烘好时，生成也会更快。

关于自带的 Python
-----------------

python\ 里是 python.org 官方的 Windows embeddable 运行时，原样未改动。

  版本   3.12.10 (amd64)
  文件   python-3.12.10-embed-amd64.zip
  SHA256 4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3

它只在你双击批处理时被调用一次，用完进程就退出。所有脚本只用标准库，
不需要 pip，不联网。

如果杀毒软件把 python\ 里的文件删了，批处理会提示你重新解压。
懒得折腾也可以不跑，游戏照样能玩，只是主 mod 的预取效果打折。
