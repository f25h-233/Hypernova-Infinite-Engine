package hypernova.hooks;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public final class FleetSpriteResolver {
    private final SpriteNameSource source;

    public FleetSpriteResolver(SpriteNameSource source) {
        this.source = source;
    }

    public List<String> resolve(FleetView view) {
        Set<String> out = new LinkedHashSet<>();
        for (VariantRef ref : view.members()) {
            out.addAll(source.variantHullSprites(ref.hullVariantId()));
        }
        return List.copyOf(out);
    }
}
