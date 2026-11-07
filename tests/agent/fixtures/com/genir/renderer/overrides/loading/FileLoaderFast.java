package com.genir.renderer.overrides.loading;

import com.fs.util.FileLoader;
import hypernova.agent.FileIndexHook;

import java.io.File;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/** Test fixture with both FR 0.9.7 (nested) and 0.9.8 (top-level) handle shapes. */
public class FileLoaderFast {
    private final List<FileLoader.ResourceLocation> allLocations;
    private final Map<String, List<Object>> cachedFiles = new HashMap<>();

    public FileLoaderFast(List<FileLoader.ResourceLocation> allLocations) {
        this.allLocations = allLocations;
    }

    public int crawl() {
        return new DirectoryCrawler().cacheLocations();
    }

    /** Runs the 0.9.7-shaped crawl and saves on the same crawler instance. */
    public int crawlAndSave() {
        DirectoryCrawler crawler = new DirectoryCrawler();
        int count = crawler.cacheLocations();
        FileIndexHook.save(crawler, count);
        FileIndexHook.awaitSavesForTest(30_000);
        return count;
    }

    /** Runs the 0.9.8-shaped crawl and saves on the same crawler instance. */
    public int crawlAndSave098() {
        DirectoryCrawler crawler = new DirectoryCrawler(true);
        int count = crawler.cacheLocations();
        FileIndexHook.save(crawler, count);
        FileIndexHook.awaitSavesForTest(30_000);
        return count;
    }

    /** Runs the 0.9.8-shaped crawl without saving (for tryLoad tests). */
    public int crawl098() {
        return new DirectoryCrawler(true).cacheLocations();
    }

    private String getLocationPath(FileLoader.ResourceLocation location) {
        String type = location.ResourceLocation_type.toString();
        if ("DIRECTORY".equals(type)) return location.ResourceLocation_path;
        if ("ABSOLUTE_AND_CWD".equals(type)) return System.getProperty("user.dir", ".");
        return null;
    }

    private boolean isExcludedLocation(FileLoader.ResourceLocation location) {
        return "CLASSPATH".equals(location.ResourceLocation_type.toString())
                || "../starfarer.res/res".equals(location.ResourceLocation_path);
    }

    private String normalize(String path) {
        if (path == null) return "";
        if (path.startsWith("/")) path = path.substring(1);
        if (path.startsWith("\\")) path = path.substring(1);
        path = path.trim();
        path = Paths.get(path).normalize().toString().replace("\\", "/");
        if (path.endsWith("/")) path = path.substring(0, path.length() - 1);
        if (path.endsWith(".")) path = path.substring(0, path.length() - 1);
        return path.toLowerCase(Locale.ROOT);
    }

    private final class DirectoryCrawler {
        private final List<Object> collector = new ArrayList<>();
        private final boolean topLevel;

        private DirectoryCrawler() {
            this(false);
        }

        private DirectoryCrawler(boolean topLevel) {
            this.topLevel = topLevel;
        }

        private int cacheLocations() {
            for (FileLoader.ResourceLocation location : allLocations) {
                if (isExcludedLocation(location)) continue;
                walk(new File(getLocationPath(location)), location);
            }
            int count = 0;
            for (Object item : collector) {
                if (item instanceof List<?> list) {
                    for (Object handle : list) {
                        saveFile(handle);
                        count++;
                    }
                } else {
                    saveFile(item);
                    count++;
                }
            }
            return count;
        }

        private void walk(File file, FileLoader.ResourceLocation location) {
            collector.add(topLevel
                    ? new ResourceHandle(file, location, "")
                    : new ResourceHandle.FileHandle(file, location));
            File[] children = file.listFiles();
            if (children != null) {
                for (File child : children) walk(child, location);
            }
        }

        private void saveFile(Object handle) {
            File file;
            FileLoader.ResourceLocation location;
            if (handle instanceof ResourceHandle h) {
                file = h.file;
                location = h.location;
            } else if (handle instanceof ResourceHandle.FileHandle h) {
                file = h.file;
                location = h.location;
            } else {
                return;
            }
            String locationPath = new File(getLocationPath(location)).getAbsolutePath();
            String key = normalize(file.getPath().replace(locationPath, ""));
            if (key.isEmpty()) return;
            cachedFiles.computeIfAbsent(key, k -> new ArrayList<>()).add(handle);
        }
    }
}
