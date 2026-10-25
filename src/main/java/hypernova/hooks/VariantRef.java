package hypernova.hooks;

import java.util.List;

public record VariantRef(String hullId, String hullVariantId, List<String> weaponIds) {
}
