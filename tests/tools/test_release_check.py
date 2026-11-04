import hashlib
import importlib.util
import os
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools"
_spec = importlib.util.spec_from_file_location("release_check", TOOLS / "release_check.py")
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

MANIFEST = b'{"schema":"hypernova-runtime-1","layers":[]}'
GEN = hashlib.sha256(MANIFEST).hexdigest()
AGENT = ("hypernova/agent/HypernovaAgent.class",
         "hypernova/agent/textures/LazyTextures.class",
         "hypernova/agent/textures/LazyProxyObject.class")
MAIN = ("hypernova/HypernovaPlugin.class",
        "hypernova/adapter/HypernovaCombatPlugin.class")


def _agent_jar(path, extra=None):
    with zipfile.ZipFile(path, "w") as zf:
        for name in AGENT:
            zf.writestr(name, b"x")
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return path


def _main_jar(path, extra=None):
    with zipfile.ZipFile(path, "w") as zf:
        for name in MAIN:
            zf.writestr(name, b"x")
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return path


def _release_zip(tmp_path, drop=(), overrides=None):
    jar = _agent_jar(tmp_path / "agent.jar")
    main = _main_jar(tmp_path / "hypernova.jar")
    files = {
        "mod_info.json": b"{}",
        "README-install.txt": b"note",
        "data/config/hypernova/manifest-v1.json": MANIFEST,
        "data/config/hypernova/lazy-skip-v1.txt":
            b"# generation=" + GEN.encode() + b"\npath\t1\t1\n",
        "jars/hypernova.agent.jar": jar.read_bytes(),
        "jars/hypernova.jar": main.read_bytes(),
        "graphics/hypernova/blank.png": b"png",
    }
    # 发行包必须带玩家侧工具（含内置 Python）；夹具直接跟随 TOOL_FILES，
    # 免得以后加文件时测试与门禁脱节。
    files.update({name: b"x" for name in rc.TOOL_FILES})
    files.update(overrides or {})
    for name in drop:
        files.pop(name, None)
    zip_path = tmp_path / "mod.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        # 发行包根目录必须套一层 <mod 文件夹>/，夹具跟着真实结构走。
        for name, data in files.items():
            zf.writestr(rc.PREFIX + name, data)
    return zip_path, jar


def test_valid_release_passes(tmp_path):
    zip_path, jar = _release_zip(tmp_path)
    assert rc.check_zip(zip_path, jar) == []


def test_missing_manifest_fails(tmp_path):
    zip_path, jar = _release_zip(
        tmp_path, drop=("data/config/hypernova/manifest-v1.json",))
    assert any("data/config/hypernova/manifest-v1.json" in f
               for f in rc.check_zip(zip_path, jar))


def test_missing_player_tool_fails(tmp_path):
    zip_path, jar = _release_zip(
        tmp_path, drop=("hypernova-tools/manage_agent.py",))
    assert any("hypernova-tools/manage_agent.py" in f
               for f in rc.check_zip(zip_path, jar))


def test_missing_bundled_python_fails(tmp_path):
    zip_path, jar = _release_zip(
        tmp_path, drop=("hypernova-tools/python/python.exe",))
    assert any("hypernova-tools/python/python.exe" in f
               for f in rc.check_zip(zip_path, jar))


def test_host_skip_v2_is_forbidden(tmp_path):
    zip_path, jar = _release_zip(tmp_path, overrides={
        "data/config/hypernova/lazy-skip-v2.txt":
            b"# generation=" + GEN.encode()
            + b"\npath\t1\t1\tC:/x.png\tC:/x.dds\t1\n",
    })
    assert any("lazy-skip-v2" in f for f in rc.check_zip(zip_path, jar))


def test_generation_mismatch_fails(tmp_path):
    zip_path, jar = _release_zip(tmp_path, overrides={
        "data/config/hypernova/lazy-skip-v1.txt":
            b"# generation=deadbeef\npath\t1\t1\n",
    })
    assert any("generation" in f for f in rc.check_zip(zip_path, jar))


