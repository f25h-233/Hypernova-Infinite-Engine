package hypernova.agent.textures;

import com.fs.graphics.Object;

/**
 * Engine-facing proxy for a skipped texture. Instances are inserted into
 * oOoO.new before mod onApplicationLoad runs, so every skip path stays present
 * in the global texture repository. The first bind/id read materializes the
 * real texture when the caller is the loading thread or the runtime main
 * thread; other threads only see the manifest-sized placeholder.
 *
 * <p>This class lives in a separate source root because it must be compiled
 * against the game jars (com.fs.graphics.Object), while the rest of the agent
 * compiles without them.
 */
public final class LazyProxyObject extends Object {
    public LazyProxyObject(int target, int id, String path) {
        super(target, id, path);
    }

    @Override
    public void Ø00000() {
        LazyTextures.onProxyUse(this);
        super.Ø00000();
    }

    @Override
    public int ö00000() {
        LazyTextures.onProxyUse(this);
        return super.ö00000();
    }
}
