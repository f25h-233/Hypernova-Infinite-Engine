package com.genir.renderer.overrides.loading.textures;

import java.nio.file.Path;

/** Test fixture with the public fields of FR 0.9.7rc2 TextureData. */
public class TextureData {
    public Path imagePath;
    public Path ddsImagePath;
    public int imageWidth;
    public int imageHeight;
    public int width;
    public int height;

    public boolean isDDS() {
        return ddsImagePath != null;
    }
}
