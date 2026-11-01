package hypernova.agent.textures;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class LazyGateTest {

    @Test
    void nullPathIsNotAnError() {
        assertNull(LazyTextures.lookup(null));
        LazyTextures.probeLookup(null); // must not throw
    }

    @Test
    void dimensionMismatchMatrix() {
        assertTrue(LazyTextures.dimensionsMatch(32, 16, 32, 16));
        assertFalse(LazyTextures.dimensionsMatch(64, 16, 32, 16));
        assertFalse(LazyTextures.dimensionsMatch(32, 32, 32, 16));
        assertFalse(LazyTextures.dimensionsMatch(0, 16, 32, 16));
        assertFalse(LazyTextures.dimensionsMatch(32, 0, 32, 16));
    }

    @Test
    void drainedDisablesSkipDecision() {
        assertTrue(LazyTextures.skipAllowed(true, false, false, false,
                indexWith("graphics/a.png"), "TEXTURE", "graphics/a.png"));
        assertFalse(LazyTextures.skipAllowed(true, false, false, true,
                indexWith("graphics/a.png"), "TEXTURE", "graphics/a.png"));
        assertFalse(LazyTextures.skipAllowed(false, false, false, false,
                indexWith("graphics/a.png"), "TEXTURE", "graphics/a.png"));
        assertFalse(LazyTextures.skipAllowed(true, true, false, false,
                indexWith("graphics/a.png"), "TEXTURE", "graphics/a.png"));
    }

    @Test
    void generationCheckMatchesManifestHash(@TempDir Path dir) throws Exception {
        Path manifest = dir.resolve("manifest-v1.json");
        Files.writeString(manifest, "{\"layers\":{}}");
        String sha = LazyTextures.sha256(manifest);
        Path skip = dir.resolve("lazy-skip-v1.txt");
        Files.writeString(skip, "# generation=" + sha + "\ngraphics/a.png\t1\t1\n");
        LazySkipIndex idx = LazySkipIndex.load(skip);
        assertNull(LazyTextures.verifyGeneration(idx, manifest));
    }

    @Test
    void generationMismatchAndMissingHeaderAreRejected(@TempDir Path dir) throws Exception {
        Path manifest = dir.resolve("manifest-v1.json");
        Files.writeString(manifest, "{\"layers\":{}}");
        Path skip = dir.resolve("lazy-skip-v1.txt");
        Files.writeString(skip, "# generation=deadbeef\ngraphics/a.png\t1\t1\n");
        assertNotNull(LazyTextures.verifyGeneration(LazySkipIndex.load(skip), manifest));

        Files.writeString(skip, "graphics/a.png\t1\t1\n");
        assertNotNull(LazyTextures.verifyGeneration(LazySkipIndex.load(skip), manifest));

        Files.writeString(skip, "# generation=" + LazyTextures.sha256(manifest) + "\n");
        assertNotNull(LazyTextures.verifyGeneration(LazySkipIndex.load(skip), dir.resolve("missing.json")));
    }

    @Test
    void loadAsyncShapeGate() throws Exception {
        assertFalse(LazyTextures.isLoadAsync(null));
        assertFalse(LazyTextures.isLoadAsync(String.class.getMethod("length")));
        class Fake {
            public void loadTextureAsync(String type, String path) {
            }
        }
        assertTrue(LazyTextures.isLoadAsync(
                Fake.class.getMethod("loadTextureAsync", String.class, String.class)));
    }

    @Test
    void failOpenOnDisabledDrain() {
        assertTrue(LazyTextures.shouldFailOpenDisabledDrain(true, false, true, 1));
        assertTrue(LazyTextures.shouldFailOpenDisabledDrain(false, false, false, 1));
        assertFalse(LazyTextures.shouldFailOpenDisabledDrain(true, false, true, 0));
        assertFalse(LazyTextures.shouldFailOpenDisabledDrain(true, false, false, 5));
    }

    @Test
    void resolvesLoadAsyncIndependently() {
        class WithAsync {
            public void loadTextureAsync(String type, String path) {
            }
        }
        assertNotNull(LazyTextures.resolveLoadAsync(new WithAsync()));
        assertNull(LazyTextures.resolveLoadAsync(new Object()));
    }

    private static LazySkipIndex indexWith(String path) {
        try {
            Path dir = Files.createTempDirectory("lazy-gate");
            Path f = dir.resolve("skip.txt");
            Files.writeString(f, path + "\t10\t20\n");
            return LazySkipIndex.load(f);
        } catch (Exception e) {
            throw new AssertionError(e);
        }
    }
}
