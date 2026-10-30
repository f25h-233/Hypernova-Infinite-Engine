#!/usr/bin/env python3
"""Apply the Hypernova lazy-normal-cache patch to GraphicsLib 1.12.1 TextureData.java.

The patch is intentionally exact-version: the source SHA-256 is pinned, and the
method we rewrite is located structurally. Any other GraphicsLib version fails
closed (exit 2) instead of producing a half-patched class.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

EXPECTED_SOURCE_SHA = "db95f036a87276685ee3c7ae5b57671866d6c68542cdf3f9c3adf8cae4bacaa4"
METHOD_ANCHOR = "    public static void mapSpriteToMNSWithAutoGen("
HELPER_ANCHOR = "    private static String filePathForCache(String key, ObjectType type, int frame) {"
PATCHED_MARKER = "Hypernova: startup registers the cached normal map"
METHOD_GUARDS = (
    "autoGenNormalMap(spriteName, key, type, frame)",
    'isAlwaysPreload(key, "ship")',
    "normalSpriteNameToEntry.put(spriteName, entry);",
)


NEW_METHOD = r'''    public static void mapSpriteToMNSWithAutoGen(String key, String spriteName, ObjectType type, int frame, boolean autoGen, boolean autoGenOverride) {
        if ((spriteName != null) && !spriteName.isEmpty() && (key != null) && !key.isEmpty()) {
            if (frame > 0) {
                spriteName = getAnimNameForFrame(spriteName, frame);
            }
            if (CHECK_INEFFICIENT) {
                alertInefficientSprite(spriteName, type);
            }
            if (isLoadMaterial()) {
                TextureEntry entry = getTextureDataWithAutoGen(key, TextureDataType.MATERIAL_MAP, type, frame, null, true);
                if (entry == null) {
                    entry = materialSpriteNameToEntry.get(spriteName);
                    if (entry != null) {
                        materialKeyToEntry.put(getTextureDataKey(key, type, frame), entry);
                        if ((entry.spriteName != null) && !spriteName.isEmpty()) {
                            mnsSpritePathSet.add(entry.spriteName);
                        }
                    }
                } else {
                    materialSpriteNameToEntry.put(spriteName, entry);
                }
            }
            if (isLoadNormal()) {
                TextureEntry entry = getTextureDataWithAutoGen(key, TextureDataType.NORMAL_MAP, type, frame, null, true);
                if (entry == null) {
                    entry = normalSpriteNameToEntry.get(spriteName);
                    if (entry == null) {
                        if (autoGen) {
                            final boolean forceLoad = isAlwaysPreloadFor(type, key);
                            final String cachePath = filePathForCache(key, type, frame);
                            /* Hypernova: startup registers the cached normal map without loading it.
                             * The original implementation decoded and uploaded every cached normal map
                             * just to obtain its dimensions, then unloaded it again when
                             * preloadAllMaps=false. On 260mods those 30,378 load/unload cycles cost
                             * 29-64 s of first-screen time. The lazy entry below is loaded on demand by
                             * unloadAndPreloadTextures() / getTextureDataWithAutoGen() exactly as before.
                             */
                            if (!invalidateCache && !GraphicsLibSettings.preloadAllMaps()
                                    && !forceLoad && hasCachedNormalMap(cachePath)) {
                                entry = new TextureEntry(null, cachePath, 1f, !autoGenOverride, true, false, false);
                                normalKeyToEntry.put(getTextureDataKey(key, type, frame), entry);
                                if ((entry.spriteName != null) && !spriteName.isEmpty()) {
                                    mnsSpritePathSet.add(entry.spriteName);
                                }
                                normalSpriteNameToEntry.put(spriteName, entry);
                            } else {
                                final SpriteAPI sprite = autoGenNormalMap(spriteName, key, type, frame);
                                if (sprite != null) {
                                    /* Even if we're not preloading, we do need to load the sprite when establishing the
                                     * cache of auto-generated normal maps.  However, once we have that sprite and have
                                     * made its texture entry, it's safe to just unload it to save memory.
                                     */
                                    entry = new TextureEntry(sprite, cachePath, 1f, !autoGenOverride, true, true, forceLoad);
                                    if (!GraphicsLibSettings.preloadAllMaps()) {
                                        final int texId = entry.sprite.getTextureId();
                                        Global.getSettings().unloadTexture(entry.spriteName);
                                        GL11.glDeleteTextures(texId);
                                        entry.sprite = null;
                                        entry.loaded = false;
                                        vramUsageBytes -= entry.vramSize;
                                    }
                                    normalKeyToEntry.put(getTextureDataKey(key, type, frame), entry);
                                    if ((entry.spriteName != null) && !spriteName.isEmpty()) {
                                        mnsSpritePathSet.add(entry.spriteName);
                                    }
                                    normalSpriteNameToEntry.put(spriteName, entry);
                                }
                            }
                        }
                    } else {
                        normalKeyToEntry.put(getTextureDataKey(key, type, frame), entry);
                        if ((entry.spriteName != null) && !spriteName.isEmpty()) {
                            mnsSpritePathSet.add(entry.spriteName);
                        }
                    }
                } else {
                    normalSpriteNameToEntry.put(spriteName, entry);
                }
            }
            if (isLoadSurface()) {
                TextureEntry entry = getTextureDataWithAutoGen(key, TextureDataType.SURFACE_MAP, type, frame, null, true);
                if (entry == null) {
                    entry = surfaceSpriteNameToEntry.get(spriteName);
                    if (entry != null) {
                        surfaceKeyToEntry.put(getTextureDataKey(key, type, frame), entry);
                        if ((entry.spriteName != null) && !spriteName.isEmpty()) {
                            mnsSpritePathSet.add(entry.spriteName);
                        }
                    }
                } else {
                    surfaceSpriteNameToEntry.put(spriteName, entry);
                }
            }
        }
    }'''


HELPERS = r'''    private static boolean isAlwaysPreloadFor(ObjectType type, String key) {
        switch (type) {
            case SHIP:
                return isAlwaysPreload(key, "ship");
            case TURRET:
                return isAlwaysPreload(key, "turret");
            case TURRET_BARREL:
                return isAlwaysPreload(key, "turretbarrel");
            case TURRET_UNDER:
                return isAlwaysPreload(key, "turretunder");
            case HARDPOINT:
                return isAlwaysPreload(key, "hardpoint");
            case HARDPOINT_BARREL:
                return isAlwaysPreload(key, "hardpointbarrel");
            case HARDPOINT_UNDER:
                return isAlwaysPreload(key, "hardpointunder");
            case MISSILE:
                return isAlwaysPreload(key, "missile");
            default:
                return false;
        }
    }

    private static boolean hasCachedNormalMap(String cachePath) {
        try {
            final String modPath = Global.getSettings().getModManager().getModSpec("shaderLib").getPath();
            final java.io.File file = new java.io.File(modPath, cachePath);
            return file.isFile() && (file.length() >= 8L);
        } catch (Throwable t) {
            return false;
        }
    }

'''


def find_method(text: str) -> tuple[int, int]:
    start = text.index(METHOD_ANCHOR)
    i = text.index("{", start)
    depth = 0
    j = i
    while j < len(text):
        c = text[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return start, j + 1
        j += 1
    raise SystemExit("unterminated mapSpriteToMNSWithAutoGen method")


def patch_text(text: str) -> str:
    if PATCHED_MARKER in text:
        raise SystemExit("already patched")
    start, end = find_method(text)
    old = text[start:end]
    for guard in METHOD_GUARDS:
        if guard not in old:
            raise SystemExit(f"unexpected TextureData version: missing guard {guard!r}")
    text = text[:start] + NEW_METHOD + text[end:]
    if HELPER_ANCHOR not in text:
        raise SystemExit("helper anchor missing")
    text = text.replace(HELPER_ANCHOR, HELPERS + HELPER_ANCHOR, 1)
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    raw = Path(args.source).read_bytes()
    # Idempotence guard must run before the pinned hash check: a patched file
    # necessarily has a different SHA-256 than the pristine source.
    if PATCHED_MARKER.encode("utf-8") in raw:
        print("already patched", file=sys.stderr)
        return 2
    sha = hashlib.sha256(raw).hexdigest()
    if sha != EXPECTED_SOURCE_SHA:
        print(f"sha256 mismatch: {sha} != {EXPECTED_SOURCE_SHA}", file=sys.stderr)
        return 2
    text = raw.decode("utf-8")
    out = patch_text(text)
    Path(args.out).write_text(out, encoding="utf-8", newline="\n")
    print(f"patched {args.source} -> {args.out} ({len(out)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
