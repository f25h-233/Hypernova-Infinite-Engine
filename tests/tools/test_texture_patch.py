import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JAR = ROOT / "Starsector-098-260mods/mods/GraphicsLib/jars/Graphics.jar"
EXPECTED_CLASS_SHA = "6a4302bcacd2dd90f6637c815d1443ddfdb3d28ff59095d48c875358de4e8594"


def extract_source(tmp_path):
    if not JAR.is_file():
        pytest.skip("GraphicsLib jar not installed")
    with zipfile.ZipFile(JAR) as z:
        return z.read("org/dark/shaders/util/TextureData.java")


def test_patch_adds_lazy_entry_without_loading(tmp_path):
    src = extract_source(tmp_path)
    inp = tmp_path / "TextureData.java"
    out = tmp_path / "TextureData.patched.java"
    inp.write_bytes(src)
    r = subprocess.run([sys.executable, str(ROOT / "tools/java/texture_patch.py"),
                        "--source", str(inp), "--out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    text = out.read_text(encoding="utf-8")
    assert "hasCachedNormalMap(cachePath)" in text
    assert "new TextureEntry(null, cachePath" in text
    assert "!invalidateCache && !GraphicsLibSettings.preloadAllMaps()" in text
    # 原路径必须还在（回退时仍走 autoGenNormalMap）
    assert "autoGenNormalMap(spriteName, key, type, frame)" in text


def test_patch_rejects_wrong_source_hash(tmp_path):
    src = bytearray(extract_source(tmp_path))
    src[100] ^= 0xFF
    inp = tmp_path / "TextureData.java"
    out = tmp_path / "out.java"
    inp.write_bytes(src)
    r = subprocess.run([sys.executable, str(ROOT / "tools/java/texture_patch.py"),
                        "--source", str(inp), "--out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert "sha256 mismatch" in (r.stderr + r.stdout)


def test_patch_is_idempotence_guarded(tmp_path):
    src = extract_source(tmp_path)
    inp = tmp_path / "TextureData.java"
    out1 = tmp_path / "out1.java"
    out2 = tmp_path / "out2.java"
    inp.write_bytes(src)
    cmd = [sys.executable, str(ROOT / "tools/java/texture_patch.py"),
           "--source", str(inp), "--out", str(out1)]
    assert subprocess.run(cmd, capture_output=True).returncode == 0
    cmd2 = [sys.executable, str(ROOT / "tools/java/texture_patch.py"),
            "--source", str(out1), "--out", str(out2)]
    r = subprocess.run(cmd2, capture_output=True, text=True)
    assert r.returncode != 0
    assert "already patched" in (r.stderr + r.stdout)
