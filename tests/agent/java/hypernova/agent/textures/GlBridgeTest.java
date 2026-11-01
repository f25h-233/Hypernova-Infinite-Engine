package hypernova.agent.textures;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class GlBridgeTest {
    @Test
    void degradesWhenFrBridgeMissing() {
        assertFalse(GlBridge.available());
        assertFalse(GlBridge.deleteTexture(7));
    }
}
