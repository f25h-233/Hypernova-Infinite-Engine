import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GLIB_1121_JAR = ROOT / ".cache/graphicslib-1.12.1/Graphics.jar"
GLIB_1122_SRC = ROOT / ".cache/graphicslib-1.12.2/src/TextureData.java"
LEGACY_JAR = ROOT / "Starsector-098-260mods/mods/GraphicsLib/jars/Graphics.jar"
SHA_1121 = "db95f036a87276685ee3c7ae5b57671866d6c68542cdf3f9c3adf8cae4bacaa4"
SHA_1122 = "dc7b2a4fdae2633275eaed37a0c9a694961a4676f771eaf9682425429d93d2a1"
EXPECTED_CLASS_SHA = "6a4302bcacd2dd90f6637c815d1443ddfdb3d28ff59095d48c875358de4e8594"


def extract_source():
    """Return (pristine TextureData.java bytes, pinned SHA-256).

    1.12.2 no longer ships .java inside Graphics.jar, so prefer the staged
    upstream source; fall back to a 1.12.1 jar (staged or test install).
    """
    if GLIB_1122_SRC.is_file():
        return GLIB_1122_SRC.read_bytes(), SHA_1122
    for jar in (GLIB_1121_JAR, LEGACY_JAR):
        if not jar.is_file():
            continue
        with zipfile.ZipFile(jar) as z:
            try:
                return z.read("org/dark/shaders/util/TextureData.java"), SHA_1121
            except KeyError:
                continue
    pytest.skip("no pristine GraphicsLib TextureData.java available")


def test_patch_adds_lazy_entry_without_loading(tmp_path):
    src, sha = extract_source()
    inp = tmp_path / "TextureData.java"
    out = tmp_path / "TextureData.patched.java"
    inp.write_bytes(src)
    r = subprocess.run([sys.executable, str(ROOT / "tools/java/texture_patch.py"),
                        "--source", str(inp), "--out", str(out),
                        "--expect-source-sha", sha],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    text = out.read_text(encoding="utf-8")
    assert "hasCachedNormalMap(cachePath)" in text
    assert "new TextureEntry(null, cachePath" in text
    assert "!invalidateCache && !GraphicsLibSettings.preloadAllMaps()" in text
    # 原路径必须还在（回退时仍走 autoGenNormalMap）
    assert "autoGenNormalMap(spriteName, key, type, frame)" in text


def test_patch_rejects_wrong_source_hash(tmp_path):
    src, sha = extract_source()
    src = bytearray(src)
    src[100] ^= 0xFF
    inp = tmp_path / "TextureData.java"
    out = tmp_path / "out.java"
    inp.write_bytes(src)
    r = subprocess.run([sys.executable, str(ROOT / "tools/java/texture_patch.py"),
                        "--source", str(inp), "--out", str(out),
                        "--expect-source-sha", sha],
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert "sha256 mismatch" in (r.stderr + r.stdout)


def test_patch_is_idempotence_guarded(tmp_path):
    src, sha = extract_source()
    inp = tmp_path / "TextureData.java"
    out1 = tmp_path / "out1.java"
    out2 = tmp_path / "out2.java"
    inp.write_bytes(src)
    cmd = [sys.executable, str(ROOT / "tools/java/texture_patch.py"),
           "--source", str(inp), "--out", str(out1),
           "--expect-source-sha", sha]
    assert subprocess.run(cmd, capture_output=True).returncode == 0
    cmd2 = [sys.executable, str(ROOT / "tools/java/texture_patch.py"),
            "--source", str(out1), "--out", str(out2)]
    r = subprocess.run(cmd2, capture_output=True, text=True)
    assert r.returncode != 0
    assert "already patched" in (r.stderr + r.stdout)
