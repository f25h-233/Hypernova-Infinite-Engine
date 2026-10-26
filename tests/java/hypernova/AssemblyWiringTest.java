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
    void installHappensAfterActiveTrueAndRollsBackOnFailure() throws Exception {
        // I2 / INV-05：catch 必须清空静态槽位，且 install() 不得早于 active = true 之前的
        // 失败窗口。这里用源码顺序做静态守护（运行期依赖 Global，单测无法执行）。
        String src = read(PLUGIN);
        int activeTrue = src.indexOf("active = true;");
        int install = src.indexOf("HypernovaCombatPlugin.install(poller");
        int rollback = src.indexOf("HypernovaCombatPlugin.install(null");
        assertTrue(activeTrue > 0 && install > 0 && rollback > 0, "装配/回滚调用必须存在");
        assertTrue(install > activeTrue, "install() 必须在 active = true 之后");
        assertTrue(rollback > install, "catch 里的 install(null,...) 必须在 install() 之后");
    }

    @Test
    void combatPluginGuardsDoubleAdvance() throws Exception {
        // I1：双入口（transient script + combat plugin）必须走共享门闩。
        String src = read(COMBAT);
        assertTrue(src.contains("GATE.shouldRun("), "缺少同帧幂等门闩");
        assertTrue(src.contains("GATE.completed("), "门闩未登记 tick 计数");
    }

    @Test
    void contactDialogIsTheRealTriggerPointTwo() throws Exception {
        // I6：触发点②接的是 contactDialogOpen，不是 codexOpen。
        String src = Files.readString(Path.of("src/main/java/hypernova/adapter/TriggerPoller.java"));
        assertTrue(src.contains("world.contactDialogOpen()"), "触发点②未接线到接触对话框");
        assertTrue(src.contains("contactDialogFleetName()"), "未按 dialog target 舰队预取");
    }

    @Test
    void saveLoadGuardReceivesAFrameBudget() throws Exception {
        String src = read(PLUGIN);
        assertTrue(src.contains("config.frameBudgetMicros() * 1_000L"),
                "SaveLoadGuard 必须收到与调度器一致的帧预算（I3）");
    }

    @Test
    void battleEndResetsDeploymentHook() throws Exception {
        String listener = Files.readString(Path.of("src/main/java/hypernova/adapter/HypernovaCampaignListener.java"));
        assertTrue(listener.contains("onBattleEnded()"), "第二场战斗不再触发 L1 预取");
    }
}
