package hypernova.agent;

import org.json.JSONObject;

import java.io.File;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Injects a persisted directory enumeration into FR FileLoaderFast.DirectoryCrawler.
 *
 * <p>Everything is reflective: this class must compile without FR on the classpath.
 * Any mismatch (field rename, constructor change, corrupt index, changed directory)
 * returns -1 and lets FR perform its original crawl. It must never throw into the game.
 *
 * <p>The game's {@code ResourceLocation} is runtime-obfuscated by FR's agent
 * ({@code com.fs.util.FileLoader$ResourceLocation} becomes {@code com.fs.util.C$Oo},
 * with fields {@code super}/{@code Ó00000}/{@code String}). Field lookup therefore
 * tries the readable names first and falls back to the class shape: exactly one
 * enum-typed, one {@code String}, and one boolean field.
 */
public final class FileIndexHook {
    private static final String FH_CLASS =
            "com.genir.renderer.overrides.loading.ResourceHandle$FileHandle";
    private static final String EXCLUDED_RESOURCE_PATH = "../starfarer.res/res";

    private static volatile RuntimeContext context;
    private static final Set<Object> LOADED = Collections.newSetFromMap(new IdentityHashMap<>());
    private static final AtomicInteger LAST_LOADED = new AtomicInteger(Integer.MIN_VALUE);
    private static final AtomicReference<Thread> SAVE_THREAD = new AtomicReference<>();
    private static final Object SAVE_LOCK = new Object();

    private record LocationFields(Field type, Field path, Field isMod) {
    }

    private static final ClassValue<LocationFields> LOCATION_FIELDS = new ClassValue<>() {
        @Override
        protected LocationFields computeValue(Class<?> type) {
            return resolveLocationFields(type);
        }
    };

    private FileIndexHook() {
    }

    public static void setContext(RuntimeContext ctx) {
        context = ctx;
    }

    /**
     * FR builds this lever's assumptions into the injected {@code F_SAME} frame and
     * into the cached key normalization. Only the pinned 0.9.7 line is supported;
     * anything else disables the transformer before it can emit unverifiable bytecode.
     */
    static boolean supportedFrVersion() {
        return supportedFrVersion(frVersion());
    }

    static boolean supportedFrVersion(String version) {
        String v = normalizeFrVersion(version);
        return "0.9.7rc2".equals(v) || "0.9.7".equals(v);
    }

    static String normalizeFrVersion(String version) {
        if (version == null) return "unknown";
        String v = version.trim().toLowerCase(Locale.ROOT);
        if (v.startsWith("v")) v = v.substring(1).trim();
        return v.isEmpty() ? "unknown" : v;
    }

    /** {@code starsector-core/fr.version.txt} first, reflection second, else unknown. */
    static String frVersion() {
        RuntimeContext ctx = context;
        if (ctx != null) {
            Path file = ctx.gameRoot().resolve("starsector-core/fr.version.txt");
            try {
                if (Files.isRegularFile(file)) {
                    String raw = Files.readString(file).trim();
                    if (!raw.isEmpty()) return normalizeFrVersion(raw);
                }
            } catch (Throwable ignored) {
                // fail open: try reflection, then report unknown
            }
        }
        try {
            Class<?> cls = Class.forName(
                    "com.genir.renderer.Version", false, ClassLoader.getSystemClassLoader());
            Object value = cls.getMethod("getVersion").invoke(null);
            if (value != null) {
                String v = normalizeFrVersion(String.valueOf(value));
                if (!"unknown".equals(v)) return v;
            }
        } catch (Throwable ignored) {
            // FR absent or shape changed; unknown disables the lever
        }
        return "unknown";
    }

