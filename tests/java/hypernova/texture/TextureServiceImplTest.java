package hypernova.texture;

import hypernova.manifest.Layer;
import hypernova.manifest.TextureEntry;
import hypernova.manifest.TextureManifest;
import hypernova.telemetry.Telemetry;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;

import static org.junit.jupiter.api.Assertions.*;

class TextureServiceImplTest {

    static final class FakeBackend implements TextureBackend {
        final Set<String> registered = new HashSet<>();
        final List<String> calls = new ArrayList<>();
        int failuresLeft;
        long sleepMillis;

        @Override
        public boolean isRegistered(String path) {
            return registered.contains(path);
        }

        @Override
        public void load(String path) throws Exception {
            calls.add(path);
            if (sleepMillis > 0) {
                Thread.sleep(sleepMillis);
            }
            if (failuresLeft > 0) {
                failuresLeft--;
                throw new java.io.IOException("boom");
            }
            registered.add(path);
        }
    }

    static final class RecordingTelemetry implements Telemetry {
        final List<String> events = new ArrayList<>();

        @Override
        public void event(String kind, String path, long nanos, String detail) {
            events.add(kind + "|" + path + "|" + detail);
        }

        @Override
        public void flush() {
        }

        @Override
        public int buffered() {
            return events.size();
        }
    }

    // json.jar 是 2010 版 org.json，put(...) 抛受检 JSONException，故辅助方法显式声明 throws。
    private static TextureManifest manifestWith(String... paths) throws JSONException {
        JSONObject root = new JSONObject();
        JSONObject layers = new JSONObject();
        JSONArray l1 = new JSONArray();
        for (String p : paths) {
            JSONObject e = new JSONObject();
            e.put("path", p);
            e.put("modId", "m");
            e.put("w", 1);
            e.put("h", 1);
            e.put("baked", true);
            l1.put(e);
        }
        layers.put("L1", l1);
        layers.put("L2", new JSONArray());
        layers.put("L3", new JSONArray());
        root.put("layers", layers);
        return TextureManifest.fromJson(root);
    }

    private static TextureServiceImpl service(TextureManifest m, TextureBackend b, Telemetry t,
                                             AtomicBoolean loadingSave) {
        return new TextureServiceImpl(m, b, t, Thread.currentThread(), loadingSave::get);
    }

    @Test
    void loadsPathInManifest() throws JSONException {
        FakeBackend b = new FakeBackend();
        RecordingTelemetry t = new RecordingTelemetry();
        TextureServiceImpl s = service(manifestWith("a.png"), b, t, new AtomicBoolean(false));
        TextureLoadResult r = s.ensureLoaded("a.png");
        assertTrue(r.ok());
        assertFalse(r.queued());
        assertEquals(TextureState.LIVE, r.state());
        assertEquals(List.of("a.png"), b.calls);
        assertTrue(t.events.stream().anyMatch(e -> e.startsWith("loaded|a.png|")));
    }

    @Test
    void unknownPathDoesNotLoad() throws JSONException {
        FakeBackend b = new FakeBackend();
        RecordingTelemetry t = new RecordingTelemetry();
        TextureServiceImpl s = service(manifestWith("a.png"), b, t, new AtomicBoolean(false));
        TextureLoadResult r = s.ensureLoaded("nope.png");
        assertFalse(r.ok());
        assertEquals(TextureState.MISS, r.state());
        assertTrue(b.calls.isEmpty());
    }

    @Test
    void alreadyRegisteredSkipsBackend() throws JSONException {
        FakeBackend b = new FakeBackend();
        b.registered.add("a.png");
        RecordingTelemetry t = new RecordingTelemetry();
        TextureServiceImpl s = service(manifestWith("a.png"), b, t, new AtomicBoolean(false));
        TextureLoadResult r = s.ensureLoaded("a.png");
        assertTrue(r.ok());
        assertTrue(b.calls.isEmpty());
        assertTrue(t.events.stream().anyMatch(e -> e.startsWith("hit|a.png|")));
    }

