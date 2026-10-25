package hypernova.manifest;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class TextureManifestTest {

    // 0.98a 自带的 2010 版 org.json 中 put(...) 抛受检 JSONException（现代版为运行时异常），
    // 故测试辅助方法显式声明 throws。
    private static JSONObject entry(String path, String modId, int w, int h) throws JSONException {
        JSONObject e = new JSONObject();
        e.put("path", path);
        e.put("modId", modId);
        e.put("w", w);
        e.put("h", h);
        e.put("baked", true);
        return e;
    }

    private static JSONObject manifest(Object... layers) throws JSONException {
        JSONObject root = new JSONObject();
        JSONObject l = new JSONObject();
        for (int i = 0; i < layers.length; i += 2) {
            JSONArray arr = new JSONArray();
            for (Object o : (List<?>) layers[i + 1]) {
                arr.put(o);
            }
            l.put((String) layers[i], arr);
        }
        root.put("layers", l);
        return root;
    }

    @Test
    void indexesByPath() throws JSONException {
        JSONObject root = manifest(
                "L1", List.of(entry("graphics/ui/a.png", "core", 10, 10)),
                "L2", List.of(entry("graphics/ships/b.png", "mymod", 20, 30)),
                "L3", List.of());
        TextureManifest m = TextureManifest.fromJson(root);
        assertEquals(2, m.size());
        assertEquals("mymod", m.lookup("graphics/ships/b.png").modId());
        assertEquals(20, m.lookup("graphics/ships/b.png").w());
        assertNull(m.lookup("graphics/nope.png"));
    }

    @Test
    void earlierLayerWinsOnDuplicate() throws JSONException {
        JSONObject root = manifest(
                "L1", List.of(entry("graphics/weapons/x.png", "modA", 10, 10)),
                "L2", List.of(),
                "L3", List.of(entry("graphics/weapons/x.png", "core", 99, 99)));
        TextureManifest m = TextureManifest.fromJson(root);
        assertEquals(1, m.size());
        assertEquals("modA", m.lookup("graphics/weapons/x.png").modId());
        assertEquals(Layer.L1, m.lookupLayer("graphics/weapons/x.png"));
        assertEquals(1, m.duplicateCount());
    }

    @Test
    void skipsEntriesWithoutPath() throws JSONException {
        JSONObject bad = new JSONObject();
        bad.put("modId", "x");
        JSONObject root = manifest("L1", List.of(bad), "L2", List.of(), "L3", List.of());
        TextureManifest m = TextureManifest.fromJson(root);
        assertEquals(0, m.size());
    }

    @Test
    void pathsInLayerPreserveManifestOrder() throws JSONException {
        JSONObject root = manifest(
                "L1", List.of(entry("a.png", "m", 1, 1), entry("b.png", "m", 1, 1)),
                "L2", List.of(),
                "L3", List.of());
        TextureManifest m = TextureManifest.fromJson(root);
        assertEquals(List.of("a.png", "b.png"), m.pathsInLayer(Layer.L1));
        assertEquals(List.of(), m.pathsInLayer(Layer.L2));
    }
}
