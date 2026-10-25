package hypernova.hooks;

import java.util.List;

public interface SpriteNameSource {
    List<String> hullSpriteNames();

    List<String> weaponSpriteNames();

    List<String> variantHullSprites(String hullVariantId);
}
