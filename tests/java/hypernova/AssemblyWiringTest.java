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
    void heartbeatFrequencyIsConfigurable() throws Exception {
        // Minor：verbose 死开关改为 heartbeat_frames。
        String src = read(COMBAT);
        assertTrue(src.contains("heartbeatFrames"), "心跳频率必须可配置");
        assertFalse(src.contains("tickCount % 3000"), "硬编码 3000 帧已被配置项取代");
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

    @Test
    void mainThreadIsBoundFromGameEntrypointsNotApplicationLoad() throws Exception {
        String plugin = read(PLUGIN);
        // FR 0.9.7 moved onApplicationLoad to Thread-N-FR-Main-Loader.
        assertFalse(plugin.contains("Thread.currentThread(), () -> Global.LOADING_SAVE"),
                "TextureServiceImpl must not capture onApplicationLoad's thread");
        assertTrue(plugin.contains("bindMainThread(\"onGameLoad\")"),
                "onGameLoad must bind the main thread");
        assertTrue(plugin.contains("bindMainThread(\"onNewGame\")"),
                "onNewGame must bind the main thread");
        String combat = read(COMBAT);
        assertTrue(combat.contains("bindMainThread(Thread.currentThread())"),
                "first advance must bind the main thread");
        assertTrue(combat.contains("sharedStartupSelfCheck"),
                "the one-shot self-check must run on the main thread");
    }

    @Test
    void frameProbeRunsAfterGateAndOnlyWhenPresent() throws Exception {
        String src = read(COMBAT);
        int completed = src.indexOf("GATE.completed(");
        int probe = src.indexOf("probe.frame(");
        assertTrue(completed > 0 && probe > completed,
                "frame probe 必须在 GATE.completed 之后采样");
        assertTrue(src.contains("FrameTimeProbe probe = frameProbe;"),
                "关闭时必须只做一次 null 检查");
        assertTrue(src.contains(".info(frameLine)"),
                "探针行必须写入游戏日志");
        assertTrue(read(PLUGIN).contains("Boolean.getBoolean(\"hypernova.frameProbe\")"),
                "frame probe 必须默认关闭、用 -Dhypernova.frameProbe=true 开启");
        assertTrue(read(PLUGIN).contains("new FrameTimeProbe(FRAME_PROBE_LOG_FRAMES)"),
                "探针构造必须只在属性开启时发生");
    }

    @Test
    void frameProbePropertyDefaultsOff() {
        String old = System.getProperty("hypernova.frameProbe");
        try {
            System.clearProperty("hypernova.frameProbe");
            assertFalse(HypernovaPlugin.frameProbeEnabled());
            System.setProperty("hypernova.frameProbe", "true");
            assertTrue(HypernovaPlugin.frameProbeEnabled());
        } finally {
            if (old == null) {
                System.clearProperty("hypernova.frameProbe");
            } else {
                System.setProperty("hypernova.frameProbe", old);
            }
        }
    }
}
