package hypernova.adapter;

import hypernova.hooks.SpriteNameSource;

import java.util.ArrayList;
import java.util.List;

public final class GameSpriteSource implements SpriteNameSource {
    private final VariantLookup lookup;

    public GameSpriteSource(VariantLookup lookup) {
        this.lookup = lookup;
    }

    @Override
    public List<String> hullSpriteNames() {
        return List.of();
    }

    @Override
    public List<String> weaponSpriteNames() {
        return List.of();
    }

    @Override
    public List<String> variantHullSprites(String hullVariantId) {
        if (hullVariantId == null) {
            return List.of();
        }
        VariantLookup.Result r = lookup.lookup(hullVariantId);
        if (r == null || r.hullSpriteName() == null || r.hullSpriteName().isEmpty()) {
            return List.of();
        }
        List<String> out = new ArrayList<>(1);
        out.add(r.hullSpriteName());
        return out;
    }
}
