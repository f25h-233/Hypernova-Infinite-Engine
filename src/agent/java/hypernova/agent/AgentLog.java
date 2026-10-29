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
        // 日志可能从 transformer 注入的游戏类加载路径调用：任何异常
        // （SecurityException、OOM、Error）都绝不能外抛，整个方法体兜住。
        try {
            StringBuilder sb = new StringBuilder();
            sb.append(Instant.now()).append(' ').append(level).append(' ').append(msg);
            if (t != null) {
                StringWriter sw = new StringWriter();
                t.printStackTrace(new PrintWriter(sw));
                sb.append('\n').append(sw);
            }
            sb.append('\n');
            try {
                System.err.print(sb);
            } catch (Throwable ignored) {
                // 控制台写失败不影响继续落盘
            }
            Path f = file;
            if (f == null) return;
            try {
                Files.writeString(f, sb.toString(), StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            } catch (Throwable ignored) {
                // agent 日志失败不能影响游戏
            }
        } catch (Throwable ignored) {
            // 连格式化/时间戳都失败时也只能吞掉
        }
    }
}
