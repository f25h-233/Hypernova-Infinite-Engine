package hypernova.adapter;

import com.fs.starfarer.api.SettingsAPI;
import com.fs.starfarer.api.graphics.SpriteAPI;
import hypernova.texture.TextureBackend;

public final class GameBackend implements TextureBackend {
    private final SettingsAPI settings;

    public GameBackend(SettingsAPI settings) {
        this.settings = settings;
    }

    @Override
    public boolean isRegistered(String path) {
        SpriteAPI sprite = settings.getSprite(path);
        return sprite != null && sprite.getTextureId() > 0;
    }

    @Override
    public void load(String path) throws Exception {
        settings.loadTexture(path);
    }
}