    /**
     * Stable fingerprint of the runtime shapes the transformer assumes: the
     * obfuscated location class, the resolved enum/String/boolean fields, and the
     * {@code FileHandle} constructor parameters. Any drift rejects the index.
     */
    static String shapeStamp(List<Object> locations, ClassLoader loader) {
        try {
            if (locations == null || locations.isEmpty()) return null;
            Class<?> locationClass = locations.get(0).getClass();
            LocationFields fields = LOCATION_FIELDS.get(locationClass);
            if (fields == null) return null;
            Constructor<?> ctor = fileHandleCtor(loader);
            if (ctor == null) return null;
            StringBuilder out = new StringBuilder(locationClass.getSimpleName());
            out.append('|').append(fieldSignature(fields.type()));
            out.append('|').append(fieldSignature(fields.path()));
            out.append('|').append(fieldSignature(fields.isMod()));
            out.append('|');
            Class<?>[] params = ctor.getParameterTypes();
            for (int i = 0; i < params.length; i++) {
                if (i > 0) out.append(',');
                out.append(params[i].getSimpleName());
            }
            return out.toString();
        } catch (Throwable t) {
            return null;
        }
    }

    private static String fieldSignature(Field field) {
        Class<?> type = field.getType();
        if (type.isEnum()) return "enum";
        if (type == String.class) return "String";
        if (type == boolean.class || type == Boolean.class) return "boolean";
        return type.getSimpleName();
    }

    static boolean enabled() {
        String prop = System.getProperty("hypernova.fileIndex");
        if (prop != null) return Boolean.parseBoolean(prop);
        RuntimeContext ctx = context;
        if (ctx == null) return true;
        Path cfg = ctx.gameRoot().resolve(
                "mods/hypernova_infinite_engine/data/config/hypernova/hypernova.json");
        if (!Files.isRegularFile(cfg)) return true;
        try {
            JSONObject root = new JSONObject(Files.readString(cfg));
            JSONObject section = root.optJSONObject("fileIndex");
            return section == null || section.optBoolean("enabled", true);
        } catch (Throwable t) {
            AgentLog.fail("file index config parse failed; enabled by default", t);
            return true;
        }
    }

    /** Returns the cached entry count, or -1 to let FR run its full crawl. */
    public static int tryLoad(Object crawler) {
        if (!enabled()) return -1;
        RuntimeContext ctx = context;
        if (ctx == null) return -1;
        try {
            Object outer = get(crawler, "this$0");
            if (outer == null) return -1;
            @SuppressWarnings("unchecked")
            Map<String, List<Object>> target = (Map<String, List<Object>>) get(outer, "cachedFiles");
            @SuppressWarnings("unchecked")
            List<Object> locations = (List<Object>) get(outer, "allLocations");
            if (target == null || locations == null || locations.isEmpty()) return -1;

            String frVersion = frVersion();
            if (!supportedFrVersion(frVersion)) {
                AgentLog.info("file index: unsupported FR version " + frVersion + "; full crawl");
                return -1;
            }
            String shapeStamp = shapeStamp(locations, outer.getClass().getClassLoader());
            if (shapeStamp == null) {
                AgentLog.info("file index: cannot resolve runtime shape; full crawl");
                return -1;
            }
            FileIndex index = FileIndex.read(indexFile(ctx), frVersion, shapeStamp);
            if (index == null) {
                AgentLog.info("file index: absent, corrupt, or FR version/shape mismatch; full crawl");
                return -1;
            }
            List<FileIndex.Location> current = locationKeys(locations);
            if (current == null || current.size() != index.locations().size()) return -1;

            Map<FileIndex.Location, Integer> stored = new HashMap<>();
            for (int i = 0; i < index.locations().size(); i++) {
                stored.put(index.locations().get(i), i);
            }
            int[] storedForCurrent = new int[current.size()];
            for (int i = 0; i < current.size(); i++) {
                Integer s = stored.get(current.get(i));
                if (s == null) return -1;
                storedForCurrent[i] = s;
            }

            String changed = index.firstMismatchedDir();
            if (changed != null) {
                AgentLog.info("file index: directory changed [" + changed + "]; full crawl");
                return -1;
            }
            Constructor<?> ctor = fileHandleCtor(outer.getClass().getClassLoader());
            if (ctor == null) return -1;

            Map<Integer, List<FileIndex.Entry>> cached = new HashMap<>();
            for (FileIndex.Entry entry : index.entries()) {
                cached.computeIfAbsent(entry.locationIndex(), k -> new ArrayList<>()).add(entry);
            }

            Map<String, List<Object>> loaded = new HashMap<>();
            int total = 0;
            for (int i = 0; i < locations.size(); i++) {
                Object location = locations.get(i);
                String type = typeName(location);
                if ("DIRECTORY".equals(type)) {
                    if (isExcluded(type, pathOf(location))) continue;
                    List<FileIndex.Entry> entries = cached.get(storedForCurrent[i]);
                    if (entries == null) {
                        total += crawlDirectory(location, loaded, ctor);
                    } else {
                        for (FileIndex.Entry entry : entries) {
                            if (!prefixOk(entry.filePath(), location)) return -1;
                            add(loaded, ctor, location, entry.key(), entry.filePath());
                            total++;
                        }
                    }
                } else if ("ABSOLUTE_AND_CWD".equals(type)) {
                    total += crawlAbsolute(location, loaded, ctor);
                }
                // CLASSPATH and unknown location types are not crawled by FR.
            }
            // An empty result means we cannot reproduce FR's enumeration: fail open.
            if (total == 0) return -1;
            target.clear();
            target.putAll(loaded);
            LOADED.add(crawler);
            LAST_LOADED.set(total);
            AgentLog.info("file index: loaded mod_entries=" + index.entries().size()
                    + ", total_entries=" + total + ", dirs=" + index.dirs().size()
                    + ", bytes=" + Files.size(indexFile(ctx)));
            return total;
        } catch (Throwable t) {
            AgentLog.fail("file index load failed; falling back to full crawl", t);
            return -1;
        }
    }

