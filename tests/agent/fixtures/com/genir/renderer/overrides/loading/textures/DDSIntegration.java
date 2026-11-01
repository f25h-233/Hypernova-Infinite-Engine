package com.genir.renderer.overrides.loading.textures;

import java.nio.file.Path;

/** Test fixture with the runtime shape of FR 0.9.7rc2 DDSIntegration. */
public class DDSIntegration {
    public static boolean initialized;
    public static TextureData next;
    public static int nextId = 42;

    public static void initialize() {
        initialized = true;
    }

    public static TextureData getTexture(Path path) {
        return next;
    }

    public static int commitTexture(TextureData data) {
        return nextId;
    }
}
