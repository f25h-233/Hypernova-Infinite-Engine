package com.genir.renderer.overrides.loading;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/** 与 FR 0.9.5 同形的最小 fake：字段名、构造器描述符、findClass 语义一致。 */
public class MultiThreadedJaninoClassLoader extends ClassLoader {
    private final Map<String, byte[]> bytecodeCache = new ConcurrentHashMap<>();

    public MultiThreadedJaninoClassLoader(ClassLoader parent) {
        super(parent);
    }

    @Override
    protected Class<?> findClass(String name) throws ClassNotFoundException {
        byte[] b = bytecodeCache.get(name);
        if (b == null) throw new ClassNotFoundException(name);
        return defineClass(name, b, 0, b.length);
    }

    public Map<String, byte[]> bytecodeCache() {
        return bytecodeCache;
    }

    public Class<?> find(String name) throws ClassNotFoundException {
        return findClass(name);
    }
}