    /**
     * Schedules the index write on a daemon thread and returns immediately.
     *
     * <p>The snapshot is taken on the crawler thread: {@link Thread#start()}
     * publishes every write that happened before it (including the crawl's
     * {@code FileHandle} fields), and FR discards the crawler right after
     * {@code cacheLocations} returns. The payload is written to a {@code .tmp}
     * file and only renamed into place when complete, so a process that exits
     * early leaves either no index or a complete one; the next launch then
     * fail-opens to a full crawl.
     */
    public static void save(Object crawler, int count) {
        if (!enabled() || count <= 0 || LOADED.contains(crawler)) return;
        RuntimeContext ctx = context;
        if (ctx == null) return;
        try {
            Object outer = get(crawler, "this$0");
            if (outer == null) return;
            @SuppressWarnings("unchecked")
            List<Object> locations = (List<Object>) get(outer, "allLocations");
            @SuppressWarnings("unchecked")
            List<Object> collector = (List<Object>) get(crawler, "collector");
            if (locations == null || collector == null || locations.isEmpty()) return;
            String frVersion = frVersion();
            if (!supportedFrVersion(frVersion)) return;
            String shapeStamp = shapeStamp(locations, outer.getClass().getClassLoader());
            if (shapeStamp == null) {
                AgentLog.info("file index: cannot resolve runtime shape; index not saved");
                return;
            }
            List<FileIndex.Location> keys = locationKeys(locations);
            if (keys == null) return;

            // The injected call runs right before cacheLocations returns, so the
            // enumeration is complete; this timestamp bounds what the writer may
            // accept as an unchanged directory.
            long crawlEndMs = System.currentTimeMillis();
            Object[] items = collector.toArray();
            Object[] allLocations = locations.toArray();
            Path target = indexFile(ctx);

            Thread writer = new Thread(() -> {
                try {
                    writeIndex(frVersion, shapeStamp, keys, allLocations, items, target,
                            crawlEndMs);
                } finally {
                    SAVE_THREAD.compareAndSet(Thread.currentThread(), null);
                }
            }, "hypernova-file-index-writer");
            writer.setDaemon(true);
            writer.setPriority(Thread.MIN_PRIORITY);
            synchronized (SAVE_LOCK) {
                Thread previous = SAVE_THREAD.get();
                if (previous != null && previous.isAlive()) {
                    AgentLog.info("file index: save already in progress; skipping");
                    return;
                }
                SAVE_THREAD.set(writer);
            }
            AgentLog.info("file index: save scheduled entries=" + count);
            writer.start();
        } catch (Throwable t) {
            AgentLog.fail("file index save failed; next launch will crawl", t);
        }
    }

