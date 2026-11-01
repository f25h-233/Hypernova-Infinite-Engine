package hypernova.agent.textures;

import hypernova.agent.AgentLog;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Reflection bridge to FR 0.9.7rc2 DDSIntegration/TextureData and the merged
 * TextureLoader.newVanillaTextureHandler. Any shape mismatch disables only the
 * DDS path; the caller falls back to the M2.5 PNG materializer.
 */
public final class DdsBridge {
    public record Data(Object texData, int imageWidth, int imageHeight,
                       int width, int height, Path ddsPath) {
    }

    private static volatile boolean resolved;
    private static volatile boolean available;
    private static volatile Method getTexture;
    private static volatile Method commitTexture;
    private static volatile Method isDds;
    private static volatile Field imageWidth;
    private static volatile Field imageHeight;
    private static volatile Field width;
    private static volatile Field height;
    private static volatile Field ddsPath;
    private static final AtomicBoolean FAIL_LOGGED = new AtomicBoolean();

    private DdsBridge() {
    }

    public static boolean available() {
        resolve();
        return available;
    }

    public static Data get(Path absoluteImagePath) {
        resolve();
        if (!available) return null;
        try {
            Object data = getTexture.invoke(null, absoluteImagePath);
            if (data == null) return null;
            if (isDds != null && !(Boolean) isDds.invoke(data)) return null;
            Path file = (Path) ddsPath.get(data);
            if (file == null) return null;
            return new Data(data, imageWidth.getInt(data), imageHeight.getInt(data),
                    width.getInt(data), height.getInt(data), file);
        } catch (Throwable t) {
            fail("getTexture failed for " + absoluteImagePath, t);
            return null;
        }
    }

    public static int commit(Object textureData) {
        resolve();
        if (!available) return -1;
        try {
            return (int) commitTexture.invoke(null, textureData);
        } catch (Throwable t) {
            fail("commitTexture failed", t);
            return -1;
        }
    }

    /**
     * Invokes the FR-private newVanillaTextureHandler(name, path, texData, id)
     * merged into the real com.fs.graphics.TextureLoader class. name is null,
     * matching FR's synchronous 7-arg path.
     */
    public static Object newHandler(Object loader, String path, Object textureData, int id)
            throws Exception {
        if (loader == null) throw new IllegalStateException("loader null");
        for (Method m : loader.getClass().getDeclaredMethods()) {
            if (!"newVanillaTextureHandler".equals(m.getName())) continue;
            Class<?>[] p = m.getParameterTypes();
            if (p.length == 4 && p[0] == String.class && p[1] == String.class
                    && p[2].isInstance(textureData) && p[3] == int.class) {
                m.setAccessible(true);
                return m.invoke(null, null, path, textureData, id);
            }
        }
        throw new NoSuchMethodException("TextureLoader.newVanillaTextureHandler"
                + "(String,String,TextureData,int)");
    }

    private static void resolve() {
        if (resolved) return;
        synchronized (DdsBridge.class) {
            if (resolved) return;
            try {
                ClassLoader cl = DdsBridge.class.getClassLoader();
                Class<?> dds = Class.forName(
                        "com.genir.renderer.overrides.loading.textures.DDSIntegration", false, cl);
                Class<?> td = Class.forName(
                        "com.genir.renderer.overrides.loading.textures.TextureData", false, cl);
                getTexture = dds.getMethod("getTexture", Path.class);
                commitTexture = dds.getMethod("commitTexture", td);
                isDds = td.getMethod("isDDS");
                imageWidth = td.getField("imageWidth");
                imageHeight = td.getField("imageHeight");
                width = td.getField("width");
                height = td.getField("height");
                ddsPath = td.getField("ddsImagePath");
                available = true;
                AgentLog.info("lazy: DDS bridge resolved");
            } catch (Throwable t) {
                available = false;
                fail("DDS bridge unavailable; DDS materialization disabled", t);
            } finally {
                resolved = true;
            }
        }
    }

    private static void fail(String message, Throwable t) {
        if (FAIL_LOGGED.compareAndSet(false, true)) {
            AgentLog.fail("lazy: " + message, t);
        }
    }
}
