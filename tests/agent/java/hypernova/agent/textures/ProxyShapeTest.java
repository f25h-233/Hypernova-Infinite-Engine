package hypernova.agent.textures;

import org.junit.jupiter.api.Test;

import java.awt.Color;

import static org.junit.jupiter.api.Assertions.*;

class ProxyShapeTest {
    @Test
    void newProxySetsDimensionsUvAndIds() throws Exception {
        ProxyShape shape = ProxyShape.resolve(TextureObjectFixture.type(), TextureObjectFixture.proxyType());
        TextureObjectFixture o = new TextureObjectFixture(shape.newProxy("graphics/a.png", 40, 24));
        assertEquals(3553, o.target());
        assertEquals(0, o.id());
        assertEquals(40, o.width());
        assertEquals(24, o.height());
        assertEquals(40, o.imageWidth());
        assertEquals(24, o.imageHeight());
        assertEquals(1.0f, o.texWidth(), 1e-6);
        assertEquals(1.0f, o.texHeight(), 1e-6);
        assertEquals("graphics/a.png", o.stringId());
        assertEquals("graphics/a.png", o.path());
    }

    @Test
    void copyCopiesAllFields() throws Exception {
        ProxyShape shape = ProxyShape.resolve(TextureObjectFixture.type(), TextureObjectFixture.proxyType());
        TextureObjectFixture from = new TextureObjectFixture(3553, 7, "b");
        from.setWidth(11);
        from.setHeight(13);
        from.setImageWidth(11);
        from.setImageHeight(13);
        from.setColors(Color.RED, Color.GREEN, Color.BLUE);
        TextureObjectFixture to = new TextureObjectFixture(shape.newProxy("a", 1, 1));
        shape.copy(from.raw(), to.raw());
        assertEquals(7, to.id());
        assertEquals(11, to.width());
        assertEquals(13, to.height());
        assertEquals(Color.RED, to.color0());
        assertEquals(Color.GREEN, to.color1());
        assertEquals(Color.BLUE, to.color2());
    }

    @Test
    void missingFieldFails() {
        assertThrows(Exception.class,
                () -> ProxyShape.resolve(MissingFixture.class, MissingFixture.class));
    }

    @Test
    void resetWritesPlaceholderFields() throws Exception {
        ProxyShape shape = ProxyShape.resolve(TextureObjectFixture.type(), TextureObjectFixture.proxyType());
        TextureObjectFixture o = new TextureObjectFixture(shape.newProxy("graphics/a.png", 32, 16));
        shape.reset(o.raw(), 3553, 99, 1, 1, 1.0f, 1.0f, 32, 16);
        assertEquals(3553, o.target());
        assertEquals(99, o.id());
        assertEquals(1, o.width());
        assertEquals(1, o.height());
        assertEquals(32, o.imageWidth());
        assertEquals(16, o.imageHeight());
        assertEquals(1.0f, o.texWidth(), 1e-6);
        assertEquals(1.0f, o.texHeight(), 1e-6);
        assertEquals("graphics/a.png", o.path());
        assertEquals(Color.WHITE, o.color0());
        assertEquals(Color.WHITE, o.color1());
        assertEquals(Color.WHITE, o.color2());
    }

    static final class MissingFixture {
        MissingFixture(int a, int b, String c) {
        }
    }
}
