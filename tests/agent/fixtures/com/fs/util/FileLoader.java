package com.fs.util;

/** Test fixture mirroring the fields FileIndexHook reflects on. */
public class FileLoader {
    public enum Type { DIRECTORY, ABSOLUTE_AND_CWD, CLASSPATH }

    public static final class ResourceLocation {
        public final Object ResourceLocation_type;
        public final String ResourceLocation_path;
        public final boolean ResourceLocation_isMod;

        public ResourceLocation(Object type, String path, boolean isMod) {
            this.ResourceLocation_type = type;
            this.ResourceLocation_path = path;
            this.ResourceLocation_isMod = isMod;
        }
    }
}
