package hypernova.agent;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class KeyManifestRefreshTest {
    @TempDir Path tmp;

    @Test
    void refreshSkipsFileThatVanishedAfterScan() throws Exception {
        Path f = tmp.resolve("gone.java");
        Files.writeString(f, "class Gone {}");
        KeyManifest m = KeyManifest.load(tmp.resolve("manifest.json"));
        Files.delete(f);

        List<KeyManifest.Entry> entries = m.refresh(
                List.of(new KeyScanner.FileInfo(f, 10L, 1L)), false);

        assertTrue(entries.isEmpty(), "a file deleted between scan and hash must be skipped");
    }

    @Test
    void refreshIsCleanWhenAttributesMatchAndNotRacy() throws Exception {
        Path f = tmp.resolve("a.java");
        Files.writeString(f, "class A {}");
        FileTime past = FileTime.fromMillis(System.currentTimeMillis() - 60_000L);
        Files.setLastModifiedTime(f, past);
        Path mf = tmp.resolve("manifest.json");
        KeyScanner.FileInfo info = new KeyScanner.FileInfo(f, Files.size(f), past.toMillis());

        KeyManifest first = KeyManifest.load(mf);
        first.refresh(List.of(info), false);
        assertTrue(first.saveNeeded(), "a new file must make the manifest dirty");
        first.save(mf);

        KeyManifest reloaded = KeyManifest.load(mf);
        reloaded.refresh(List.of(info), false);
        assertFalse(reloaded.saveNeeded(),
                "unchanged inputs below savedAt must reuse the hash and skip the rewrite");
    }

    @Test
    void forceRehashAlwaysMarksDirty() throws Exception {
        Path f = tmp.resolve("b.java");
        Files.writeString(f, "class B {}");
        FileTime past = FileTime.fromMillis(System.currentTimeMillis() - 60_000L);
        Files.setLastModifiedTime(f, past);
        Path mf = tmp.resolve("manifest2.json");
        KeyScanner.FileInfo info = new KeyScanner.FileInfo(f, Files.size(f), past.toMillis());

        KeyManifest first = KeyManifest.load(mf);
        first.refresh(List.of(info), false);
        first.save(mf);

        KeyManifest reloaded = KeyManifest.load(mf);
        reloaded.refresh(List.of(info), true);
        assertTrue(reloaded.saveNeeded(),
                "-Dhypernova.rehash=true must not take the reuse fast path");
    }
}
