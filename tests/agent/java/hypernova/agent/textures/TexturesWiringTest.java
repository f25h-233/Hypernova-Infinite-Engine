package hypernova.agent.textures;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.jar.JarFile;

import static org.junit.jupiter.api.Assertions.*;

class TexturesWiringTest {
    @Test
    void agentJarCarriesPatchResourceButNotTheClass() throws Exception {
        try (JarFile jar = new JarFile("build/agent/hypernova.agent.jar")) {
            assertNotNull(jar.getEntry("hypernova/agent/textures/variants.properties"),
                    "变体索引必须打包");
            long variants = jar.stream()
                    .filter(e -> e.getName().startsWith("hypernova/agent/textures/v/")
                            && e.getName().endsWith(".class.bin"))
                    .count();
            assertTrue(variants >= 2, "至少要有 1.12.1 与 1.12.2 两个补丁变体，实际 " + variants);
            assertNull(jar.getEntry("org/dark/shaders/util/TextureData.class"),
                    "补丁类不能出现在 agent classpath 根，否则父加载器会先加载它");
        }
    }

    @Test
    void premainRegistersTexturesBeforeTheScriptsEarlyReturn() throws Exception {
        String src = Files.readString(Path.of("src/agent/java/hypernova/agent/HypernovaAgent.java"));
        int textures = src.indexOf("addTransformer(transformer, false)");
        int scriptsGate = src.indexOf("scripts cache disabled by config");
        assertTrue(textures > 0, "premain 必须注册 textures transformer");
        assertTrue(scriptsGate > 0, "scripts 早退必须还在");
        assertTrue(textures < scriptsGate,
                "textures 注册必须在 scripts 早退之前，否则 scripts 关闭时纹理补丁也失效");
    }
}
