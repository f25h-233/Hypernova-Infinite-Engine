package hypernova.telemetry;

import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;

/**
 * JSONL 遥测。
 *
 * <p>落盘语义：{@code writeTextFileToCommon} 是**整文件覆盖写**，不是 append。
 * 因此每次 flush 都把「本次会话已写出的全部行 + 本批新行」一起写下去（I4），
 * 否则磁盘上只剩最后一批事件，30 分钟观测与 P99 采样都无法重建。
 *
 * <p>内存上限：写出历史按行数（{@value #MAX_WRITTEN_LINES}）与字符数
 * （{@value #MAX_WRITTEN_CHARS}，留出引擎单次写入 1 MB 上限的余量）双封顶；
 * 超限时丢弃最旧的一半，并补一条 {@code kind="telemetry-truncated"} 说明丢了什么。
 *
 * <p>nanos 口径（按 kind 区分，不可横向比较）：
 * <ul>
 *   <li>{@code hit} / {@code miss} / {@code queued} / {@code rejected}：manifest 查表与状态判定耗时；</li>
 *   <li>{@code loaded} / {@code failed}：单次 backend.load 尝试耗时（REQ-R1-03 的 P99 取 loaded）；</li>
 *   <li>{@code telemetry-truncated}：固定 0。</li>
 * </ul>
 */
public final class JsonlTelemetry implements Telemetry {
    public static final String NAME = "hypernova/telemetry.jsonl";
    private static final int MAX_PATH_CHARS = 1024;
    /** 单次落盘允许的最大行数（会话累计）。 */
    static final int MAX_WRITTEN_LINES = 50_000;
    /** 单次落盘的字符预算：引擎 writeTextFileToCommon 单次写入上限约 1 MB。 */
    static final int MAX_WRITTEN_CHARS = 900_000;

    private final TelemetrySink sink;
    private final int maxLines;
    private final Deque<String> lines = new ArrayDeque<>();
    /** 本次会话已经（或即将）落盘的全部行，flush 时整份重写。 */
    private final List<String> written = new ArrayList<>();
    private long writtenChars;
    private long droppedLines;

    public JsonlTelemetry(TelemetrySink sink, int maxLines) {
        this.sink = sink;
        this.maxLines = Math.max(1, maxLines);
    }

    @Override
    public void event(String kind, String path, long nanos, String detail) {
        String line = format(kind, path, nanos, detail);
        if (line == null) {
            return; // 遥测失败绝不打断游戏（INV-05 的失败方向：静默）
        }
        synchronized (lines) {
            if (lines.size() >= maxLines) {
                int drop = Math.max(1, maxLines / 2);
                for (int i = 0; i < drop && !lines.isEmpty(); i++) {
                    lines.pollFirst();
                }
            }
            lines.addLast(line);
        }
    }

    private String format(String kind, String path, long nanos, String detail) {
        JSONObject o = new JSONObject();
        try {
            o.put("t", System.currentTimeMillis());
            o.put("kind", kind);
            o.put("path", truncate(path));
            o.put("nanos", nanos);
            o.put("thread", Thread.currentThread().getName());
            o.put("detail", detail == null ? "" : truncate(detail));
            return o.toString();
        } catch (JSONException ignored) {
            return null;
        }
    }

    private static String truncate(String s) {
        if (s == null) {
            return "";
        }
        return s.length() <= MAX_PATH_CHARS ? s : s.substring(0, MAX_PATH_CHARS);
    }

    @Override
    public void flush() {
        List<String> out;
        long dropped;
        synchronized (lines) {
            if (lines.isEmpty()) {
                com.fs.starfarer.api.Global.getLogger(JsonlTelemetry.class)
                        .info("telemetry flush: buffer empty, nothing to write");
                return;
            }
            synchronized (written) {
                while (!lines.isEmpty()) {
                    String line = lines.pollFirst();
                    written.add(line);
                    writtenChars += line.length() + 1;
                }
                trimIfNeeded();
                out = new ArrayList<>(written);
                dropped = droppedLines;
            }
        }
        try {
            sink.write(NAME, String.join("\n", out) + "\n");
            com.fs.starfarer.api.Global.getLogger(JsonlTelemetry.class)
                    .info("telemetry flush: wrote " + out.size() + " lines (dropped=" + dropped
                            + ") to " + NAME);
        } catch (Exception e) {
            com.fs.starfarer.api.Global.getLogger(JsonlTelemetry.class)
                    .error("telemetry flush failed: " + NAME, e);
        }
    }

    /** 行数或字符数超限时丢最旧的一半，并留一条 truncated 说明（计入本次输出）。 */
    private void trimIfNeeded() {
        while (written.size() > MAX_WRITTEN_LINES || writtenChars > MAX_WRITTEN_CHARS) {
            int drop = Math.max(1, written.size() / 2);
            for (int i = 0; i < drop && !written.isEmpty(); i++) {
                writtenChars -= written.remove(0).length() + 1;
            }
            droppedLines += drop;
            String note = format("telemetry-truncated", "", 0L, "dropped=" + droppedLines);
            if (note != null) {
                written.add(note);
                writtenChars += note.length() + 1;
            }
            if (written.size() <= 1) {
                break; // 只剩说明行时不再循环（防御性，正常不会触发）
            }
        }
    }

    @Override
    public int buffered() {
        synchronized (lines) {
            return lines.size();
        }
    }

    /** 诊断用：本次会话已写出（或待写出）的总行数。 */
    public int writtenTotal() {
        synchronized (written) {
            return written.size();
        }
    }

    /** 诊断用：因超限而被丢弃的累计行数。 */
    public long droppedTotal() {
        synchronized (written) {
            return droppedLines;
        }
    }
}
