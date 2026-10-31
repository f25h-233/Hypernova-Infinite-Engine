package com.genir.renderer.overrides.loading;

import com.fs.util.FileLoader;

import java.io.File;

/** Test fixture with the same nested FileHandle shape as FR 0.9.7. */
public class ResourceHandle {
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
