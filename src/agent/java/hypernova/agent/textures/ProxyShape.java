package hypernova.agent.textures;

import java.awt.Color;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

/**
 * Reflection shape of com.fs.graphics.Object (0.98a-RC8). Field names are the
 * obfuscated names verified by javap; any rename/type change makes resolve()
 * throw and the lazy module fail open (disabled).
 *
 * <p>Field semantics (final-review m6; see docs/m25-spike.md):
 *   ö00000 target, ô00000 GL id, ÒO0000 imageHeight, Ô00000 imageWidth,
 *   oO0000 texture width, Object texture height, for texWidth, ø00000 texHeight,
 *   int path, Ò00000 stringId, Ø00000 deferred, three Color fields.
 */
final class ProxyShape {
    private final Constructor<?> ctor;
    private final Field[] all;
    private final Field target;
    private final Field glId;
    private final Field width;
    private final Field height;
    private final Field imageWidth;
    private final Field imageHeight;
    private final Field texWidth;
    private final Field texHeight;
    private final Field path;
    private final Field stringId;
    private final Field deferred;
    private final Field color0;
    private final Field color1;
    private final Field color2;

    private ProxyShape(Constructor<?> ctor, Field[] all, Field target, Field glId,
                       Field width, Field height, Field imageWidth, Field imageHeight,
                       Field texWidth, Field texHeight, Field path, Field stringId,
                       Field deferred, Field color0, Field color1, Field color2) {
        this.ctor = ctor;
        this.all = all;
        this.target = target;
        this.glId = glId;
        this.width = width;
        this.height = height;
        this.imageWidth = imageWidth;
        this.imageHeight = imageHeight;
        this.texWidth = texWidth;
        this.texHeight = texHeight;
        this.path = path;
        this.stringId = stringId;
        this.deferred = deferred;
        this.color0 = color0;
        this.color1 = color1;
        this.color2 = color2;
    }

    static ProxyShape resolve(Class<?> fieldType, Class<?> proxyType) throws Exception {
        Constructor<?> ctor = proxyType.getDeclaredConstructor(int.class, int.class, String.class);
        ctor.setAccessible(true);
        Field target = field(fieldType, "ö00000", int.class);
        Field id = field(fieldType, "ô00000", int.class);
        Field imageHeight = field(fieldType, "ÒO0000", int.class);
        Field imageWidth = field(fieldType, "Ô00000", int.class);
        Field width = field(fieldType, "oO0000", int.class);
        Field height = field(fieldType, "Object", int.class);
        Field texWidth = field(fieldType, "for", float.class);
        Field texHeight = field(fieldType, "ø00000", float.class);
        Field path = field(fieldType, "int", String.class);
        Field stringId = field(fieldType, "Ò00000", String.class);
        Field deferred = field(fieldType, "Ø00000", boolean.class);
        Field color0 = field(fieldType, "Õ00000", Color.class);
        Field color1 = field(fieldType, "o00000", Color.class);
        Field color2 = field(fieldType, "public", Color.class);
        Field[] all = {target, id, imageHeight, imageWidth, width, height,
                texWidth, texHeight, path, stringId, deferred, color0, color1, color2};
        return new ProxyShape(ctor, all, target, id, width, height, imageWidth,
                imageHeight, texWidth, texHeight, path, stringId, deferred,
                color0, color1, color2);
    }

    Object newProxy(String pathValue, int w, int h) throws Exception {
        Object proxy = ctor.newInstance(3553, 0, pathValue);
        width.setInt(proxy, w);
        height.setInt(proxy, h);
        imageWidth.setInt(proxy, w);
        imageHeight.setInt(proxy, h);
        texWidth.setFloat(proxy, 1.0f);
        texHeight.setFloat(proxy, 1.0f);
        path.set(proxy, pathValue);
        stringId.set(proxy, pathValue);
        return proxy;
    }

    void copy(Object from, Object to) throws Exception {
        for (Field field : all) field.set(to, field.get(from));
    }

    /**
     * Resets a proxy to the shared 1x1 placeholder texture while keeping the
     * declared image dimensions (layout) so existing Sprites do not collapse.
     */
    void reset(Object obj, int targetValue, int idValue, int w, int h,
               float tw, float th, int imageW, int imageH) throws Exception {
        target.setInt(obj, targetValue);
        glId.setInt(obj, idValue);
        width.setInt(obj, w);
        height.setInt(obj, h);
        texWidth.setFloat(obj, tw);
        texHeight.setFloat(obj, th);
        imageWidth.setInt(obj, imageW);
        imageHeight.setInt(obj, imageH);
        deferred.setBoolean(obj, false);
        color0.set(obj, Color.WHITE);
        color1.set(obj, Color.WHITE);
        color2.set(obj, Color.WHITE);
    }

    int imageWidth(Object obj) throws Exception {
        return imageWidth.getInt(obj);
    }

    int imageHeight(Object obj) throws Exception {
        return imageHeight.getInt(obj);
    }

    int glId(Object obj) throws Exception {
        return glId.getInt(obj);
    }

    int target(Object obj) throws Exception {
        return target.getInt(obj);
    }

    private static Field field(Class<?> type, String name, Class<?> expected) throws Exception {
        Field field = type.getDeclaredField(name);
        if (field.getType() != expected) {
            throw new NoSuchFieldException(name + " has type " + field.getType());
        }
        field.setAccessible(true);
        return field;
    }
}
