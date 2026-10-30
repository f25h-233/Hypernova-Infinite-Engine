package hypernova.agent;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * {@code -Dhypernova.sourceOracle} 是 SourceOracle 诊断扫描的开关。
 *
 * <p>默认必须开启（不改变既有行为）：关闭只对显式的 {@code false} 生效，
 * 其它取值（包括未设置）都保持开启。
 */
class SourceOracleSwitchTest {
    private static final String PROP = "hypernova.sourceOracle";
    private String original;

    @BeforeEach
    void captureProperty() {
        original = System.getProperty(PROP);
    }

    @AfterEach
    void restoreProperty() {
        // 系统属性是 JVM 全局状态：每个用例后必须复原，避免污染其它测试类。
        if (original == null) {
            System.clearProperty(PROP);
        } else {
            System.setProperty(PROP, original);
        }
    }

    @Test
    void enabledWhenPropertyUnset() {
        System.clearProperty(PROP);
        assertTrue(ScriptCacheHook.sourceOracleEnabled(),
                "未设属性时 SourceOracle 必须默认开启");
    }

    @Test
    void disabledWhenPropertyIsFalse() {
        System.setProperty(PROP, "false");
        assertFalse(ScriptCacheHook.sourceOracleEnabled(),
                "-Dhypernova.sourceOracle=false 必须关闭 SourceOracle");
    }

    @Test
    void explicitTrueKeepsItEnabled() {
        System.setProperty(PROP, "true");
        assertTrue(ScriptCacheHook.sourceOracleEnabled(),
                "显式设为 true 时保持开启");
    }
}
