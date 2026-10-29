package hypernova.agent;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;

public final class KeyManifest {
    public record Entry(String path, long size, long mtime, String sha256) {
    }

    private final Map<String, Entry> byPath = new HashMap<>();

    public static KeyManifest load(Path file) {
        KeyManifest manifest = new KeyManifest();
        if (!Files.isRegularFile(file)) return manifest;
        try {
            JSONArray array = new JSONArray(Files.readString(file));
            for (int i = 0; i < array.length(); i++) {
                JSONObject o = array.getJSONObject(i);
                Entry e = new Entry(o.getString("path"), o.getLong("size"),
                        o.getLong("mtime"), o.getString("sha256"));
                manifest.byPath.put(e.path(), e);
            }
        } catch (Throwable t) {
            AgentLog.fail("key manifest load failed; rebuilding", t);
        }
        return manifest;
    }

    public List<Entry> refresh(List<Path> files) {
        List<Entry> out = new ArrayList<>(files.size());
        for (Path p : files) {
            try {
                String path = p.toString();
                long size = Files.size(p);
                long mtime = Files.getLastModifiedTime(p).toMillis();
                Entry prev = byPath.get(path);
                String hash = (prev != null && prev.size() == size && prev.mtime() == mtime)
                        ? prev.sha256() : sha256(p);
                out.add(new Entry(path, size, mtime, hash));
            } catch (IOException e) {
                AgentLog.fail("stat failed: " + p, e);
            }
        }
        byPath.clear();
        for (Entry e : out) byPath.put(e.path(), e);
        return out;
    }

    public void save(Path file) throws IOException {
        JSONArray array = new JSONArray();
        try {
            for (Entry e : byPath.values()) {
                JSONObject o = new JSONObject();
                o.put("path", e.path());
                o.put("size", e.size());
                o.put("mtime", e.mtime());
                o.put("sha256", e.sha256());
                array.put(o);
            }
        } catch (JSONException e) {
            // 游戏自带 json.jar 是 2010 版 org.json：JSONException 为 checked。
            throw new IOException("key manifest encode failed", e);
        }
        Files.createDirectories(file.getParent());
        Path tmp = file.resolveSibling(file.getFileName() + ".tmp");
        Files.writeString(tmp, array.toString(), StandardCharsets.UTF_8);
        Files.move(tmp, file, StandardCopyOption.REPLACE_EXISTING,
                StandardCopyOption.ATOMIC_MOVE);
    }

    private static String sha256(Path path) throws IOException {
        try (InputStream in = Files.newInputStream(path)) {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) > 0) md.update(buf, 0, n);
            return HexFormat.of().formatHex(md.digest());
        } catch (NoSuchAlgorithmException e) {
            throw new IOException(e);
        }
    }
}
