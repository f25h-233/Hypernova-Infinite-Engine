package com.genir.renderer.overrides.loading;

public final class ResourceLoaderLock {
    public static final Object executorLock = new Object();

    private ResourceLoaderLock() {
    }
}
