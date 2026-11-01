Hypernova Infinite Engine — 纹理懒加载安装说明（M2.7）

1. 本包内的 data/config/hypernova/manifest-v1.json 与 lazy-skip-v1.txt 由
   Starsector-098-Base 的纹理集生成，只对 Base 安装准确。
2. 在 260mods 或任何其它 mod 集上使用前，必须在该游戏目录运行：
     python -I tools/install_manifest.py --game-root <游戏目录>
   然后重启游戏。skip/manifest 的 generation 不匹配时 lazy 会 fail-open
   （不跳过、不代理），不会崩溃；尺寸不一致时同样 fail-open。
3. 默认 textures.lazy.enabled=false、textures.lazy.eviction.enabled=false。
   开启方式见 data/config/hypernova/hypernova.json 或 -D 启动参数。
4. 回滚：把 textures.lazy.enabled 设为 false，或加
   -Dhypernova.textures.lazy=false，或删除启动文件中的 -javaagent 行。