    @Test
    void failureIsRetriedOnceThenFailed() throws JSONException {
        FakeBackend b = new FakeBackend();
        b.failuresLeft = 5;
        RecordingTelemetry t = new RecordingTelemetry();
        TextureServiceImpl s = service(manifestWith("a.png"), b, t, new AtomicBoolean(false));
        TextureLoadResult r = s.ensureLoaded("a.png");
        assertFalse(r.ok());
        assertEquals(TextureState.FAILED, r.state());
        assertEquals(2, b.calls.size());
        assertTrue(t.events.stream().anyMatch(e -> e.startsWith("failed|a.png|")));
    }

    @Test
    void failureThenSuccessOnRetry() throws JSONException {
        FakeBackend b = new FakeBackend();
        b.failuresLeft = 1;
        RecordingTelemetry t = new RecordingTelemetry();
        TextureServiceImpl s = service(manifestWith("a.png"), b, t, new AtomicBoolean(false));
        TextureLoadResult r = s.ensureLoaded("a.png");
        assertTrue(r.ok());
        assertEquals(2, b.calls.size());
    }

    @Test
    void loadingSaveQueuesWithoutLoading() throws JSONException {
        FakeBackend b = new FakeBackend();
        RecordingTelemetry t = new RecordingTelemetry();
        AtomicBoolean loading = new AtomicBoolean(true);
        TextureServiceImpl s = service(manifestWith("a.png"), b, t, loading);
        TextureLoadResult r = s.ensureLoaded("a.png");
        assertTrue(r.queued());
        assertFalse(r.ok());
        assertTrue(b.calls.isEmpty());
        assertEquals(1, s.pendingCount());
        assertTrue(t.events.stream().noneMatch(e -> e.startsWith("loaded|")));
    }

    @Test
    void drainPendingOnlyAfterWindowCloses() throws JSONException {
        FakeBackend b = new FakeBackend();
        RecordingTelemetry t = new RecordingTelemetry();
        AtomicBoolean loading = new AtomicBoolean(true);
        TextureServiceImpl s = service(manifestWith("a.png", "b.png"), b, t, loading);
        s.ensureLoaded("a.png");
        s.ensureLoaded("b.png");
        assertEquals(List.of(), s.drainPending(10));
        loading.set(false);
        assertEquals(List.of("a.png", "b.png"), s.drainPending(10));
        assertEquals(0, s.pendingCount());
    }

    @Test
    void nonMainThreadThrows() throws Exception {
        FakeBackend b = new FakeBackend();
        RecordingTelemetry t = new RecordingTelemetry();
        TextureServiceImpl s = service(manifestWith("a.png"), b, t, new AtomicBoolean(false));
        Throwable[] caught = new Throwable[1];
        Thread worker = new Thread(() -> {
            try {
                s.ensureLoaded("a.png");
            } catch (Throwable e) {
                caught[0] = e;
            }
        });
        worker.start();
        worker.join();
        assertInstanceOf(IllegalStateException.class, caught[0]);
    }

    @Test
    void unloadRefusedWhenEvictionDisabled() throws JSONException {
        FakeBackend b = new FakeBackend();
        RecordingTelemetry t = new RecordingTelemetry();
        TextureServiceImpl s = service(manifestWith("a.png"), b, t, new AtomicBoolean(false));
        s.ensureLoaded("a.png");
        assertFalse(s.unload("a.png"));
        assertTrue(t.events.stream().anyMatch(e -> e.startsWith("refused|a.png|eviction-disabled")));
    }

    @Test
    void acquireReleaseCounts() throws JSONException {
        FakeBackend b = new FakeBackend();
        RecordingTelemetry t = new RecordingTelemetry();
        TextureServiceImpl s = service(manifestWith("a.png"), b, t, new AtomicBoolean(false));
        s.ensureLoaded("a.png");
        assertTrue(s.acquire("a.png"));
        s.release("a.png");
    }
}
