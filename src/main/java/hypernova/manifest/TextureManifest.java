package hypernova.manifest;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class TextureManifest {
    private final Map<String, TextureEntry> byPath;
    private final Map<Layer, List<String>> byLayer;
    private final int duplicates;

    private TextureManifest(Map<String, TextureEntry> byPath,
                            Map<Layer, List<String>> byLayer,
                            int duplicates) {
        this.byPath = byPath;
        this.byLayer = byLayer;
        this.duplicates = duplicates;
    }

    public static TextureManifest fromJson(JSONObject root) {
        Map<String, TextureEntry> byPath = new LinkedHashMap<>();
        Map<Layer, List<String>> byLayer = new EnumMap<>(Layer.class);
        int duplicates = 0;
        JSONObject layers = root.optJSONObject("layers");
        if (layers == null) {
            return new TextureManifest(byPath, byLayer, 0);
        }
        for (Layer layer : Layer.values()) {
            JSONArray arr = layers.optJSONArray(layer.name());
            List<String> paths = new ArrayList<>();
            byLayer.put(layer, paths);
            if (arr == null) {
                continue;
            }
            for (int i = 0; i < arr.length(); i++) {
                JSONObject e = arr.optJSONObject(i);
                if (e == null) {
                    continue;
                }
                String path = e.optString("path", "");
                if (path.isEmpty()) {
                    continue;
                }
                if (byPath.containsKey(path)) {
                    duplicates++;
                    continue;
                }
                TextureEntry entry = new TextureEntry(
                        path,
                        e.optString("modId", "unknown"),
                        e.optInt("w", 0),
                        e.optInt("h", 0),
                        e.optBoolean("baked", false),
                        layer);
                byPath.put(path, entry);
                paths.add(path);
            }
        }
        return new TextureManifest(byPath, byLayer, duplicates);
    }

    public TextureEntry lookup(String path) {
        return byPath.get(path);
    }

    public Layer lookupLayer(String path) {
        TextureEntry e = byPath.get(path);
        return e == null ? null : e.layer();
    }

    public List<String> pathsInLayer(Layer layer) {
        List<String> paths = byLayer.get(layer);
        return paths == null ? List.of() : Collections.unmodifiableList(paths);
    }

    public int size() {
        return byPath.size();
    }

    public int sizeInLayer(Layer layer) {
        List<String> paths = byLayer.get(layer);
        return paths == null ? 0 : paths.size();
    }

    public int duplicateCount() {
        return duplicates;
    }
}
