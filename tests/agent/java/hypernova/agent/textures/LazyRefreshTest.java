package hypernova.agent.textures;

import org.junit.jupiter.api.Test;

import java.awt.Color;

import static org.junit.jupiter.api.Assertions.*;

/**
 * F3: an already-materialized proxy must absorb a newly registered real object
 * (new GL id after a cache clear/reload) instead of keeping stale fields.
 *
 * <p>Uses the ASM fixture shape ({@link TextureObjectFixture}), so no game
 * classes are needed. The 260mods integration path is covered by the agent log:
 * before this fix every treatment session reported {@code reregistered=1} for
 * {@code graphics/intro/bbplus_boss_splash_intro.png}; after the fix the same
 * path logs {@code lazy: refreshed ready proxy ...} and keeps failed=0.
 */
class LazyRefreshTest {
    private static final String PATH = "graphics/intro/bbplus_boss_splash_intro.png";

    private static ProxyShape shape() throws Exception {
        return ProxyShape.resolve(TextureObjectFixture.type(), TextureObjectFixture.proxyType());
    }

    private static LazyTextures.ProxyEntry readyEntry(ProxyShape shape) throws Exception {
        Object proxy = shape.newProxy(PATH, 32, 16);
        LazyTextures.ProxyEntry e =
                new LazyTextures.ProxyEntry(PATH, "TEXTURE", 32, 16, proxy);
        e.ready = true;
        return e;
    }

    private static TextureObjectFixture real(int id) {
        TextureObjectFixture real = new TextureObjectFixture(3553, id, PATH);
        real.setWidth(32);
        real.setHeight(16);
        real.setImageWidth(32);
        real.setImageHeight(16);
        real.setStringId(PATH);
        real.setColors(Color.RED, Color.GREEN, Color.BLUE);
        return real;
    }

    @Test
    void refreshCopiesNewGlIdAndFields() throws Exception {
        ProxyShape shape = shape();
        LazyTextures.ProxyEntry e = readyEntry(shape);
        TextureObjectFixture real = real(77);

        assertTrue(LazyTextures.refreshReady(shape, e, real.raw(), "register"));

        TextureObjectFixture out = new TextureObjectFixture(e.obj);
        assertEquals(77, out.id());
        assertEquals(32, out.width());
        assertEquals(16, out.height());
        assertEquals(32, out.imageWidth());
        assertEquals(16, out.imageHeight());
        assertEquals(PATH, out.stringId());
        assertEquals(PATH, out.path());
        assertEquals(Color.RED, out.color0());
        assertEquals(Color.GREEN, out.color1());
        assertEquals(Color.BLUE, out.color2());
        assertEquals(1, e.reregistered);
        assertSame(real.raw(), e.lastSource);
        assertTrue(e.ready);
    }

    @Test
    void sameSourceIsAbsorbedOnce() throws Exception {
        ProxyShape shape = shape();
        LazyTextures.ProxyEntry e = readyEntry(shape);
        TextureObjectFixture real = real(77);

        assertTrue(LazyTextures.refreshReady(shape, e, real.raw(), "register"));
        assertFalse(LazyTextures.refreshReady(shape, e, real.raw(), "engine hit"));

        assertEquals(1, e.reregistered);
        assertEquals(77, new TextureObjectFixture(e.obj).id());
    }

    @Test
    void differentSourceRefreshesAgain() throws Exception {
        ProxyShape shape = shape();
        LazyTextures.ProxyEntry e = readyEntry(shape);

        assertTrue(LazyTextures.refreshReady(shape, e, real(77).raw(), "register"));
        assertTrue(LazyTextures.refreshReady(shape, e, real(88).raw(), "engine hit"));

        assertEquals(2, e.reregistered);
        assertEquals(88, new TextureObjectFixture(e.obj).id());
    }

    @Test
    void proxyItselfAndNullAreIgnored() throws Exception {
        ProxyShape shape = shape();
        LazyTextures.ProxyEntry e = readyEntry(shape);

        assertFalse(LazyTextures.refreshReady(shape, e, e.obj, "register"));
        assertFalse(LazyTextures.refreshReady(shape, e, null, "register"));
        assertFalse(LazyTextures.refreshReady(shape, null, real(77).raw(), "register"));
        assertFalse(LazyTextures.refreshReady(null, e, real(77).raw(), "register"));
        assertEquals(0, e.reregistered);
    }

    @Test
    void dimensionMismatchIsRejectedNotCopied() throws Exception {
        ProxyShape shape = shape();
        LazyTextures.ProxyEntry e = readyEntry(shape);
        TextureObjectFixture real = real(77);
        real.setImageWidth(64);
        real.setImageHeight(32);
        try {
            assertFalse(LazyTextures.refreshReady(shape, e, real.raw(), "register"));
            TextureObjectFixture out = new TextureObjectFixture(e.obj);
            assertEquals(0, out.id());
            assertEquals(32, out.imageWidth());
            assertEquals(16, out.imageHeight());
            assertEquals(0, e.reregistered);
        } finally {
            LazyTextures.resetGateStateForTest();
        }
    }

    @Test
    void refreshMovesOwnedBytesToForeign() throws Exception {
        LazyTextures.resetGateStateForTest();
        ProxyShape shape = shape();
        LazyTextures.ProxyEntry e = readyEntry(shape);
        e.owned = true;
        LazyTextures.noteMaterialized(e, 40, true);
        assertEquals(40, LazyTextures.evictableBytesForTest());

        assertTrue(LazyTextures.refreshReady(shape, e, real(77).raw(), "register"));

        assertEquals(40, LazyTextures.liveBytesForTest());
        assertEquals(40, LazyTextures.foreignBytesForTest());
        assertEquals(0, LazyTextures.evictableBytesForTest());
        LazyTextures.resetGateStateForTest();
    }
}
