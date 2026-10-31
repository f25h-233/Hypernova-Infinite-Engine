package hypernova;

import hypernova.manifest.TextureManifest;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StartupSelfCheckTest {

    private static JSONObject entry(String path) throws Exception {
        JSONObject e = new JSONObject();
        e.put("path", path);
        e.put("modId", "m");
        return e;
    }

    private static JSONObject manifest(Object... layers) throws Exception {
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
    void candidatesComeOnlyFromL1() throws Exception {
        TextureManifest m = TextureManifest.fromJson(manifest(
                "L1", List.of(entry("a.png")),
                "L2", List.of(entry("b.png")),
                "L3", List.of(entry("c.png"))));
        assertEquals(List.of("a.png"),
                HypernovaPlugin.selfCheckCandidates(m, p -> false, 10));
    }

    @Test
    void loadedAndLimitAreHonored() throws Exception {
        TextureManifest m = TextureManifest.fromJson(manifest(
                "L1", List.of(entry("a.png"), entry("b.png"), entry("c.png")),
                "L2", List.of(),
                "L3", List.of()));
        assertEquals(List.of("b.png", "c.png"),
                HypernovaPlugin.selfCheckCandidates(m, "a.png"::equals, 2));
    }

    @Test
    void zeroLimitReturnsEmpty() throws Exception {
        TextureManifest m = TextureManifest.fromJson(manifest(
                "L1", List.of(entry("a.png")),
                "L2", List.of(),
                "L3", List.of()));
        assertEquals(List.of(),
                HypernovaPlugin.selfCheckCandidates(m, p -> false, 0));
    }
}
