package hypernova.adapter;

public interface VariantLookup {
    Result lookup(String hullVariantId);

    record Result(String hullSpriteName) {
    }
}
