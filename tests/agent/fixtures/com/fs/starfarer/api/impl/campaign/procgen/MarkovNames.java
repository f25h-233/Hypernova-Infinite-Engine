package com.fs.starfarer.api.impl.campaign.procgen;

/**
 * Test fixture with the runtime shape of the vanilla MarkovNames class.
 *
 * <p>FR's merged ResourceLoaderState.initMods calls
 * {@code MarkovNames.loadIfNeeded()} as its first statement, so this is the real
 * executed anchor used for {@code mods.start} (the donor FileLoader class is only
 * mergeClass input and is never loaded).
 */
public class MarkovNames {
    public static boolean loaded;

    public static void loadIfNeeded() {
        loaded = true;
    }
}
