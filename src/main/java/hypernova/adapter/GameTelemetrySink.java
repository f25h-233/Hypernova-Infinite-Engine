package hypernova.adapter;

import com.fs.starfarer.api.SettingsAPI;
import hypernova.telemetry.TelemetrySink;

public final class GameTelemetrySink implements TelemetrySink {
    private final SettingsAPI settings;

    public GameTelemetrySink(SettingsAPI settings) {
        this.settings = settings;
    }

    @Override
    public void write(String name, String content) throws Exception {
        settings.writeTextFileToCommon(name, content);
    }
}
