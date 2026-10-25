package hypernova.texture;

public interface TextureBackend {
    boolean isRegistered(String path);

    void load(String path) throws Exception;
}
