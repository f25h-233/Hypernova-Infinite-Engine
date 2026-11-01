package com.fs.starfarer.api;

/** Test fixture for the game's state enum probe. */
public class Global {
    public static Object currentState;
    public static boolean throwNow;

    public static Object getCurrentState() {
        if (throwNow) throw new IllegalStateException("probe failure");
        return currentState;
    }
}