    /** Writes the snapshot; false means the index was not persisted. */
    static boolean writeIndex(String frVersion, String shapeStamp,
                              List<FileIndex.Location> keys, Object[] locations,
                              Object[] items, Path target, long crawlEndMs) {
        long start = System.currentTimeMillis();
        try {
            IdentityHashMap<Object, Integer> index = new IdentityHashMap<>();
            for (int i = 0; i < locations.length; i++) index.put(locations[i], i);
            List<FileIndex.Entry> entries = new ArrayList<>(Math.max(16, items.length));
            Set<String> dirs = new LinkedHashSet<>();
            for (Object item : items) {
                if (item instanceof List<?> list) {
                    for (Object handle : list) addSaved(handle, index, entries, dirs);
                } else {
                    addSaved(item, index, entries, dirs);
                }
            }
            for (FileIndex.Location location : keys) {
                if (!"DIRECTORY".equals(location.type())) continue;
                if (isExcluded(location.type(), location.path())) continue;
                File root = new File(location.path());
                if (root.isDirectory()) dirs.add(root.getPath());
            }
            List<FileIndex.Dir> dirList = captureDirs(dirs, crawlEndMs);
            if (dirList == null) return false;
            if (entries.isEmpty() && dirList.isEmpty()) return false;
            new FileIndex(frVersion, shapeStamp, keys, dirList, entries).write(target);
            AgentLog.info("file index: written entries=" + entries.size()
                    + ", dirs=" + dirList.size() + ", ms="
                    + (System.currentTimeMillis() - start));
            return true;
        } catch (Throwable t) {
            AgentLog.fail("file index save failed; next launch will crawl", t);
            return false;
        }
    }

    /**
     * Reads the recorded directory mtimes. Returns null when a directory
     * disappeared or was modified after the crawl finished: the enumeration
     * would then describe an older state than the timestamps, and a later cache
     * hit could hide the change. Aborting is fail-open (next launch crawls).
     */
    static List<FileIndex.Dir> captureDirs(Set<String> dirs, long crawlEndMs) {
        List<FileIndex.Dir> out = new ArrayList<>(dirs.size());
        for (String dir : dirs) {
            long mtime = new File(dir).lastModified();
            if (mtime == 0) {
                AgentLog.info("file index: save skipped; directory missing [" + dir + "]");
                return null;
            }
            if (mtime > crawlEndMs) {
                AgentLog.info("file index: save skipped; directory changed after crawl ["
                        + dir + "]");
                return null;
            }
            out.add(new FileIndex.Dir(dir, mtime));
        }
        return out;
    }

