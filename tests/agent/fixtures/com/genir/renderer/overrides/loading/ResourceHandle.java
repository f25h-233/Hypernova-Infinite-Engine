package com.genir.renderer.overrides.loading;

import com.fs.util.FileLoader;

import java.io.File;

/**
 * Test fixture with both FR handle shapes:
 * 0.9.7 nested FileHandle(File, ResourceLocation) and
 * 0.9.8 top-level ResourceHandle(File, ResourceLocation, String).
 */
public class ResourceHandle {
    public final File file;
    public final FileLoader.ResourceLocation location;
    public final String cachedString;

    public ResourceHandle(File file, FileLoader.ResourceLocation location, String extension) {
        this.file = file;
        this.location = location;
        this.cachedString = null;
    }

    public static final class FileHandle {
        public final File file;
        public final FileLoader.ResourceLocation location;
        public String cachedContents;

        public FileHandle(File file, FileLoader.ResourceLocation location) {
            this.file = file;
            this.location = location;
        }
    }
}
