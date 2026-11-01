package hypernova.agent.textures;

import java.awt.Color;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

/**
 * Reflection shape of com.fs.graphics.Object (0.98a-RC8). Field names are the
 * obfuscated names verified by javap; any rename/type change makes resolve()
 * throw and the lazy module fail open (disabled).
 *
 * <p>fieldType supplies the 14 data fields (com.fs.graphics.Object); proxyType
 * supplies the 3-arg constructor (LazyProxyObject, a subclass of Object, so the
 * superclass fields apply to its instances).
 *
 * Field semantics (see docs/m25-spike.md):
 *   ö00000 target, ô00000 GL id, ÒO0000 imageHeight, Ô00000 imageWidth,
 *   oO0000 width, Object height, for texWidth, ø00000 texHeight,
 *   int path, Ò00000 stringId, Ø00000 deferred, three Color fields.
 */
final class ProxyShape {
    private final Constructor<?> ctor;
    private final Field[] all;
    private final Field width;
    private final Field height;
    private final Field imageWidth;
    private final Field imageHeight;
    private final Field texWidth;
    private final Field texHeight;
    private final Field path;
    private final Field stringId;

    private ProxyShape(Constructor<?> ctor, Field[] all, Field width, Field height,
                       Field imageWidth, Field imageHeight, Field texWidth, Field texHeight,
                       Field path, Field stringId) {
        this.ctor = ctor;
        this.all = all;
        this.width = width;
        this.height = height;
        this.imageWidth = imageWidth;
        this.imageHeight = imageHeight;
        this.texWidth = texWidth;
        this.texHeight = texHeight;
        this.path = path;
        this.stringId = stringId;
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
        return new ProxyShape(ctor, all, width, height, imageWidth, imageHeight,
                texWidth, texHeight, path, stringId);
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

    private static Field field(Class<?> type, String name, Class<?> expected) throws Exception {
        Field field = type.getDeclaredField(name);
        if (field.getType() != expected) {
            throw new NoSuchFieldException(name + " has type " + field.getType());
        }
        field.setAccessible(true);
        return field;
    }
}
