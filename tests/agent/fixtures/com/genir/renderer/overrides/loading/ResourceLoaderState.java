package com.genir.renderer.overrides.loading;

/** Test fixture with the same method shapes as FR 0.9.7 ResourceLoaderState. */
public class ResourceLoaderState {
    public boolean fileLoaders;
    public boolean specStore;
    public boolean mods;

    private void initFileLoaders() throws Exception {
        fileLoaders = true;
    }

    private void initSpecStore(java.util.Map<String, Object> session) throws Exception {
        specStore = session != null;
    }

    private void initMods() throws Exception {
        mods = true;
    }

    public void run() throws Exception {
        initFileLoaders();
        initSpecStore(new java.util.HashMap<>());
        initMods();
    }
}
