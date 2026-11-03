import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from m7_stack import (
    apply_migrate,
    inspect_root,
    main,
    plan_migrate,
    plan_route_b,
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
