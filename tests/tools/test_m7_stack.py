import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import m7_stack
from m7_stack import (
    apply_disable_ime,
    apply_disable_mixinfr_fonts,
    apply_migrate,
    apply_route_a,
    apply_route_b,
    collect_logs,
    inspect_root,
    main,
    plan_disable_ime,
    plan_disable_mixinfr_fonts,
    plan_migrate,
    plan_route_a,
    plan_route_b,
    rollback_route,
    snapshot_route,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _mod(src: Path, folder: str, mod_id: str | None = None) -> None:
    (src / folder).mkdir(parents=True, exist_ok=True)
    _write(src / folder / "mod_info.json",
           json.dumps({"id": mod_id or folder}))


@pytest.fixture
def mini_install(tmp_path):
    root = tmp_path / "install"
    _write(root / "starsector-core/localization_version.json", json.dumps({
        "name": "远行星号中文汉化包", "author": "远星汉化组",
        "version": "2026.10.15", "branch": "startup-optimization",
        "language": "zh-Hans", "game_version": "0.98a-RC8",
    }))
    _write(root / "starsector-core/graphics/fonts/dyn_font/chars.txt", "a\n")
    (root / "starsector-core/native/windows").mkdir(parents=True)
    (root / "starsector-core/native/windows/ssime.dll").write_bytes(b"x")
    _write(root / "vmparams", "java.exe -Xmx2g com.fs.starfarer.StarfarerLauncher\n")
    _write(root / "mods/enabled_mods.json", json.dumps({"enabledMods": []}))
    _write(root / "jre/release", "JAVA_VERSION=\"17.0.10\"\n")
    return root


def test_inspect_root_reports_chinese_optimized_build(mini_install):
    data = inspect_root(mini_install)
    assert data["localization"]["version"] == "2026.10.15"
    assert data["localization"]["branch"] == "startup-optimization"
    assert data["dyn_font"] is True
    assert data["ssime_dll"] is True
    assert data["jre_version"] == "17.0.10"
    assert data["vmparams"]["has_agent"] is False
    assert data["mods"]["enabled_count"] == 0


def test_inspect_root_detects_agents_and_flags(mini_install):
    _write(mini_install / "vmparams",
           "java.exe -javaagent:..\\mods\\MixinFR\\jars\\MixinLib-bridge.jar "
           "-Dhypernova.frameProbe=true com.fs.starfarer.StarfarerLauncher\n")
    data = inspect_root(mini_install)
    assert data["vmparams"]["has_agent"] is True
    assert "MixinLib-bridge.jar" in data["vmparams"]["agents"][0]
    assert "frameProbe" in data["vmparams"]["hypernova_flags"][0]


def test_plan_migrate_excludes_route_mods(tmp_path):
    src = tmp_path / "src"
    for name in ("mod_a", "VramOptimizer", "ChineseInputFix",
                 "hypernova_infinite_engine", "MixinFR", "StarsectorParallel"):
        (src / name).mkdir(parents=True)
        (src / name / "mod_info.json").write_text(
            '{"id":"%s"}' % name, encoding="utf-8")
    (src / "enabled_mods.json").write_text(
        '{"enabledMods":["mod_a","VramOptimizer","ChineseInputFix",'
        '"hypernova_infinite_engine","MixinLib","starsectorparallel"]}',
        encoding="utf-8")
    plan = plan_migrate(src, tmp_path / "dst", link=False)
    assert set(plan["copy"]) == {"mod_a", "VramOptimizer", "ChineseInputFix"}
    assert plan["enabled"] == ["mod_a", "VramOptimizer", "ChineseInputFix"]
    assert plan["excluded"] == ["MixinFR", "StarsectorParallel",
                                "hypernova_infinite_engine"]


def test_apply_migrate_dry_run_writes_nothing(tmp_path):
    src = tmp_path / "src"; (src / "mod_a").mkdir(parents=True)
    _write(src / "enabled_mods.json", '{"enabledMods":["mod_a"]}')
    plan = plan_migrate(src, tmp_path / "dst", link=False)
    result = apply_migrate(plan)
    assert result["applied"] is False
    assert not (tmp_path / "dst").exists()


def test_plan_migrate_maps_id_to_different_folder(tmp_path):
    src = tmp_path / "src"
    _mod(src, "AzureFederation", mod_id="Starlight1130")
    _write(src / "enabled_mods.json", '{"enabledMods":["Starlight1130"]}')
    plan = plan_migrate(src, tmp_path / "dst", link=False)
    assert plan["enabled"] == ["Starlight1130"]
    assert plan["copy"] == ["AzureFederation"]
    assert plan["enabled_folders"] == {"Starlight1130": "AzureFederation"}
    assert plan["missing_enabled_ids"] == []


def test_plan_migrate_duplicate_ids_choose_alphabetically_first(tmp_path):
    src = tmp_path / "src"
    _mod(src, "zeta", mod_id="dup_id")
    _mod(src, "alpha", mod_id="dup_id")
    _write(src / "enabled_mods.json", '{"enabledMods":["dup_id"]}')
    plan = plan_migrate(src, tmp_path / "dst", link=False)
    assert plan["copy"] == ["alpha"]
    assert plan["duplicate_ids"] == {
        "dup_id": {"chosen": "alpha", "candidates": ["alpha", "zeta"]},
    }


def test_plan_migrate_reports_missing_enabled_ids(tmp_path):
    src = tmp_path / "src"
    _mod(src, "mod_a")
    _write(src / "enabled_mods.json",
           '{"enabledMods":["mod_a","ghost_id"]}')
    plan = plan_migrate(src, tmp_path / "dst", link=False)
    assert plan["enabled"] == ["mod_a", "ghost_id"]
    assert plan["copy"] == ["mod_a"]
    assert plan["missing_enabled_ids"] == ["ghost_id"]


@pytest.mark.parametrize("payload", [
    None,
    "{bad json",
    '{"enabledMods": null}',
    '{"enabledMods": []}',
    '{"enabledMods": [1]}',
])
def test_plan_migrate_rejects_bad_enabled_mods(tmp_path, payload):
    src = tmp_path / "src"
    _mod(src, "mod_a")
    if payload is not None:
        _write(src / "enabled_mods.json", payload)
    with pytest.raises((FileNotFoundError, ValueError)):
        plan_migrate(src, tmp_path / "dst", link=False)


def test_plan_migrate_preserves_disabled_chinese_input_fix(tmp_path):
    src = tmp_path / "src"
    _mod(src, "mod_a")
    _mod(src, "VramOptimizer")
    _mod(src, "ChineseInputFix")
    _write(src / "enabled_mods.json",
           '{"enabledMods":["mod_a","VramOptimizer"]}')
    plan = plan_migrate(src, tmp_path / "dst", link=False)
    assert plan["copy"] == ["mod_a", "VramOptimizer"]
    assert plan["enabled"] == ["mod_a", "VramOptimizer"]
    assert [item["folder"] for item in plan["extras"]] == ["ChineseInputFix"]
    assert "ChineseInputFix" not in plan["enabled"]

    plan["apply"] = True
    result = apply_migrate(plan)
    assert result["applied"] is True
    assert result["extras_copied"] == 1
    assert (tmp_path / "dst" / "ChineseInputFix").is_dir()
    written = json.loads(
        (tmp_path / "dst" / "enabled_mods.json").read_text(encoding="utf-8"))
    assert written == {"enabledMods": ["mod_a", "VramOptimizer"]}


def test_apply_migrate_copies_and_preserves_enabled_order(tmp_path):
    src = tmp_path / "src"
    _mod(src, "zeta_folder", mod_id="zeta_id")
    _mod(src, "alpha_folder", mod_id="alpha_id")
    _write(src / "enabled_mods.json",
           '{"enabledMods":["zeta_id","alpha_id"]}')
    dst = tmp_path / "dst"
    plan = plan_migrate(src, dst, link=False)
    plan["apply"] = True
    result = apply_migrate(plan)
    assert result["applied"] is True
    assert result["copied"] == 2
    assert (dst / "zeta_folder" / "mod_info.json").is_file()
    assert (dst / "alpha_folder" / "mod_info.json").is_file()
    text = (dst / "enabled_mods.json").read_text(encoding="utf-8")
    assert json.loads(text) == {"enabledMods": ["zeta_id", "alpha_id"]}
    assert text == '{\n  "enabledMods": [\n    "zeta_id",\n    "alpha_id"\n  ]\n}\n'


def test_apply_migrate_rejects_existing_target(tmp_path):
    src = tmp_path / "src"
    _mod(src, "mod_a")
    _write(src / "enabled_mods.json", '{"enabledMods":["mod_a"]}')
    dst = tmp_path / "dst"
    dst.mkdir()
    plan = plan_migrate(src, dst, link=False)
    plan["apply"] = True
    with pytest.raises(FileExistsError):
        apply_migrate(plan)


def test_apply_migrate_refuses_empty_plan(tmp_path):
    plan = {
        "apply": True,
        "source": str(tmp_path / "src"),
        "target": str(tmp_path / "dst"),
        "copy": [],
        "enabled": [],
        "enabled_folders": {},
        "extras": [],
        "missing_enabled_ids": [],
        "link": False,
    }
    with pytest.raises(ValueError):
        apply_migrate(plan)
    assert not (tmp_path / "dst").exists()


def test_apply_migrate_rolls_back_on_copy_failure(tmp_path, monkeypatch):
    src = tmp_path / "src"
    _mod(src, "mod_a")
    _mod(src, "mod_b")
    _write(src / "enabled_mods.json",
           '{"enabledMods":["mod_a","mod_b"]}')
    dst = tmp_path / "dst"
    plan = plan_migrate(src, dst, link=False)
    plan["apply"] = True
    calls = {"count": 0}

    def boom(source, target, *args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("copy failed")
        return shutil.copytree(source, target, *args, **kwargs)

    monkeypatch.setattr("m7_stack.shutil.copytree", boom)
    with pytest.raises(OSError):
        apply_migrate(plan)
    assert not dst.exists()


@pytest.mark.skipif(os.name != "nt", reason="junctions are Windows-only")
def test_apply_migrate_link_creates_junction(tmp_path):
    src = tmp_path / "src"
    _mod(src, "mod_a")
    _write(src / "enabled_mods.json", '{"enabledMods":["mod_a"]}')
    dst = tmp_path / "dst"
    plan = plan_migrate(src, dst, link=True)
    plan["apply"] = True
    result = apply_migrate(plan)
    assert result["applied"] is True
    assert result["link"] is True
    assert (dst / "mod_a" / "mod_info.json").is_file()


@pytest.mark.skipif(os.name != "nt", reason="junctions are Windows-only")
def test_apply_migrate_rolls_back_on_link_failure(tmp_path, monkeypatch):
    src = tmp_path / "src"
    _mod(src, "mod_a")
    _mod(src, "mod_b")
    _write(src / "enabled_mods.json",
           '{"enabledMods":["mod_a","mod_b"]}')
    dst = tmp_path / "dst"
    plan = plan_migrate(src, dst, link=True)
    plan["apply"] = True
    real_run = subprocess.run
    calls = {"count": 0}

    def fake_run(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            return subprocess.CompletedProcess(args[0], 1, "", "mklink boom")
        return real_run(*args, **kwargs)

    monkeypatch.setattr("m7_stack.subprocess.run", fake_run)
    with pytest.raises(RuntimeError):
        apply_migrate(plan)
    assert not dst.exists()


def test_cli_migrate_text_summary(tmp_path, capsys):
    src = tmp_path / "src"
    _mod(src, "mod_a")
    _mod(src, "ChineseInputFix")
    _write(src / "enabled_mods.json", '{"enabledMods":["mod_a"]}')
    rc = main([
        "migrate", "--source", str(src), "--target", str(tmp_path / "dst"),
        "--link", "--text",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "copy=1" in out
    assert "enabled=1" in out
    assert "extras=ChineseInputFix" in out
    assert "link=true" in out


def test_cli_migrate_fails_closed_on_missing_enabled(tmp_path, capsys):
    src = tmp_path / "src"
    _mod(src, "mod_a")
    rc = main([
        "migrate", "--source", str(src), "--target", str(tmp_path / "dst"),
    ])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.err.strip().startswith("FATAL:")
    assert "enabled_mods.json not found" in captured.err
    assert not (tmp_path / "dst").exists()


@pytest.mark.skipif(os.name != "nt", reason="junctions are Windows-only")
def test_cli_migrate_apply_link_keeps_stdout_json(tmp_path, capsys):
    src = tmp_path / "src"
    _mod(src, "mod_a")
    _write(src / "enabled_mods.json", '{"enabledMods":["mod_a"]}')
    rc = main([
        "migrate", "--source", str(src), "--target", str(tmp_path / "dst"),
        "--link", "--apply",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["applied"] is True
    assert "Junction created" not in out


def test_plan_route_b_inserts_flags_before_main_class(tmp_path):
    root = tmp_path / "install"
    _write(root / "vmparams", "java.exe -Xmx2g com.fs.starfarer.StarfarerLauncher\n")
    plan = plan_route_b(root, fr_dir=tmp_path / "fr", jdk_dir=tmp_path / "jdk",
                        hypernova_mod=tmp_path / "hn")
    line = plan["vmparams"]
    assert line.index("-javaagent:") < line.index(
        "com.fs.starfarer.StarfarerLauncher")
    assert "-Dhypernova.textures.lazy=true" in line
    assert "jdk-28+13" in plan["java"]


def test_plan_route_b_is_idempotent(tmp_path):
    root = tmp_path / "install"
    _write(root / "vmparams", "java.exe com.fs.starfarer.StarfarerLauncher\n")
    first = plan_route_b(root, fr_dir=tmp_path / "fr", jdk_dir=tmp_path / "jdk",
                         hypernova_mod=tmp_path / "hn")
    _write(root / "vmparams", first["vmparams"] + "\n")
    second = plan_route_b(root, fr_dir=tmp_path / "fr", jdk_dir=tmp_path / "jdk",
                          hypernova_mod=tmp_path / "hn")
    assert second["vmparams"] == first["vmparams"]


def _route_b_sources(tmp_path, *, enabled=("mod_a", "mod_b")):
    root = tmp_path / "install"
    _write(root / "vmparams",
           "java.exe -Xmx2g -classpath janino.jar "
           "com.fs.starfarer.StarfarerLauncher\n")
    _write(root / "starsector-core/data/config/settings.json", '{"x":1}\n')
    if enabled is not None:
        _write(root / "mods/enabled_mods.json",
               json.dumps({"enabledMods": list(enabled)}))

    fr = tmp_path / "fr"
    (fr / "fr.agent.jar").parent.mkdir(parents=True, exist_ok=True)
    (fr / "fr.agent.jar").write_bytes(b"agent")
    (fr / "fr.jar").write_bytes(b"fr")
    _write(fr / "fr.version.txt", "v0.9.7rc2\n")
    _write(fr / "fr.vmparams",
           "-Xmx4g\n-javaagent:fr.agent.jar\n\n-classpath\nfr.jar\n"
           "com.fs.starfarer.StarfarerLauncher")

    jdk = tmp_path / "jdk"
    _write(jdk / "release",
           'JAVA_VERSION="28"\nJAVA_RUNTIME_VERSION="28-beta+13-ea"\n'
           'IMPLEMENTOR_VERSION="Temurin-28+13-test"\n')
    (jdk / "bin").mkdir(parents=True, exist_ok=True)
    (jdk / "bin/java.exe").write_bytes(b"x")

    hn = tmp_path / "hn"
    _write(hn / "mod_info.json",
           '{"id":"hypernova_infinite_engine"}')
    _write(hn / "data/config/hypernova/hypernova.json", '{"enabled":true}\n')
    (hn / "graphics/hypernova").mkdir(parents=True, exist_ok=True)
    (hn / "graphics/hypernova/blank.png").write_bytes(b"png")
    (hn / "build/java").mkdir(parents=True, exist_ok=True)
    (hn / "build/java/hypernova.jar").write_bytes(b"jar")
    (hn / "build/agent").mkdir(parents=True, exist_ok=True)
    (hn / "build/agent/hypernova.agent.jar").write_bytes(b"agent")
    return root, fr, jdk, hn


def test_plan_route_b_tokenless_argfile_and_explicit_launcher(tmp_path):
    root, fr, jdk, hn = _route_b_sources(tmp_path)
    plan = plan_route_b(root, fr_dir=fr, jdk_dir=jdk, hypernova_mod=hn)
    line = plan["vmparams"]
    first = line.split()[0]
    assert "java.exe" not in first.lower()
    assert "bin\\java" not in first.lower()
    assert line.index("-javaagent:") < line.index(
        "com.fs.starfarer.StarfarerLauncher")
    assert plan["vmparams_tokenless"] is True
    assert plan["root_vmparams_modified"] is False
    assert plan["vmparams_path"].endswith("route-b.vmparams")
    assert plan["root_vmparams_path"].endswith("vmparams")

    launcher = plan["launcher"]
    assert launcher["java"] == "..\\jdk-28+13\\bin\\java.exe"
    assert "..\\jdk-28+13\\bin\\java.exe" in launcher["bat_content"]
    assert "@..\\route-b.vmparams" in launcher["bat_content"]
    assert launcher["bat"].endswith("launch-route-b.bat")
    assert plan["intended_java"]["java_version"] == "28"
    assert plan["effective_java"]["verified"] is False
    assert plan["starsector_exe"]["route_b"] is False
    assert plan["starsector_exe"]["java"] == "..\\jre\\bin\\java.exe"


def test_plan_route_b_prepatcher_agent_order(tmp_path):
    root, fr, jdk, hn = _route_b_sources(tmp_path)
    pp = tmp_path / "pp"
    _write(pp / "mod_info.json", '{"id":"starsector_prepatcher"}')
    (pp / "agent").mkdir(parents=True, exist_ok=True)
    (pp / "agent/StarsectorPrepatcherAgent.jar").write_bytes(b"agent")
    _write(pp / "prepatcher.properties", "enabled=true\npatch.foo=true\n")
    plan = plan_route_b(root, fr_dir=fr, jdk_dir=jdk, hypernova_mod=hn,
                        prepatcher_dir=pp)
    line = plan["vmparams"]
    hypernova = line.index("hypernova.agent.jar")
    fr_agent = line.index("fr.agent.jar")
    prepatcher = line.index("StarsectorPrepatcherAgent.jar")
    assert hypernova < fr_agent < prepatcher
    assert prepatcher < line.index("-classpath")
    assert plan["prepatcher"]["patch_count"] == 1
    assert plan["enabled_mods"]["add"] == [
        "hypernova_infinite_engine", "starsector_prepatcher"]


def test_snapshot_route_rollback_restores_existing_and_deletes_created(tmp_path):
    root = tmp_path / "install"
    _write(root / "vmparams", "original\n")
    _write(root / "keep.txt", "keep\n")
    dest = tmp_path / "backups"
    snapshot_route(root, "label", paths=["vmparams", "keep.txt", "created.txt"],
                   dest=dest)
    _write(root / "vmparams", "changed\n")
    _write(root / "keep.txt", "tampered\n")
    _write(root / "created.txt", "new\n")

    plan = rollback_route(root, "label", dest=dest)
    assert plan["applied"] is False
    assert any(item["action"] == "delete" for item in plan["actions"])
    result = rollback_route(root, "label", dest=dest, apply=True)
    assert result["ok"] is True
    assert (root / "vmparams").read_text(encoding="utf-8") == "original\n"
    assert (root / "keep.txt").read_text(encoding="utf-8") == "keep\n"
    assert not (root / "created.txt").exists()
    assert result["restored"] == 2
    assert result["deleted"] == 1
    again = rollback_route(root, "label", dest=dest, apply=True)
    assert again["restored"] == 0
    assert again["deleted"] == 0


def test_apply_route_b_dry_run_writes_nothing(tmp_path):
    root, fr, jdk, hn = _route_b_sources(tmp_path)
    original = (root / "vmparams").read_text(encoding="utf-8")
    plan = plan_route_b(root, fr_dir=fr, jdk_dir=jdk, hypernova_mod=hn)
    result = apply_route_b(plan)
    assert result["applied"] is False
    assert not (root / "route-b.vmparams").exists()
    assert not (tmp_path / "scripts/launch-route-b.bat").exists()
    assert (root / "vmparams").read_text(encoding="utf-8") == original


def test_apply_route_b_writes_and_rollback_removes_created(tmp_path):
    root, fr, jdk, hn = _route_b_sources(tmp_path)
    original = (root / "vmparams").read_text(encoding="utf-8")
    plan = plan_route_b(root, fr_dir=fr, jdk_dir=jdk, hypernova_mod=hn)
    plan["apply"] = True
    result = apply_route_b(plan)
    assert result["applied"] is True
    assert (root / "route-b.vmparams").is_file()
    first = (root / "route-b.vmparams").read_text(
        encoding="utf-8").split()[0]
    assert "java.exe" not in first.lower()
    assert "bin\\java" not in first.lower()
    assert (tmp_path / "scripts/launch-route-b.bat").is_file()
    assert (root / "vmparams").read_text(encoding="utf-8") == original
    enabled = json.loads(
        (root / "mods/enabled_mods.json").read_text(encoding="utf-8"))
    assert enabled["enabledMods"] == [
        "mod_a", "mod_b", "hypernova_infinite_engine"]
    rollback = result["rollback"]
    assert Path(rollback["manifest"]).is_file()

    rolled = rollback_route(
        root, rollback["label"], dest=rollback["dest"], apply=True)
    assert rolled["ok"] is True
    assert (root / "vmparams").read_text(encoding="utf-8") == original
    assert not (root / "route-b.vmparams").exists()
    assert not (tmp_path / "scripts/launch-route-b.bat").exists()
    assert json.loads(
        (root / "mods/enabled_mods.json").read_text(encoding="utf-8")
    ) == {"enabledMods": ["mod_a", "mod_b"]}
    assert not (root / "mods/hypernova_infinite_engine").exists()
    assert not (root / "starsector-core/fr.jar").exists()
    assert not (root / "jdk-28+13").exists()


def test_apply_route_b_refuses_corrupt_enabled_mods(tmp_path):
    root, fr, jdk, hn = _route_b_sources(tmp_path, enabled=None)
    _write(root / "mods/enabled_mods.json", "{bad json")
    plan = plan_route_b(root, fr_dir=fr, jdk_dir=jdk, hypernova_mod=hn)
    plan["apply"] = True
    with pytest.raises(ValueError):
        apply_route_b(plan)
    assert not (root / "route-b.vmparams").exists()
    assert (root / "mods/enabled_mods.json").read_text(
        encoding="utf-8") == "{bad json"


def test_cli_route_b_apply_failure_returns_nonzero(tmp_path, monkeypatch, capsys):
    root = tmp_path / "install"
    _write(root / "vmparams", "java.exe com.fs.starfarer.StarfarerLauncher\n")

    def fake_apply(plan):
        return {"applied": True, "ok": False, "root": str(root),
                "manifest": {"critical": ["missing_jar"]},
                "agent": {"returncode": 1},
                "rollback": {"label": "rollback-label"}}

    monkeypatch.setattr("m7_stack.apply_route_b", fake_apply)
    rc = main([
        "route-b", "--root", str(root), "--fr-dir", str(tmp_path / "fr"),
        "--jdk-dir", str(tmp_path / "jdk"),
        "--hypernova-mod", str(tmp_path / "hn"), "--apply", "--text",
    ])
    captured = capsys.readouterr()
    assert rc == 1
    assert "FATAL: route-b apply failed" in captured.err
    assert "rollback-label" in captured.err


def test_cli_route_b_text_and_json_out(tmp_path, capsys):
    root, fr, jdk, hn = _route_b_sources(tmp_path)
    out = tmp_path / "evidence/route-b-plan.json"
    rc = main([
        "route-b", "--root", str(root), "--fr-dir", str(fr),
        "--jdk-dir", str(jdk), "--hypernova-mod", str(hn),
        "--text", "--json-out", str(out),
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert "launcher.java=..\\jdk-28+13\\bin\\java.exe" in captured.out
    assert out.is_file()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["vmparams_tokenless"] is True
    assert data["root_vmparams_modified"] is False


# ---- 路线 A（Task 4）：MixinFR 1.2.5 + JRE 17 + StarsectorParallel ----


def test_plan_route_a_has_two_agents_and_jre17(tmp_path):
    root = tmp_path / "install"
    _write(root / "vmparams", "java.exe com.fs.starfarer.StarfarerLauncher\n")
    plan = plan_route_a(root, mixinfr_dir=tmp_path / "mixin",
                        parallel_dir=tmp_path / "par",
                        hypernova_mod=tmp_path / "hn")
    line = plan["vmparams"]
    agents = [tok for tok in line.split() if tok.startswith("-javaagent:")]
    assert len(agents) == 2
    assert any("MixinLib-bridge.jar" in a for a in agents)
    # 实际工时 jar 名为 hypernova.agent.jar（点号）；brief 里的
    # "hypernova-agent.jar" 是笔误，按真实工件修正。
    assert any("hypernova.agent.jar" in a for a in agents)
    assert "jdk-28" not in plan["java"]


def test_plan_route_a_rejects_mixing_fr097(tmp_path):
    root = tmp_path / "install"
    _write(root / "vmparams", "java.exe com.fs.starfarer.StarfarerLauncher\n")
    (root / "starsector-core").mkdir(parents=True)
    (root / "starsector-core/fr.jar").write_bytes(b"x")
    with pytest.raises(ValueError):
        plan_route_a(root, mixinfr_dir=tmp_path / "mixin",
                     parallel_dir=tmp_path / "par",
                     hypernova_mod=tmp_path / "hn")


@pytest.mark.parametrize("vmparams", [
    "java.exe -javaagent:fr.agent.jar "
    "com.fs.starfarer.StarfarerLauncher\n",
    "java.exe -classpath fr.jar;janino.jar "
    "com.fs.starfarer.StarfarerLauncher\n",
])
def test_plan_route_a_rejects_vmparams_fr097_tokens(tmp_path, vmparams):
    root = tmp_path / "install"
    _write(root / "vmparams", vmparams)
    with pytest.raises(ValueError, match="FR 0.9.7"):
        plan_route_a(root, mixinfr_dir=tmp_path / "mixin",
                     parallel_dir=tmp_path / "par",
                     hypernova_mod=tmp_path / "hn")


@pytest.mark.parametrize("vmparams", [
    "java.exe com.fs.starfarer.StarfarerLauncher\n",
    "java.exe -javaagent:..\\mods\\StarsectorPrepatcher\\agent\\"
    "StarsectorPrepatcherAgent.jar com.fs.starfarer.StarfarerLauncher\n",
])
def test_plan_route_a_rejects_prepatcher(tmp_path, vmparams):
    root = tmp_path / "install"
    _write(root / "vmparams", vmparams)
    if "-javaagent:" not in vmparams:
        (root / "mods/StarsectorPrepatcher").mkdir(parents=True)
    with pytest.raises(ValueError, match="Prepatcher"):
        plan_route_a(root, mixinfr_dir=tmp_path / "mixin",
                     parallel_dir=tmp_path / "par",
                     hypernova_mod=tmp_path / "hn")


def test_plan_route_a_tokenless_ordered_agents_and_jre_launcher(tmp_path):
    root = tmp_path / "install"
    _write(root / "vmparams",
           "java.exe -Xmx2g -classpath janino.jar "
           "com.fs.starfarer.StarfarerLauncher\n")
    plan = plan_route_a(root, mixinfr_dir=tmp_path / "mixin",
                        parallel_dir=tmp_path / "par",
                        hypernova_mod=tmp_path / "hn")
    line = plan["vmparams"]
    first = line.split()[0]
    assert "java.exe" not in first.lower()
    assert line.index("MixinLib-bridge.jar") < line.index(
        "hypernova.agent.jar")
    assert line.index("hypernova.agent.jar") < line.index("-classpath")
    assert plan["vmparams_tokenless"] is True
    assert plan["root_vmparams_modified"] is False
    assert plan["vmparams_path"].endswith("route-a.vmparams")
    assert plan["root_vmparams_path"].endswith("vmparams")
    assert plan["launcher"]["java"] == "..\\jre\\bin\\java.exe"
    assert "@..\\route-a.vmparams" in plan["launcher"]["bat_content"]
    assert plan["launcher"]["bat"].endswith("launch-route-a.bat")


def _route_a_sources(tmp_path, *, enabled=("mod_a",)):
    root = tmp_path / "install"
    _write(root / "vmparams",
           "java.exe -Xmx2g -classpath janino.jar "
           "com.fs.starfarer.StarfarerLauncher\n")
    _write(root / "starsector-core/data/config/settings.json", '{"x":1}\n')
    _write(root / "jre/release", 'JAVA_VERSION="17.0.10"\n')
    (root / "jre/bin").mkdir(parents=True, exist_ok=True)
    (root / "jre/bin/java.exe").write_bytes(b"x")
    if enabled is not None:
        _write(root / "mods/enabled_mods.json",
               json.dumps({"enabledMods": list(enabled)}))

    mixin = tmp_path / "mixin"
    _write(mixin / "mod_info.json", '{"id":"MixinLib","version":"1.2.5"}')
    (mixin / "jars").mkdir(parents=True, exist_ok=True)
    (mixin / "jars/MixinLib-bridge.jar").write_bytes(b"agent")
    (mixin / "jars/fr.jar").write_bytes(b"fr-0.9.5")

    par = tmp_path / "par"
    _write(par / "mod_info.json",
           '{"id":"starsectorparallel","version":"0.1.0"}')
    (par / "jars").mkdir(parents=True, exist_ok=True)
    (par / "jars/starsectorparallel.jar").write_bytes(b"par")

    hn = tmp_path / "hn"
    _write(hn / "mod_info.json", '{"id":"hypernova_infinite_engine"}')
    _write(hn / "data/config/hypernova/hypernova.json", '{"enabled":true}\n')
    (hn / "graphics/hypernova").mkdir(parents=True, exist_ok=True)
    (hn / "graphics/hypernova/blank.png").write_bytes(b"png")
    (hn / "build/java").mkdir(parents=True, exist_ok=True)
    (hn / "build/java/hypernova.jar").write_bytes(b"jar")
    (hn / "build/agent").mkdir(parents=True, exist_ok=True)
    (hn / "build/agent/hypernova.agent.jar").write_bytes(b"agent")
    return root, mixin, par, hn


def test_plan_route_a_enabled_mods_ordered_after_hypernova(tmp_path):
    root, mixin, par, hn = _route_a_sources(tmp_path)
    plan = plan_route_a(root, mixinfr_dir=mixin, parallel_dir=par,
                        hypernova_mod=hn)
    enabled = plan["enabled_mods"]
    assert enabled["add"] == [
        "hypernova_infinite_engine", "MixinLib", "starsectorparallel"]
    assert enabled["order"] == [
        "mod_a", "hypernova_infinite_engine", "MixinLib",
        "starsectorparallel"]
    assert plan["mixinfr"]["id"] == "MixinLib"
    assert plan["parallel"]["id"] == "starsectorparallel"


def test_plan_route_a_skips_unverified_mod_ids(tmp_path):
    root = tmp_path / "install"
    _write(root / "vmparams", "java.exe com.fs.starfarer.StarfarerLauncher\n")
    _write(root / "mods/enabled_mods.json", '{"enabledMods":["mod_a"]}')
    plan = plan_route_a(root, mixinfr_dir=tmp_path / "mixin",
                        parallel_dir=tmp_path / "par",
                        hypernova_mod=tmp_path / "hn")
    assert plan["enabled_mods"]["add"] == []
    assert plan["enabled_mods"]["order"] == ["mod_a"]


def test_apply_route_a_dry_run_writes_nothing(tmp_path):
    root, mixin, par, hn = _route_a_sources(tmp_path)
    original = (root / "vmparams").read_text(encoding="utf-8")
    plan = plan_route_a(root, mixinfr_dir=mixin, parallel_dir=par,
                        hypernova_mod=hn)
    result = apply_route_a(plan)
    assert result["applied"] is False
    assert not (root / "route-a.vmparams").exists()
    assert not (tmp_path / "scripts/launch-route-a.bat").exists()
    assert (root / "vmparams").read_text(encoding="utf-8") == original


def test_apply_route_a_writes_and_rollback_removes_created(tmp_path):
    root, mixin, par, hn = _route_a_sources(tmp_path)
    original = (root / "vmparams").read_text(encoding="utf-8")
    plan = plan_route_a(root, mixinfr_dir=mixin, parallel_dir=par,
                        hypernova_mod=hn)
    plan["apply"] = True
    result = apply_route_a(plan)
    assert result["applied"] is True
    assert (root / "route-a.vmparams").is_file()
    assert (tmp_path / "scripts/launch-route-a.bat").is_file()
    assert (root / "mods/MixinFR/jars/MixinLib-bridge.jar").is_file()
    assert (root / "mods/StarsectorParallel/mod_info.json").is_file()
    assert (root / "vmparams").read_text(encoding="utf-8") == original
    enabled = json.loads(
        (root / "mods/enabled_mods.json").read_text(encoding="utf-8"))
    assert enabled["enabledMods"] == [
        "mod_a", "hypernova_infinite_engine", "MixinLib",
        "starsectorparallel"]

    rollback = result["rollback"]
    assert Path(rollback["manifest"]).is_file()
    rolled = rollback_route(
        root, rollback["label"], dest=rollback["dest"], apply=True)
    assert rolled["ok"] is True
    assert not (root / "route-a.vmparams").exists()
    assert not (tmp_path / "scripts/launch-route-a.bat").exists()
    assert not (root / "mods/MixinFR").exists()
    assert not (root / "mods/StarsectorParallel").exists()
    assert not (root / "mods/hypernova_infinite_engine").exists()
    assert (root / "vmparams").read_text(encoding="utf-8") == original
    assert json.loads(
        (root / "mods/enabled_mods.json").read_text(encoding="utf-8")
    ) == {"enabledMods": ["mod_a"]}


def test_cli_route_a_text_summary(tmp_path, capsys):
    root, mixin, par, hn = _route_a_sources(tmp_path)
    rc = main([
        "route-a", "--root", str(root), "--mixinfr", str(mixin),
        "--parallel", str(par), "--hypernova-mod", str(hn), "--text",
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert "route=a" in captured.out
    assert "launcher.java=..\\jre\\bin\\java.exe" in captured.out
    assert "agents=" in captured.out


# ---- 短路、回滚与日志收集（Task 5）----


def test_disable_ime_plan_renames_dll(tmp_path):
    root = tmp_path / "install"
    (root / "starsector-core/native/windows").mkdir(parents=True)
    (root / "starsector-core/native/windows/ssime.dll").write_bytes(b"x")
    plan = plan_disable_ime(root)
    assert plan["rename"] == [("ssime.dll", "ssime.dll.disabled")]
    assert plan["apply"] is False


def test_collect_logs_copies_existing_only(tmp_path):
    root = tmp_path / "install"
    (root / "starsector-core").mkdir(parents=True)
    (root / "starsector-core/starsector.log").write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    report = collect_logs(root, out)
    assert (out / "starsector.log").is_file()
    assert "mixinlib.log" in report["missing"]


def _ime_install(tmp_path):
    root = tmp_path / "install"
    (root / "starsector-core/native/windows").mkdir(parents=True)
    (root / "starsector-core/native/windows/ssime.dll").write_bytes(b"x")
    _write(root / "mods/enabled_mods.json", '{"enabledMods":["mod_a"]}')
    cif_src = tmp_path / "cif"
    _write(cif_src / "mod_info.json", '{"id":"ChineseInputFix"}')
    return root, cif_src


def test_plan_disable_ime_requires_cif_before_enabling(tmp_path):
    root, cif_src = _ime_install(tmp_path)
    plan = plan_disable_ime(root, cif_source=cif_src)
    assert plan["cif"]["verified"] is True
    assert plan["cif"]["need_copy"] is True
    assert plan["enabled_mods"]["add"] == ["ChineseInputFix"]
    assert plan["enabled_mods"]["state"] == "ok"


def test_apply_disable_ime_renames_enables_cif_and_rolls_back(tmp_path):
    root, cif_src = _ime_install(tmp_path)
    plan = plan_disable_ime(root, cif_source=cif_src)
    plan["apply"] = True
    result = apply_disable_ime(plan)
    assert result["changed"] is True
    assert not (root / "starsector-core/native/windows/ssime.dll").exists()
    assert (root / "starsector-core/native/windows/ssime.dll.disabled").is_file()
    assert (root / "mods/ChineseInputFix/mod_info.json").is_file()
    assert json.loads(
        (root / "mods/enabled_mods.json").read_text(encoding="utf-8")
    ) == {"enabledMods": ["mod_a", "ChineseInputFix"]}

    rolled = rollback_route(
        root, result["rollback"]["label"], dest=result["rollback"]["dest"],
        apply=True)
    assert rolled["ok"] is True
    assert (root / "starsector-core/native/windows/ssime.dll").is_file()
    assert not (root / "starsector-core/native/windows/ssime.dll.disabled").exists()
    assert not (root / "mods/ChineseInputFix").exists()
    assert json.loads(
        (root / "mods/enabled_mods.json").read_text(encoding="utf-8")
    ) == {"enabledMods": ["mod_a"]}


def test_apply_disable_ime_refuses_missing_cif_source(tmp_path):
    root, _ = _ime_install(tmp_path)
    plan = plan_disable_ime(root, cif_source=tmp_path / "missing-cif")
    assert plan["cif"]["verified"] is False
    plan["apply"] = True
    with pytest.raises((FileNotFoundError, ValueError)):
        apply_disable_ime(plan)
    assert (root / "starsector-core/native/windows/ssime.dll").is_file()
    assert json.loads(
        (root / "mods/enabled_mods.json").read_text(encoding="utf-8")
    ) == {"enabledMods": ["mod_a"]}


def test_disable_ime_is_idempotent(tmp_path):
    root, cif_src = _ime_install(tmp_path)
    first = plan_disable_ime(root, cif_source=cif_src)
    first["apply"] = True
    apply_disable_ime(first)

    second = plan_disable_ime(root, cif_source=cif_src)
    assert second["rename"] == []
    assert second["enabled_mods"]["add"] == []
    second["apply"] = True
    result = apply_disable_ime(second)
    assert result["changed"] is False
    assert (root / "starsector-core/native/windows/ssime.dll.disabled").is_file()


def test_apply_disable_ime_snapshots_before_writes(tmp_path, monkeypatch):
    root, cif_src = _ime_install(tmp_path)
    plan = plan_disable_ime(root, cif_source=cif_src)
    plan["apply"] = True

    def boom(*args, **kwargs):
        raise RuntimeError("snapshot boom")

    monkeypatch.setattr("m7_stack.snapshot_route", boom)
    with pytest.raises(RuntimeError, match="snapshot boom"):
        apply_disable_ime(plan)
    assert (root / "starsector-core/native/windows/ssime.dll").is_file()
    assert not (root / "starsector-core/native/windows/ssime.dll.disabled").exists()
    assert not (root / "mods/ChineseInputFix").exists()
    assert json.loads(
        (root / "mods/enabled_mods.json").read_text(encoding="utf-8")
    ) == {"enabledMods": ["mod_a"]}


def test_plan_disable_mixinfr_fonts_reports_no_switch(tmp_path):
    root = tmp_path / "install"
    _write(root / "mods/MixinFR/mod_info.json",
           '{"id":"MixinLib","version":"1.2.5"}')
    plan = plan_disable_mixinfr_fonts(root)
    assert plan["applicable"] is True
    assert plan["version"] == "1.2.5"
    assert plan["switch_available"] is False
    assert plan["writes"] == []
    assert "1.2.5" in plan["recommendation"]
    plan["apply"] = True
    result = apply_disable_mixinfr_fonts(plan)
    assert result["applied"] is False
    assert result["changed"] is False


def test_plan_disable_mixinfr_fonts_missing_mod_info(tmp_path):
    root = tmp_path / "install"
    (root / "mods/MixinFR").mkdir(parents=True)
    plan = plan_disable_mixinfr_fonts(root)
    assert plan["applicable"] is True
    assert plan["version"] is None


def test_disable_mixinfr_fonts_edits_explicit_switch_and_rolls_back(tmp_path):
    root = tmp_path / "install"
    _write(root / "mods/MixinFR/mod_info.json",
           '{"id":"MixinLib","version":"1.2.5"}')
    switch = root / "mods/MixinFR/mixinfr.font.json"
    _write(switch, '{"FrFontHd": true}\n')
    plan = plan_disable_mixinfr_fonts(root)
    assert plan["switch_available"] is True
    assert len(plan["writes"]) == 1
    plan["apply"] = True
    result = apply_disable_mixinfr_fonts(plan)
    assert result["changed"] is True
    assert json.loads(switch.read_text(encoding="utf-8")) == {"FrFontHd": False}

    rolled = rollback_route(
        root, result["rollback"]["label"], dest=result["rollback"]["dest"],
        apply=True)
    assert rolled["ok"] is True
    assert json.loads(switch.read_text(encoding="utf-8")) == {"FrFontHd": True}


def test_collect_logs_finds_agent_log_under_saves(tmp_path):
    root = tmp_path / "install"
    _write(root / "saves/hypernova/scripts-agent.log", "agent")
    out = tmp_path / "out"
    report = collect_logs(root, out)
    assert report["copied"] == ["scripts-agent.log"]
    assert (out / "scripts-agent.log").read_text(encoding="utf-8") == "agent"


def test_cli_rollback_apply_restores_snapshot(tmp_path, capsys):
    root = tmp_path / "install"
    _write(root / "vmparams", "original\n")
    dest = tmp_path / "backups"
    snapshot_route(root, "label", paths=["vmparams"], dest=dest)
    _write(root / "vmparams", "changed\n")

    rc = main([
        "rollback", "--root", str(root), "--label", "label",
        "--backups", str(dest), "--apply", "--text",
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert "restored=1" in captured.out
    assert (root / "vmparams").read_text(encoding="utf-8") == "original\n"


# ---- Task 5 fix loop 1 ----


def test_plan_disable_mixinfr_fonts_relative_root_apply_rollback(
    tmp_path, monkeypatch
):
    root = tmp_path / "install"
    _write(root / "mods/MixinFR/mod_info.json",
           '{"id":"MixinLib","version":"1.2.5"}')
    switch = root / "mods/MixinFR/mixinfr.font.json"
    _write(switch, '{"FrFontHd": true}\n')
    monkeypatch.chdir(tmp_path)

    plan = plan_disable_mixinfr_fonts(Path("install"))
    assert Path(plan["writes"][0]["path"]).is_absolute()
    assert Path(plan["snapshot"]["paths"][0]).is_absolute()

    plan["apply"] = True
    result = apply_disable_mixinfr_fonts(plan)
    assert result["changed"] is True
    assert json.loads(switch.read_text(encoding="utf-8")) == {"FrFontHd": False}

    rolled = rollback_route(
        Path("install"), result["rollback"]["label"],
        dest=result["rollback"]["dest"], apply=True)
    assert rolled["ok"] is True
    assert rolled["restored"] > 0
    assert json.loads(switch.read_text(encoding="utf-8")) == {"FrFontHd": True}


def test_apply_disable_ime_refuses_missing_enabled_mods(tmp_path):
    root = tmp_path / "install"
    (root / "starsector-core/native/windows").mkdir(parents=True)
    (root / "starsector-core/native/windows/ssime.dll").write_bytes(b"x")
    cif_src = tmp_path / "cif"
    _write(cif_src / "mod_info.json", '{"id":"ChineseInputFix"}')

    plan = plan_disable_ime(root, cif_source=cif_src)
    assert plan["apply_blocked"] is True
    plan["apply"] = True
    with pytest.raises(ValueError, match="enabled_mods.json"):
        apply_disable_ime(plan)
    assert (root / "starsector-core/native/windows/ssime.dll").is_file()
    assert not (root / "mods/ChineseInputFix").exists()


def test_apply_disable_ime_refuses_corrupt_enabled_mods(tmp_path):
    root = tmp_path / "install"
    (root / "starsector-core/native/windows").mkdir(parents=True)
    (root / "starsector-core/native/windows/ssime.dll").write_bytes(b"x")
    _write(root / "mods/enabled_mods.json", "{bad json")
    cif_src = tmp_path / "cif"
    _write(cif_src / "mod_info.json", '{"id":"ChineseInputFix"}')

    plan = plan_disable_ime(root, cif_source=cif_src)
    assert plan["apply_blocked"] is True
    plan["apply"] = True
    with pytest.raises(ValueError, match="enabled_mods.json"):
        apply_disable_ime(plan)
    assert (root / "starsector-core/native/windows/ssime.dll").is_file()
    assert (root / "mods/enabled_mods.json").read_text(
        encoding="utf-8") == "{bad json"


def test_apply_disable_ime_auto_rolls_back_on_write_failure(
    tmp_path, monkeypatch
):
    root, cif_src = _ime_install(tmp_path)
    plan = plan_disable_ime(root, cif_source=cif_src)
    plan["apply"] = True
    real = m7_stack._apply_enabled_mods

    def boom(*args, **kwargs):
        real(*args, **kwargs)
        raise RuntimeError("enabled write boom")

    monkeypatch.setattr("m7_stack._apply_enabled_mods", boom)
    with pytest.raises(RuntimeError, match="enabled write boom"):
        apply_disable_ime(plan)

    assert (root / "starsector-core/native/windows/ssime.dll").is_file()
    assert not (root / "starsector-core/native/windows/ssime.dll.disabled").exists()
    assert not (root / "mods/ChineseInputFix").exists()
    assert json.loads(
        (root / "mods/enabled_mods.json").read_text(encoding="utf-8")
    ) == {"enabledMods": ["mod_a"]}


def test_plan_disable_mixinfr_fonts_reports_unreadable_config(tmp_path):
    root = tmp_path / "install"
    _write(root / "mods/MixinFR/mod_info.json",
           '{"id":"MixinLib","version":"1.2.5"}')
    _write(root / "mods/MixinFR/mixinfr.font.json", "{bad json")

    plan = plan_disable_mixinfr_fonts(root)
    assert plan["config_unreadable"] is True
    assert plan["parse_errors"]
    assert plan["switch_available"] is False
    assert any("parse" in item.lower() or "unreadable" in item.lower()
               for item in plan["warnings"])


# ---- Task 7 fix loop 1 ----


def test_route_a_relative_root_rollback_removes_created_mods_and_blank(
    tmp_path, monkeypatch
):
    root, mixin, par, hn = _route_a_sources(tmp_path)
    monkeypatch.chdir(tmp_path)
    plan = plan_route_a(Path("install"), mixinfr_dir=mixin,
                        parallel_dir=par, hypernova_mod=hn)
    plan["apply"] = True
    result = apply_route_a(plan)
    assert result["applied"] is True

    manifest_path = Path(result["rollback"]["manifest"])
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))["entries"]
    paths = {Path(entry["path"]) for entry in entries}
    assert (root / "mods/MixinFR").resolve() in paths
    assert (root / "mods/StarsectorParallel").resolve() in paths
    assert (root / "mods/hypernova_infinite_engine").resolve() in paths
    assert (root / "starsector-core/graphics/hypernova/blank.png").resolve() in paths
    root_abs = str(root.resolve())
    for entry in entries:
        path = Path(entry["path"])
        if path.is_relative_to(root.resolve()):
            # No duplicated root prefix (install/install/...).
            assert str(path).count(root_abs) == 1, entry["path"]

    rolled = rollback_route(
        Path("install"), result["rollback"]["label"],
        dest=result["rollback"]["dest"], apply=True)
    assert rolled["ok"] is True
    assert not (root / "mods/MixinFR").exists()
    assert not (root / "mods/StarsectorParallel").exists()
    assert not (root / "mods/hypernova_infinite_engine").exists()
    assert not (root / "starsector-core/graphics/hypernova/blank.png").exists()


def test_plan_route_b_removes_java17_flags_and_applies_memory(tmp_path):
    root, fr, jdk, hn = _route_b_sources(tmp_path)
    _write(
        root / "vmparams",
        "java.exe -noverify -XX:+UseXMMForArrayCopy "
        "-XX:+ParallelRefProcEnabled -XX:+AlwaysAtomicAccesses "
        "-XX:+UseVectorStubs -XX:ShenandoahGCMode=iu --enable-preview "
        "-Xms2g -Xmx2g -classpath janino.jar "
        "com.fs.starfarer.StarfarerLauncher\n",
    )
    plan = plan_route_b(root, fr_dir=fr, jdk_dir=jdk, hypernova_mod=hn,
                        xms="8G", xmx="10G")
    tokens = plan["vmparams"].split()
    for removed in (
        "-noverify",
        "-XX:+UseXMMForArrayCopy",
        "-XX:+ParallelRefProcEnabled",
        "-XX:+AlwaysAtomicAccesses",
        "-XX:+UseVectorStubs",
        "-XX:ShenandoahGCMode=iu",
        "--enable-preview",
    ):
        assert removed not in tokens
    assert "-Xms8G" in tokens
    assert "-Xmx10G" in tokens
    assert "-Xms2g" not in tokens
    assert "-Xmx2g" not in tokens
    assert plan["memory"] == {
        "xms": "8G", "xmx": "10G", "overridden": True, "source": "override",
    }
    assert len(plan["java28_removed_tokens"]) == 7
    assert tokens.index("-Xms8G") < tokens.index("-classpath")
    agent_index = next(
        index for index, token in enumerate(tokens)
        if token.startswith("-javaagent:"))
    assert agent_index < tokens.index("com.fs.starfarer.StarfarerLauncher")


def test_plan_route_b_rejects_invalid_xmx(tmp_path):
    root, fr, jdk, hn = _route_b_sources(tmp_path)
    with pytest.raises(ValueError, match="invalid xmx"):
        plan_route_b(root, fr_dir=fr, jdk_dir=jdk, hypernova_mod=hn,
                     xmx="lots")


def test_plan_route_b_prechecks_ddscache_and_lunalib(tmp_path):
    root, fr, jdk, hn = _route_b_sources(tmp_path)
    plan = plan_route_b(root, fr_dir=fr, jdk_dir=jdk, hypernova_mod=hn)
    assert plan["ddscache"]["present"] is False
    assert plan["ddscache"]["will_create"] is True
    assert str(root / "mods/DDSCache") in plan["ensure_dirs"]
    assert str(root / "mods/DDSCache") in plan["rollback_paths"]
    assert any("DDSCache" in warning for warning in plan["warnings"])
    assert plan["lunalib_settings"]["present"] is False
    assert any("LunaLib" in warning for warning in plan["warnings"])

    # The known first-run corruption: every mod file has identical content.
    _write(root / "saves/common/LunaSettings/a.json.data", '{"same":1}')
    _write(root / "saves/common/LunaSettings/b.json.data", '{"same":1}')
    suspicious = plan_route_b(root, fr_dir=fr, jdk_dir=jdk, hypernova_mod=hn)
    assert suspicious["lunalib_settings"]["suspicious"] is True
    assert suspicious["lunalib_settings"]["file_count"] == 2
    assert suspicious["lunalib_settings"]["unique_hashes"] == 1
    assert any("corrupt" in warning for warning in suspicious["warnings"])

    _write(root / "saves/common/LunaSettings/b.json.data", '{"different":2}')
    healthy = plan_route_b(root, fr_dir=fr, jdk_dir=jdk, hypernova_mod=hn)
    assert healthy["lunalib_settings"]["suspicious"] is False
    assert healthy["lunalib_settings"]["unique_hashes"] == 2

    healthy["apply"] = True
    result = apply_route_b(healthy)
    assert result["applied"] is True
    assert (root / "mods/DDSCache").is_dir()
    assert result["created_dirs"] == [str(root / "mods/DDSCache")]

    rolled = rollback_route(
        root, result["rollback"]["label"],
        dest=result["rollback"]["dest"], apply=True)
    assert rolled["ok"] is True
    assert not (root / "mods/DDSCache").exists()


# ---- 终审 must-fix：fail-closed / 单参数内存 / 版本断言 ----


def test_apply_route_b_refuses_missing_enabled_mods(tmp_path, capsys):
    root, fr, jdk, hn = _route_b_sources(tmp_path, enabled=None)
    plan = plan_route_b(root, fr_dir=fr, jdk_dir=jdk, hypernova_mod=hn)
    assert plan["enabled_mods"]["state"] == "missing"
    assert any("enabled_mods.json missing" in warning
               for warning in plan["warnings"])
    plan["apply"] = True
    with pytest.raises(ValueError, match="enabled_mods.json"):
        apply_route_b(plan)
    assert not (root / "route-b.vmparams").exists()
    assert not (root / "mods/enabled_mods.json").exists()
    assert not (tmp_path / "scripts/launch-route-b.bat").exists()

    rc = main([
        "route-b", "--root", str(root), "--fr-dir", str(fr),
        "--jdk-dir", str(jdk), "--hypernova-mod", str(hn),
        "--apply", "--text",
    ])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.err.startswith("FATAL:")
    assert "enabled_mods.json" in captured.err
    assert not (root / "route-b.vmparams").exists()
    assert not (root / "mods/enabled_mods.json").exists()


def test_apply_route_a_refuses_missing_enabled_mods(tmp_path, capsys):
    root, mixin, par, hn = _route_a_sources(tmp_path, enabled=None)
    plan = plan_route_a(root, mixinfr_dir=mixin, parallel_dir=par,
                        hypernova_mod=hn)
    assert plan["enabled_mods"]["state"] == "missing"
    assert any("enabled_mods.json missing" in warning
               for warning in plan["warnings"])
    plan["apply"] = True
    with pytest.raises(ValueError, match="enabled_mods.json"):
        apply_route_a(plan)
    assert not (root / "route-a.vmparams").exists()
    assert not (root / "mods/enabled_mods.json").exists()
    assert not (tmp_path / "scripts/launch-route-a.bat").exists()

    rc = main([
        "route-a", "--root", str(root), "--mixinfr", str(mixin),
        "--parallel", str(par), "--hypernova-mod", str(hn),
        "--apply", "--text",
    ])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.err.startswith("FATAL:")
    assert "enabled_mods.json" in captured.err
    assert not (root / "route-a.vmparams").exists()
    assert not (root / "mods/enabled_mods.json").exists()


@pytest.mark.parametrize("kwargs, expected_xms, expected_xmx", [
    ({"xms": "8G"}, "8G", "4g"),
    ({"xmx": "10G"}, "2g", "10G"),
])
def test_plan_route_b_single_memory_override_preserves_other(
        tmp_path, kwargs, expected_xms, expected_xmx):
    root, fr, jdk, hn = _route_b_sources(tmp_path)
    _write(root / "vmparams",
           "java.exe -Xms2g -Xmx4g -classpath janino.jar "
           "com.fs.starfarer.StarfarerLauncher\n")
    plan = plan_route_b(root, fr_dir=fr, jdk_dir=jdk, hypernova_mod=hn,
                        **kwargs)
    tokens = plan["vmparams"].split()
    assert f"-Xms{expected_xms}" in tokens
    assert f"-Xmx{expected_xmx}" in tokens
    if "xms" in kwargs:
        assert "-Xms2g" not in tokens   # 显式项被替换
        assert "-Xmx4g" in tokens       # 另一项保留源值
    else:
        assert "-Xmx4g" not in tokens
        assert "-Xms2g" in tokens
    assert plan["memory"]["xms"] == expected_xms
    assert plan["memory"]["xmx"] == expected_xmx
    assert plan["memory"]["overridden"] is True
    assert plan["memory"]["source"] == "override"


def test_plan_route_b_space_separated_memory_override(tmp_path):
    root, fr, jdk, hn = _route_b_sources(tmp_path)
    _write(root / "vmparams",
           "java.exe -Xms 2g -Xmx 4g -classpath janino.jar "
           "com.fs.starfarer.StarfarerLauncher\n")
    plan = plan_route_b(root, fr_dir=fr, jdk_dir=jdk, hypernova_mod=hn,
                        xms="8G")
    tokens = plan["vmparams"].split()
    assert "-Xms8G" in tokens
    assert "-Xmx4g" in tokens
    assert "2g" not in tokens
    assert "4g" not in tokens   # 被合并成 -Xmx4g
    assert plan["memory"]["xms"] == "8G"
    assert plan["memory"]["xmx"] == "4g"


@pytest.mark.parametrize("device, payload, label, expected", [
    ("mixinfr", '{"id":"MixinLib","version":"1.2.4"}', "MixinFR", "1.2.5"),
    ("parallel", '{"id":"starsectorparallel","version":"0.0.9"}',
     "StarsectorParallel", "0.1.0"),
])
def test_route_a_warns_on_unexpected_version(
        tmp_path, device, payload, label, expected):
    root, mixin, par, hn = _route_a_sources(tmp_path)
    target = mixin if device == "mixinfr" else par
    _write(target / "mod_info.json", payload)
    plan = plan_route_a(root, mixinfr_dir=mixin, parallel_dir=par,
                        hypernova_mod=hn)
    check = plan[device]
    assert check["expected_version"] == expected
    assert check["version_ok"] is False
    warnings = [warning for warning in plan["warnings"]
                if warning.startswith("WARNING:")]
    assert any(label in warning and expected in warning
               for warning in warnings)

    plan["apply"] = True
    result = apply_route_a(plan)
    assert any(label in warning and expected in warning
               for warning in result["warnings"])
    assert result[device]["version_ok"] is False


def test_route_a_text_shows_version_checks(tmp_path, capsys):
    root, mixin, par, hn = _route_a_sources(tmp_path)
    rc = main([
        "route-a", "--root", str(root), "--mixinfr", str(mixin),
        "--parallel", str(par), "--hypernova-mod", str(hn), "--text",
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert "mixinfr.version=1.2.5" in captured.out
    assert "mixinfr.version_ok=true" in captured.out
    assert "parallel.version=0.1.0" in captured.out
    assert "parallel.version_ok=true" in captured.out
