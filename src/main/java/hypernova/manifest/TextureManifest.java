package hypernova.manifest;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class TextureManifest {
    private final Map<String, TextureEntry> byPath;
    private final Map<Layer, List<String>> byLayer;
    private final int discarded;
    private final int crossLayerConflicts;

    private TextureManifest(Map<String, TextureEntry> byPath,
                            Map<Layer, List<String>> byLayer,
                            int discarded,
                            int crossLayerConflicts) {
        this.byPath = byPath;
        this.byLayer = byLayer;
        this.discarded = discarded;
        this.crossLayerConflicts = crossLayerConflicts;
    }

    public static TextureManifest fromJson(JSONObject root) {
        Map<String, TextureEntry> byPath = new LinkedHashMap<>();
        Map<Layer, List<String>> byLayer = new EnumMap<>(Layer.class);
        Map<String, EnumSet<Layer>> layersByPath = new HashMap<>();
        int discarded = 0;
        JSONObject layers = root.optJSONObject("layers");
        if (layers == null) {
            return new TextureManifest(byPath, byLayer, 0, 0);
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
                layersByPath.computeIfAbsent(path, k -> EnumSet.noneOf(Layer.class)).add(layer);
                if (byPath.containsKey(path)) {
                    discarded++;
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
        int crossLayerConflicts = 0;
        for (EnumSet<Layer> seenIn : layersByPath.values()) {
            if (seenIn.size() > 1) {
                crossLayerConflicts++;
            }
        }
        return new TextureManifest(byPath, byLayer, discarded, crossLayerConflicts);
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

    /** 被层序去重丢弃的条目数（含同层与跨层）。 */
    public int discardedCount() {
        return discarded;
    }

    /** 出现在多个不同 layer 的 path 数（同层内重复不计）。 */
    public int crossLayerConflictCount() {
        return crossLayerConflicts;
    }
}