    /** Waits for the currently scheduled writer; exposed for the test fixture. */
    public static void awaitSavesForTest(long timeoutMs) {
        for (int i = 0; i < 10; i++) {
            Thread writer = SAVE_THREAD.get();
            if (writer == null) return;
            try {
                writer.join(timeoutMs);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            if (SAVE_THREAD.get() == writer) return;
        }
    }

    static int lastLoadedForTest() {
        return LAST_LOADED.get();
    }

    static void resetForTest() {
        awaitSavesForTest(30_000);
        LOADED.clear();
        LAST_LOADED.set(Integer.MIN_VALUE);
        context = null;
    }

    static List<FileIndex.Location> locationKeysForTest(List<Object> locations) {
        return locationKeys(locations);
    }

    static boolean isExcludedForTest(String type, String path) {
        return isExcluded(type, path);
    }

    private static LocationFields resolveLocationFields(Class<?> cls) {
        // 1) readable names (fixtures / un-obfuscated dev builds)
        try {
            Field type = cls.getDeclaredField("ResourceLocation_type");
            Field path = cls.getDeclaredField("ResourceLocation_path");
            Field isMod = cls.getDeclaredField("ResourceLocation_isMod");
            type.setAccessible(true);
            path.setAccessible(true);
            isMod.setAccessible(true);
            return new LocationFields(type, path, isMod);
        } catch (NoSuchFieldException ignored) {
            // fall through to shape
        }
        // 2) runtime shape: exactly one enum, one String, one boolean
        Field type = null;
        Field path = null;
        Field isMod = null;
        int enums = 0;
        int strings = 0;
        int bools = 0;
        for (Field field : cls.getDeclaredFields()) {
            if (Modifier.isStatic(field.getModifiers())) continue;
            Class<?> fieldType = field.getType();
            if (fieldType.isEnum()) {
                type = field;
                enums++;
            } else if (fieldType == String.class) {
                path = field;
                strings++;
            } else if (fieldType == boolean.class || fieldType == Boolean.class) {
                isMod = field;
                bools++;
            }
        }
        if (enums != 1 || strings != 1 || bools != 1) return null;
        type.setAccessible(true);
        path.setAccessible(true);
        isMod.setAccessible(true);
        return new LocationFields(type, path, isMod);
    }

    private static List<FileIndex.Location> locationKeys(List<Object> locations) {
        try {
            List<FileIndex.Location> out = new ArrayList<>(locations.size());
            for (Object location : locations) {
                LocationFields fields = LOCATION_FIELDS.get(location.getClass());
                if (fields == null) return null;
                Object type = fields.type().get(location);
                Object path = fields.path().get(location);
                Object isMod = fields.isMod().get(location);
                if (!(type instanceof Enum<?>)) return null;
                String typeName = String.valueOf(type);
                String pathName = path == null ? "" : String.valueOf(path);
                boolean mod = isMod instanceof Boolean b && b;
                out.add(new FileIndex.Location(typeName, pathName, mod));
            }
            return out;
        } catch (Throwable t) {
            return null;
        }
    }

    private static boolean isExcluded(String type, String path) {
        return "CLASSPATH".equals(type) || EXCLUDED_RESOURCE_PATH.equals(path);
    }

    private static String typeName(Object location) throws Exception {
        LocationFields fields = LOCATION_FIELDS.get(location.getClass());
        if (fields == null) throw new IllegalStateException("location shape not resolved");
        Object type = fields.type().get(location);
        if (!(type instanceof Enum<?>)) throw new IllegalStateException("type is not an enum");
        return String.valueOf(type);
    }

    private static String pathOf(Object location) throws Exception {
        LocationFields fields = LOCATION_FIELDS.get(location.getClass());
        if (fields == null) return "";
        Object path = fields.path().get(location);
        return path == null ? "" : String.valueOf(path);
    }

    private static String getLocationPath(Object location) {
        try {
            String type = typeName(location);
            if ("DIRECTORY".equals(type)) return pathOf(location);
            if ("ABSOLUTE_AND_CWD".equals(type)) return System.getProperty("user.dir", ".");
        } catch (Throwable ignored) {
            // fail open: unresolved locations are excluded from keyed replay
        }
        return "";
    }

    private static void addSaved(Object handle, IdentityHashMap<Object, Integer> index,
                                 List<FileIndex.Entry> entries, Set<String> dirs) {
        try {
            Object location = get(handle, "location");
            String type = typeName(location);
            String path = pathOf(location);
            if (!"DIRECTORY".equals(type) || isExcluded(type, path)) return;
            File file = (File) get(handle, "file");
            Integer locationIndex = index.get(location);
            if (file == null || locationIndex == null) return;
            // FR enumerates directories as handles too. Recording each directory's
            // own path is what makes a directory that was EMPTY at build time
            // invalidate the index when a file appears inside it later (its
            // parent's mtime does not change in that case).
            if (file.isDirectory()) dirs.add(file.getPath());
            String key = keyFor(file, location);
            if (key.isEmpty()) return;
            entries.add(new FileIndex.Entry(key, file.getPath(), locationIndex));
            File parent = file.getParentFile();
            if (parent != null) dirs.add(parent.getPath());
        } catch (Throwable ignored) {
            // One bad handle must not abort the whole index.
        }
    }

    private static int crawlDirectory(Object location, Map<String, List<Object>> loaded,
                                      Constructor<?> ctor) throws Exception {
        String path = pathOf(location);
        if (path.isEmpty()) return 0;
        // FR enumerates Path.of(locationPath).toAbsolutePath(), not the raw path.
        return walk(Path.of(path).toAbsolutePath().toFile(), location, loaded, ctor);
    }

    private static int crawlAbsolute(Object location, Map<String, List<Object>> loaded,
                                     Constructor<?> ctor) throws Exception {
        String pwd = System.getProperty("user.dir", ".");
        String saves = System.getProperty("com.fs.starfarer.settings.paths.saves", "../saves");
        String mods = System.getProperty("com.fs.starfarer.settings.paths.mods", "../mods");
        Path base = Path.of(pwd).toAbsolutePath();
        int total = 0;
        total += walk(base.toFile(), location, loaded, ctor);
        total += walk(base.resolve(saves).toFile(), location, loaded, ctor);
        total += walk(base.resolve(mods).resolve("enabled_mods.json").toFile(),
                location, loaded, ctor);
        total += walk(base.resolve("..").resolve("mikohime").toFile(),
                location, loaded, ctor);
        return total;
    }

    private static int walk(File file, Object location, Map<String, List<Object>> loaded,
                            Constructor<?> ctor) throws Exception {
        int total = 1;
        add(loaded, ctor, location, keyFor(file, location), file.getPath());
        File[] children = file.listFiles();
        if (children != null) {
            for (File child : children) total += walk(child, location, loaded, ctor);
        }
        return total;
    }

    private static void add(Map<String, List<Object>> target, Constructor<?> ctor,
                            Object location, String key, String path) throws Exception {
        if (key == null || key.isEmpty()) return;
        target.computeIfAbsent(key, k -> new ArrayList<>())
                .add(ctor.newInstance(new File(path), location));
    }

    /** Mirrors FR's saveFile key computation exactly. */
    private static String keyFor(File file, Object location) {
        String locationPath = getLocationPath(location);
        if (locationPath.isEmpty()) return "";
        String base = Path.of(locationPath).toAbsolutePath().toString();
        return normalize(file.getPath().replace(base, ""));
    }

    private static String normalize(String path) {
        if (path == null) return "";
        if (path.startsWith("/")) path = path.substring(1);
        if (path.startsWith("\\")) path = path.substring(1);
        path = path.trim();
        path = Path.of(path).normalize().toString().replace("\\", "/");
        if (path.endsWith("/")) path = path.substring(0, path.length() - 1);
        if (path.endsWith(".")) path = path.substring(0, path.length() - 1);
        return path.toLowerCase(Locale.ROOT);
    }

    private static Path indexFile(RuntimeContext ctx) {
        return ctx.cacheRoot().getParent().resolve("file-index.idx.gz");
    }

    private static Object get(Object target, String name) {
        try {
            Field field = target.getClass().getDeclaredField(name);
            field.setAccessible(true);
            return field.get(target);
        } catch (NoSuchFieldException e) {
            throw new IllegalStateException("field not found: " + name, e);
        } catch (ReflectiveOperationException e) {
            throw new IllegalStateException("field access failed: " + name, e);
        }
    }

    private static Constructor<?> fileHandleCtor(ClassLoader preferred) {
        // FR and the game are normally on the system classpath, but the test runner
        // (and some launchers) load classes through a child loader. Try the loader
        // that owns FileLoaderFast first, then the context/system loaders.
        ClassLoader context = Thread.currentThread().getContextClassLoader();
        for (ClassLoader loader : new ClassLoader[]{
                preferred, context, ClassLoader.getSystemClassLoader()}) {
            if (loader == null) continue;
            try {
                Class<?> cls = Class.forName(FH_CLASS, false, loader);
                for (Constructor<?> ctor : cls.getConstructors()) {
                    Class<?>[] params = ctor.getParameterTypes();
                    if (params.length == 2 && params[0] == File.class) return ctor;
                }
            } catch (Throwable ignored) {
                // try the next loader; FR missing or class shape changed: fail open.
            }
        }
        return null;
    }

    private static boolean prefixOk(String filePath, Object location) {
        try {
            String base = pathOf(location);
            if (base.isBlank()) return true;
            Path file = Path.of(filePath).toAbsolutePath().normalize();
            Path root = Path.of(base).toAbsolutePath().normalize();
            return file.startsWith(root);
        } catch (Throwable t) {
            return false;
        }
    }
}
