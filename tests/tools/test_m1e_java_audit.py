import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("m1e_java_audit", REPO / "tools" / "m1e_java_audit.py")
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)


def _class(major: int) -> bytes:
    return b"\xca\xfe\xba\xbe" + (0).to_bytes(2, "big") + major.to_bytes(2, "big") + b"\x00" * 4


def test_class_major_reads_header():
    assert audit.class_major(_class(61)) == 61


def test_class_major_rejects_bad_magic():
    with pytest.raises(ValueError, match="magic"):
        audit.class_major(b"\x00\x00\x00\x00" + b"\x00" * 4)


def test_class_major_rejects_short_file():
    with pytest.raises(ValueError, match="short"):
        audit.class_major(b"\xca\xfe\xba")


def test_scan_class_dir_reports_all(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "A.class").write_bytes(_class(61))
    (pkg / "B.class").write_bytes(_class(65))
    got = {p.name: m for p, m in audit.scan_class_dir(tmp_path)}
    assert got == {"A.class": 61, "B.class": 65}


def test_scan_jar(tmp_path):
    jar = tmp_path / "x.jar"
    with zipfile.ZipFile(jar, "w") as z:
        z.writestr("pkg/A.class", _class(52))
    assert audit.scan_jar(jar) == [("pkg/A.class", 52)]


def test_audit_text_detects_java21_apis():
    hits = audit.audit_text(
        "java/util/SequencedCollection\n"
        "// Method java/lang/Math.clamp:(JII)J\n"
        "java/lang/Thread.ofVirtual")
    assert "java/util/SequencedCollection" in hits
    assert any("clamp" in h for h in hits)
    assert any("ofVirtual" in h for h in hits)


def test_audit_text_ignores_java17_code():
    assert audit.audit_text("java/util/ArrayList\nMath.max\nThread.currentThread") == []


def test_cli_fails_on_wrong_major(tmp_path):
    pkg = tmp_path / "classes" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "A.class").write_bytes(_class(65))
    r = subprocess.run(
        [sys.executable, str(REPO / "tools" / "m1e_java_audit.py"),
         "--classes", str(tmp_path / "classes"), "--skip-api-scan"],
        capture_output=True, text=True)
    assert r.returncode == 1


def test_cli_passes_on_17(tmp_path):
    pkg = tmp_path / "classes" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "A.class").write_bytes(_class(61))
    out = tmp_path / "audit.json"
    r = subprocess.run(
        [sys.executable, str(REPO / "tools" / "m1e_java_audit.py"),
         "--classes", str(tmp_path / "classes"), "--skip-api-scan",
         "--json-out", str(out)],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["ok"] is True
    assert d["class_dirs"][str(tmp_path / "classes")]["count"] == 1


def test_cli_fails_on_source_api(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "A.java").write_text("class A { int x = Math.clamp(1, 0, 2); }", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(REPO / "tools" / "m1e_java_audit.py"),
         "--source", str(src), "--skip-api-scan"],
        capture_output=True, text=True)
    assert r.returncode == 1
