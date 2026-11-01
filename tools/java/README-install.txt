Hypernova Infinite Engine — 纹理懒加载安装说明（M2.7）

1. 本包内的 data/config/hypernova/manifest-v1.json 与 lazy-skip-v1.txt 由
   Starsector-098-Base 的纹理集生成，只对 Base 安装准确。
2. 在 260mods 或任何其它 mod 集上使用前，必须重新生成 manifest/skip。
   发行 zip 不含 tools/；请取得仓库（含 tools/），在仓库根目录运行：
     bash tools/java/install-manifest.sh <游戏目录>
   该脚本生成 manifest/skip，并复制/断言
   <游戏目录>/starsector-core/graphics/hypernova/blank.png 非空
   （需先有 build/java/hypernova.jar，见 tools/java/build-mod.sh）。
   若手工运行 Python 安装器：
     python -I tools/install_manifest.py --game-root <游戏目录>
   它只写 manifest/skip，不会复制 blank.png；需自行把
   graphics/hypernova/blank.png 复制到
   <游戏目录>/starsector-core/graphics/hypernova/blank.png。
   然后重启游戏。skip/manifest 的 generation 不匹配时 lazy 会 fail-open
   （不跳过、不代理），不会崩溃；尺寸/维度不一致时同样 fail-open。
3. 默认 textures.lazy.enabled=false、textures.lazy.eviction.enabled=false；发行配置
   （data/config/hypernova/hypernova.json）没有 lazy 块。要开启，在 textures 下写入：
     "lazy": {"enabled": true, "dds": true, "eviction": {"enabled": false}}
   或使用启动参数 -Dhypernova.textures.lazy=true。
4. 回滚：把 textures.lazy.enabled 设为 false，或加
   -Dhypernova.textures.lazy=false，或删除启动文件中的 -javaagent 行。
