package hypernova.agent.textures;

import hypernova.agent.AgentLog;

import java.lang.reflect.Method;
import java.util.concurrent.atomic.AtomicBoolean;

/** Deletes a GL texture through FR's bridge (records into the current frame). */
public final class GlBridge {
    private static volatile boolean resolved;
    private static volatile boolean available;
    private static volatile Method delete;
    private static final AtomicBoolean FAIL_LOGGED = new AtomicBoolean();

    private GlBridge() {
    }

    public static boolean available() {
        resolve();
        return available;
    }

    /** Must be called on the game main thread. */
    public static boolean deleteTexture(int id) {
        resolve();
        if (!available || id <= 0) return false;
        try {
            delete.invoke(null, id);
            return true;
        } catch (Throwable t) {
            if (FAIL_LOGGED.compareAndSet(false, true)) {
                AgentLog.fail("lazy: glDeleteTextures failed for id " + id, t);
            }
            return false;
        }
    }

    private static void resolve() {
        if (resolved) return;
        synchronized (GlBridge.class) {
            if (resolved) return;
            try {
                ClassLoader cl = GlBridge.class.getClassLoader();
                Class<?> gl;
                try {
                    gl = Class.forName("com.genir.renderer.bridge.opengl.GL11", false, cl);
                } catch (Throwable t) {
                    gl = Class.forName("com.genir.renderer.bridge.commands.GL11", false, cl);
                }
                delete = gl.getMethod("glDeleteTextures", int.class);
                available = true;
                AgentLog.info("lazy: GL delete bridge resolved on " + gl.getName());
            } catch (Throwable t) {
                available = false;
                if (FAIL_LOGGED.compareAndSet(false, true)) {
                    AgentLog.fail("lazy: GL delete bridge unavailable; eviction disabled", t);
                }
            } finally {
                resolved = true;
            }
        }
    }
}
