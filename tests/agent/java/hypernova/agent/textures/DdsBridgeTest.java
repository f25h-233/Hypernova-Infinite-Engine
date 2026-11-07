package hypernova.agent.textures;

import com.genir.renderer.overrides.loading.textures.DDSIntegration;
import com.genir.renderer.overrides.loading.textures.TextureData;
import org.junit.jupiter.api.Test;

import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class DdsBridgeTest {
    @Test
    void readsDdsTextureData() {
        TextureData td = new TextureData();
        td.imageWidth = 32;
        td.imageHeight = 16;
        td.width = 32;
        td.height = 16;
        td.ddsImagePath = Path.of("D:/cache/a.dds");
        DDSIntegration.next = td;
        DdsBridge.Data data = DdsBridge.get(Path.of("D:/mods/a.png"));
        assertNotNull(data);
        assertEquals(32, data.imageWidth());
        assertEquals(16, data.imageHeight());
        assertEquals(32, data.width());
        assertEquals(16, data.height());
        assertEquals(Path.of("D:/cache/a.dds"), data.ddsPath());
    }

    @Test
    void nonDdsAndNullAreRejected() {
        DDSIntegration.next = null;
        assertNull(DdsBridge.get(Path.of("D:/mods/a.png")));
        TextureData td = new TextureData();
        td.ddsImagePath = null;
        DDSIntegration.next = td;
        assertNull(DdsBridge.get(Path.of("D:/mods/a.png")));
    }

    @Test
    void commitReturnsId() {
        DDSIntegration.nextId = 77;
        assertEquals(77, DdsBridge.commit(new TextureData()));
    }

    @Test
    void newHandlerUsesNameNullAndPath() throws Exception {
        TextureData td = new TextureData();
        Object out = DdsBridge.newHandler(new FakeLoader(), "graphics/a.png", td, 9);
        assertEquals("null|graphics/a.png|9", out);
    }

    @Test
    void newHandlerHandlesStaticAndInstanceShapes() throws Exception {
        TextureData td = new TextureData();
        assertEquals("null|graphics/a.png|9",
                DdsBridge.newHandler(new FakeLoader(), "graphics/a.png", td, 9));
        assertEquals("s|null|graphics/a.png|9",
                DdsBridge.newHandler(new StaticLoader(), "graphics/a.png", td, 9));
    }

    @Test
    void commitLockUsesFrExecutorLockWhenPresent() {
        Object loader = new Object();
        Object frLock = DdsBridge.executorLock();
        assertNotNull(frLock, "fixture ResourceLoaderLock must resolve");
        assertSame(frLock, DdsBridge.commitLock(loader));
    }

    @Test
    void commitLockFallsBackToLoaderMonitor() {
        Object loader = new Object();
        assertSame(loader, DdsBridge.commitLock(loader, null));
        Object frLock = new Object();
        assertSame(frLock, DdsBridge.commitLock(loader, frLock));
    }

    static final class FakeLoader {
        private String newVanillaTextureHandler(
                String name, String path, TextureData data, int id) {
            return name + "|" + path + "|" + id;
        }
    }

    static final class StaticLoader {
        private static String newVanillaTextureHandler(
                String name, String path, TextureData data, int id) {
            return "s|" + name + "|" + path + "|" + id;
        }
    }
}
