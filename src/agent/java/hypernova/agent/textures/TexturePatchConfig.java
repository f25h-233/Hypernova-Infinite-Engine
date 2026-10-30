package hypernova.agent.textures;

import org.json.JSONObject;

import java.nio.file.Files;
import java.nio.file.Path;

/** 读取 hypernova.json 的 textures 段；系统属性 hypernova.textures 优先。 */
public record TexturePatchConfig(boolean enabled) {

    public static TexturePatchConfig load() {
        String prop = System.getProperty("hypernova.textures");
        if (prop != null && !prop.isBlank()) {
            return new TexturePatchConfig(Boolean.parseBoolean(prop));
        }
        Path file = locateConfig();
        if (file == null || !Files.isRegularFile(file)) {
            // agent 已安装但没有配置文件：默认开启（补丁就是本模块的功能），
            // 显式 enabled=false 才关闭。
            return new TexturePatchConfig(true);
        }
        try {
            JSONObject root = new JSONObject(Files.readString(file));
            JSONObject textures = root.optJSONObject("textures");
            if (textures == null) return new TexturePatchConfig(true);
            return new TexturePatchConfig(textures.optBoolean("enabled", true));
        } catch (Throwable t) {
            // 配置坏了不能阻止游戏启动；默认开启，日志在 transformer 创建处记录。
            return new TexturePatchConfig(true);
        }
    }

    private static Path locateConfig() {
        try {
            var src = TexturePatchConfig.class.getProtectionDomain().getCodeSource();
            if (src != null && src.getLocation() != null) {
                Path jar = Path.of(src.getLocation().toURI());
                Path modRoot = jar.getParent() == null ? null : jar.getParent().getParent();
                if (modRoot != null) {
                    Path f = modRoot.resolve("data/config/hypernova/hypernova.json");
                    if (Files.isRegularFile(f)) return f;
                }
            }
        } catch (Throwable ignored) {
        }
        return null;
    }
}
