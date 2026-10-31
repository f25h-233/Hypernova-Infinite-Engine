package hypernova.agent;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

/**
 * Persistent file-enumeration index. Compile-time independent of FR/game classes.
 *
 * <p>Format (gzip): magic, version, locations[type,path,isMod], dirs[path,mtime],
 * entries[key,filePath,locationIndex]. Any decode failure returns null; callers
 * must fall back to the original FR crawl.
 */
public final class FileIndex {
    static final int MAGIC = 0x484E4649; // "HNFI"
    static final int VERSION = 1;
    private static final int MAX_RECORDS = 2_000_000;
    private static final int MAX_STRING = 1 << 20;

    public record Location(String type, String path, boolean isMod) {
        public Location {
            Objects.requireNonNull(type, "type");
            Objects.requireNonNull(path, "path");
        }
    }

    public record Dir(String path, long mtime) {
        public Dir {
            Objects.requireNonNull(path, "path");
        }
    }

    public record Entry(String key, String filePath, int locationIndex) {
        public Entry {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(filePath, "filePath");
        }
    }

    private final List<Location> locations;
    private final List<Dir> dirs;
    private final List<Entry> entries;

    public FileIndex(List<Location> locations, List<Dir> dirs, List<Entry> entries) {
        this.locations = List.copyOf(locations);
        this.dirs = List.copyOf(dirs);
        this.entries = List.copyOf(entries);
    }

    public List<Location> locations() { return locations; }
    public List<Dir> dirs() { return dirs; }
    public List<Entry> entries() { return entries; }

    /** Returns null for absent, corrupt, truncated, or unknown-version files. */
    public static FileIndex read(Path file) {
        if (file == null || !Files.isRegularFile(file)) return null;
        try (DataInputStream in = new DataInputStream(
                new GZIPInputStream(new BufferedInputStream(Files.newInputStream(file))))) {
            if (in.readInt() != MAGIC) return null;
            if (in.readInt() != VERSION) return null;

            int locationCount = count(in);
            List<Location> locations = new ArrayList<>(locationCount);
            for (int i = 0; i < locationCount; i++) {
                locations.add(new Location(readString(in), readString(in), in.readBoolean()));
            }
            int dirCount = count(in);
            List<Dir> dirs = new ArrayList<>(dirCount);
            for (int i = 0; i < dirCount; i++) {
                dirs.add(new Dir(readString(in), in.readLong()));
            }
            int entryCount = count(in);
            List<Entry> entries = new ArrayList<>(entryCount);
            for (int i = 0; i < entryCount; i++) {
                entries.add(new Entry(readString(in), readString(in), in.readInt()));
            }
            return new FileIndex(locations, dirs, entries);
        } catch (IOException | RuntimeException e) {
            return null;
        }
    }

    public void write(Path file) throws IOException {
        Path parent = file.toAbsolutePath().getParent();
        if (parent != null) Files.createDirectories(parent);
        Path tmp = file.resolveSibling(file.getFileName() + ".tmp");
        try (DataOutputStream out = new DataOutputStream(
                new GZIPOutputStream(new BufferedOutputStream(Files.newOutputStream(tmp))))) {
            out.writeInt(MAGIC);
            out.writeInt(VERSION);
            out.writeInt(locations.size());
            for (Location location : locations) {
                writeString(out, location.type());
                writeString(out, location.path());
                out.writeBoolean(location.isMod());
            }
            out.writeInt(dirs.size());
            for (Dir dir : dirs) {
                writeString(out, dir.path());
                out.writeLong(dir.mtime());
            }
            out.writeInt(entries.size());
            for (Entry entry : entries) {
                writeString(out, entry.key());
                writeString(out, entry.filePath());
                out.writeInt(entry.locationIndex());
            }
        }
        try {
            Files.move(tmp, file, StandardCopyOption.REPLACE_EXISTING,
                    StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException e) {
            Files.move(tmp, file, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    /**
     * Returns the first directory that disappeared, stopped being a directory,
     * or whose mtime changed; null when every directory still matches.
     *
     * <p>A pure mtime comparison is insufficient: {@link java.io.File#lastModified()}
     * returns 0 for a missing path, so a directory recorded with mtime 0 (already
     * absent when the index was built) would otherwise look unchanged. Windows
     * directory mtime changes when entries are added/removed, which is exactly
     * the invalidation condition for an enumeration cache.
     */
    public String firstMismatchedDir() {
        for (Dir dir : dirs) {
            java.io.File file = new java.io.File(dir.path());
            if (!file.isDirectory() || file.lastModified() != dir.mtime()) {
                return dir.path();
            }
        }
        return null;
    }

    private static int count(DataInputStream in) throws IOException {
        int n = in.readInt();
        if (n < 0 || n > MAX_RECORDS) throw new IOException("bad record count: " + n);
        return n;
    }

    private static String readString(DataInputStream in) throws IOException {
        int n = in.readInt();
        if (n < 0 || n > MAX_STRING) throw new IOException("bad string length: " + n);
        byte[] bytes = new byte[n];
        in.readFully(bytes);
        return new String(bytes, StandardCharsets.UTF_8);
    }

    private static void writeString(DataOutputStream out, String value) throws IOException {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(bytes.length);
        out.write(bytes);
    }
}
