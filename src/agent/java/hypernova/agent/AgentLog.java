package hypernova.agent;

import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;

public final class AgentLog {
    private static volatile Path file;

    private AgentLog() {
    }

    public static void init(Path path) {
        file = path;
        try {
            if (path != null && path.getParent() != null) Files.createDirectories(path.getParent());
        } catch (IOException e) {
            System.err.println("hypernova-agent: cannot create log dir: " + e);
        }
    }

    public static void info(String msg) {
        write("INFO", msg, null);
    }

    public static void fail(String msg, Throwable t) {
        write("ERROR", msg, t);
    }

    private static synchronized void write(String level, String msg, Throwable t) {
        StringBuilder sb = new StringBuilder();
        sb.append(Instant.now()).append(' ').append(level).append(' ').append(msg);
        if (t != null) {
            StringWriter sw = new StringWriter();
            t.printStackTrace(new PrintWriter(sw));
            sb.append('\n').append(sw);
        }
        sb.append('\n');
        System.err.print(sb);
        Path f = file;
        if (f == null) return;
        try {
            Files.writeString(f, sb.toString(), StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        } catch (IOException ignored) {
            // agent 日志失败不能影响游戏
        }
    }
}
