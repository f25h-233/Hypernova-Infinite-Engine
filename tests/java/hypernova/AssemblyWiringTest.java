package hypernova;

import org.junit.jupiter.api.Test;
import java.nio.file.Files;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;

/** 装配级接线守护：这些漏了单测不会红，但功能会静默失效（R-13 类缺陷）。 */
class AssemblyWiringTest {

    // 测试由 run-tests.sh 从仓库根启动（脚本先 cd 到根），故相对路径稳定。
    private static final Path PLUGIN = Path.of("src/main/java/hypernova/HypernovaPlugin.java");
    private static final Path COMBAT = Path.of("src/main/java/hypernova/adapter/HypernovaCombatPlugin.java");

    private static String read(Path p) throws Exception {
        return Files.readString(p);
    }

    @Test
    void schedulerReceivesManifestFilter() throws Exception {
        assertTrue(read(PLUGIN).contains("manifest::contains"),
                "FrameBudgetScheduler 必须收到 manifest::contains，4 参构造器会静默关闭过滤");
    }

    @Test
    void combatPluginTicksWarmupAndFlushesTelemetry() throws Exception {
        String src = read(COMBAT);
        assertTrue(src.contains("warmupHook.tick()"), "触发点⑤ 未接线");
        assertTrue(src.contains("telemetry.flush()"), "遥测永不落盘");
    }

    @Test
    void battleEndResetsDeploymentHook() throws Exception {
        String listener = Files.readString(Path.of("src/main/java/hypernova/adapter/HypernovaCampaignListener.java"));
        assertTrue(listener.contains("onBattleEnded()"), "第二场战斗不再触发 L1 预取");
    }
}
