package hypernova.agent;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * {@code -Dhypernova.sourceOracle} 是 SourceOracle 诊断扫描的开关。
 *
 * <p>默认关闭（诊断用途，缓存决策不依赖）。{@code Boolean.parseBoolean} 只有
 * {@code "true"}（忽略大小写）为 true；{@code false}/{@code 0}/{@code no}/空串等
 * 一律为 false，未设属性时走默认值 false。
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
    void disabledWhenPropertyUnset() {
        System.clearProperty(PROP);
        assertFalse(ScriptCacheHook.sourceOracleEnabled(),
                "未设属性时 SourceOracle 必须默认关闭");
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
