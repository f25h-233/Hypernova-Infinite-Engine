package hypernova.agent;

import hypernova.agent.textures.TextureCacheTransformer;
import hypernova.agent.textures.TexturePatchConfig;

import java.lang.instrument.Instrumentation;

public final class HypernovaAgent {
    private HypernovaAgent() {
    }

    public static void premain(String args, Instrumentation instrumentation) {
        try {
            RuntimeContext ctx = RuntimeContext.fromEnvironment();
            AgentLog.init(ctx.logFile());
            AgentLog.info("hypernova agent premain; config=" + ctx.config()
                    + ", cacheRoot=" + ctx.cacheRoot());
            try {
                TexturePatchConfig textures = TexturePatchConfig.load();
                if (textures.enabled()) {
                    TextureCacheTransformer transformer = TextureCacheTransformer.create();
                    if (transformer != null) {
                        instrumentation.addTransformer(transformer, false);
                        AgentLog.info("textures normal-cache transformer registered");
                    }
                } else {
                    AgentLog.info("textures normal-cache disabled by config");
                }
            } catch (Throwable t) {
                AgentLog.fail("textures normal-cache init failed; continuing", t);
            }
            ScriptCacheHook.setContext(ctx);
            if (!ctx.config().scriptsEnabled()) {
                AgentLog.info("scripts cache disabled by config");
                return;
            }
            if (!frPresent()) {
                AgentLog.info("FR missing; scripts cache disabled");
                return;
            }
            instrumentation.addTransformer(new ScriptCacheTransformer(), false);
            Runtime.getRuntime().addShutdownHook(new Thread(ScriptCacheHook::shutdown,
                    "Hypernova-ScriptCache-Shutdown"));
            ScriptCacheHook.markAgentStart();
            // 后台算缓存 key：premain 到 preload 之间有约 20 s 的游戏自身初始化，
            // 把 3–15 s 的 sha256 扫描藏进去，不占主加载线程。
            ScriptCacheHook.startKeyComputationAsync(ctx);
            Thread summary = new Thread(() -> {
                while (true) {
                    try {
                        Thread.sleep(30_000);
                    } catch (InterruptedException e) {
                        return;
                    }
                    ScriptCacheHook.summaryTick();
                }
            }, "Hypernova-ScriptCache-Summary");
            summary.setDaemon(true);
            summary.start();
            AgentLog.info("scripts cache transformer registered");
        } catch (Throwable t) {
            AgentLog.fail("agent init failed; scripts cache disabled", t);
        }
    }

    private static boolean frPresent() {
        try {
            Class.forName("com.genir.renderer.Version", false, ClassLoader.getSystemClassLoader());
            return true;
        } catch (Throwable t) {
            return false;
        }
    }
}
