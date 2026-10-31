package com.fs.util;

/** Test fixture with the runtime shape of the FR-obfuscated ResourceLocation. */
public class ObfuscatedLocation {
    public enum Kind { DIRECTORY, ABSOLUTE_AND_CWD, CLASSPATH }

    public Kind t;          // unique enum
    public String p;        // unique String
    public boolean m;       // unique boolean
    public Object extra;    // ignored

    public ObfuscatedLocation(Kind t, String p, boolean m) {
        this.t = t;
        this.p = p;
        this.m = m;
    }
}
