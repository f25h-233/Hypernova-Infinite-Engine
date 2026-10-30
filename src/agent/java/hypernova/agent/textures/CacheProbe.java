package hypernova.agent.textures;

import java.io.File;
import java.util.HashSet;
import java.util.Set;

/** agent 域缓存探测器：启动时扫描一次 cache/ 文件名，脚本域只做 set 查询，避免 SecurityException。 */
public final class CacheProbe {
    private static volatile Set<String> names = Set.of();

    private CacheProbe() {
    }

    /** 在 agent 域调用；失败时保持空集（= 懒加载禁用，回退原路径）。 */
    public static void init(String modRoot) {
        Set<String> out = new HashSet<>(40_000);
        try {
            File[] files = new File(modRoot, "cache").listFiles();
            if (files != null) {
                for (File f : files) {
                    if (f.isFile() && f.length() >= 8L) out.add(f.getName());
                }
            }
        } catch (Throwable ignored) {
        }
        names = out;
    }

    public static int size() {
        return names.size();
    }

    /** cachePath 形如 cache/foo___SHIP_normal.png；只取 basename 查表。 */
    public static boolean has(String cachePath) {
        if (cachePath == null || cachePath.isEmpty()) return false;
        int slash = Math.max(cachePath.lastIndexOf('/'), cachePath.lastIndexOf('\\'));
        String name = slash >= 0 ? cachePath.substring(slash + 1) : cachePath;
        return names.contains(name);
    }
}
