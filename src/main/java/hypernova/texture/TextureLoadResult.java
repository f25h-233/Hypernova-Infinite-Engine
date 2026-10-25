package hypernova.texture;

public record TextureLoadResult(boolean ok, boolean queued, long nanos, TextureState state) {
}