def test_agent_jar_markers_and_match(tmp_path):
    zip_path, jar = _release_zip(tmp_path)
    bad = _agent_jar(tmp_path / "bad.jar", extra={"extra/Thing.class": b"x"})
    assert any("agent jar entries differ" in f
               for f in rc.check_zip(zip_path, bad))
    incomplete = tmp_path / "incomplete.jar"
    with zipfile.ZipFile(incomplete, "w") as zf:
        zf.writestr("hypernova/agent/HypernovaAgent.class", b"x")
    assert any("missing hypernova/agent/textures/LazyTextures.class" in f
               for f in rc.check_zip(zip_path, incomplete))


def test_agent_freshness(tmp_path):
    src = tmp_path / "src"
    (src / "a").mkdir(parents=True)
    source = src / "a" / "X.java"
    source.write_text("class X {}", encoding="utf-8")
    jar = _agent_jar(tmp_path / "agent.jar")
    now = time.time()
    os.utime(source, (now - 60, now - 60))
    os.utime(jar, (now, now))
    assert rc.check_agent_fresh(jar, src) == []
    os.utime(source, (now + 60, now + 60))
    assert any("agent sources newer than jar" in f
               for f in rc.check_agent_fresh(jar, src))


def test_missing_main_jar_fails(tmp_path):
    zip_path, _ = _release_zip(tmp_path, drop=("jars/hypernova.jar",))
    assert any("jars/hypernova.jar" in f
               for f in rc.check_zip(zip_path))


def test_main_jar_missing_marker_fails(tmp_path):
    bad = tmp_path / "bad-main.jar"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("unrelated/Thing.class", b"x")
    zip_path, _ = _release_zip(
        tmp_path, overrides={"jars/hypernova.jar": bad.read_bytes()})
    assert any("packaged main jar missing" in f
               for f in rc.check_zip(zip_path))


def test_main_jar_entries_must_match_built(tmp_path):
    zip_path, _ = _release_zip(tmp_path)
    built = _main_jar(tmp_path / "built.jar",
                      extra={"extra/Thing.class": b"x"})
    assert any("packaged main jar entries differ" in f
               for f in rc.check_zip(zip_path, main_jar=built))


def test_identical_main_jar_passes(tmp_path):
    zip_path, _ = _release_zip(tmp_path)
    built = _main_jar(tmp_path / "built.jar")
    assert rc.check_zip(zip_path, main_jar=built) == []


def test_empty_main_jar_fails(tmp_path):
    zip_path, _ = _release_zip(
        tmp_path, overrides={"jars/hypernova.jar": b""})
    assert any("jars/hypernova.jar" in f and "empty" in f
               for f in rc.check_zip(zip_path))


def test_built_main_jar_missing_marker_fails(tmp_path):
    zip_path, _ = _release_zip(tmp_path)
    built = tmp_path / "built-partial.jar"
    with zipfile.ZipFile(built, "w") as zf:
        zf.writestr(MAIN[0], b"x")
    assert any("built main jar missing" in f
               for f in rc.check_zip(zip_path, main_jar=built))


def test_corrupt_main_jar_fails(tmp_path):
    zip_path, _ = _release_zip(
        tmp_path, overrides={"jars/hypernova.jar": b"not a zip"})
    assert any("packaged main jar missing" in f
               for f in rc.check_zip(zip_path))


def test_zero_size_main_marker_fails(tmp_path):
    bad = tmp_path / "empty-markers.jar"
    with zipfile.ZipFile(bad, "w") as zf:
        for name in MAIN:
            zf.writestr(name, b"")
    zip_path, _ = _release_zip(
        tmp_path, overrides={"jars/hypernova.jar": bad.read_bytes()})
    assert any("packaged main jar missing" in f
               for f in rc.check_zip(zip_path))


def test_zip_without_mod_folder_is_rejected(tmp_path):
    """根目录直接摊 mod_info.json 的包必须被拒：玩家解压到 mods/ 会散架。"""
    jar = _agent_jar(tmp_path / "agent.jar")
    zip_path = tmp_path / "flat.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("mod_info.json", b"{}")
        zf.writestr("jars/hypernova.agent.jar", jar.read_bytes())
    failures = rc.check_zip(zip_path, jar)
    assert any("zip root must be exactly" in f for f in failures), failures
