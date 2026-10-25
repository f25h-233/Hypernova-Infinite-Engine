package hypernova.adapter;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class GameSpriteSourceTest {

    @Test
    void mapsVariantToHullSprite() {
        VariantLookup lookup = id -> "onslaught_Standard".equals(id)
                ? new VariantLookup.Result("graphics/ships/onslaught.png")
                : null;
        GameSpriteSource src = new GameSpriteSource(lookup);
        assertEquals(List.of("graphics/ships/onslaught.png"),
                src.variantHullSprites("onslaught_Standard"));
    }

    @Test
    void unknownVariantIsEmpty() {
        VariantLookup lookup = id -> null;
        GameSpriteSource src = new GameSpriteSource(lookup);
        assertEquals(List.of(), src.variantHullSprites("nope"));
    }

    @Test
    void nullSpriteNameIsEmpty() {
        VariantLookup lookup = id -> new VariantLookup.Result(null);
        GameSpriteSource src = new GameSpriteSource(lookup);
        assertEquals(List.of(), src.variantHullSprites("x"));
    }

    @Test
    void emptySpriteNameIsEmpty() {
        VariantLookup lookup = id -> new VariantLookup.Result("");
        GameSpriteSource src = new GameSpriteSource(lookup);
        assertEquals(List.of(), src.variantHullSprites("x"));
    }

    @Test
    void nullVariantIdIsEmptyWithoutCallingLookup() {
        VariantLookup lookup = id -> {
            throw new AssertionError("lookup must not be called for null variant id");
        };
        GameSpriteSource src = new GameSpriteSource(lookup);
        assertEquals(List.of(), src.variantHullSprites(null));
    }
}
