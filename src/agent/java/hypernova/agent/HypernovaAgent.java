package hypernova.agent;

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
