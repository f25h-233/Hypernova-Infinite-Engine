package hypernova.config;

public final class VersionProbe {
    public static final String EXPECTED_PREFIX = "Starsector 0.98a-RC8";

    private VersionProbe() {
    }

    public static Capability probe(String versionString, boolean frPresent) {
        if (versionString == null) {
            return new Capability(false, frPresent, "version string unavailable");
        }
        if (!versionString.startsWith(EXPECTED_PREFIX)) {
            return new Capability(false, frPresent, "game version mismatch: " + versionString);
        }
        return new Capability(true, frPresent, frPresent ? "ok" : "FR missing: vanilla path");
    }
}
