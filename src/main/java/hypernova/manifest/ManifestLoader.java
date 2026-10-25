package hypernova.manifest;

import com.fs.starfarer.api.SettingsAPI;
import org.json.JSONObject;

public final class ManifestLoader {
    public static final String PATH = "data/hypernova/manifest-v1.json";

    private ManifestLoader() {
    }

    /** 读取失败返回 null；调用方负责降级为「预取整体禁用」。 */
    public static TextureManifest load(SettingsAPI settings) {
        try {
            JSONObject root = settings.loadJSON(PATH);
            return TextureManifest.fromJson(root);
        } catch (Exception e) {
            return null;
        }
    }
}
