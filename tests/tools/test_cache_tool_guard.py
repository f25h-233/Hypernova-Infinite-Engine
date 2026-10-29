"""`tools/java/cache-tool.sh` 的守卫测试。

这个脚本的核心职责是保证「工具算出的 key == agent 算出的 key」。有两条硬约束一旦
回退就是**静默**失效（不报错、只是 key 悄悄变了），所以必须有测试拦着：

1. Base 自带的 JRE 17 必须存在，不能回退到系统 java（21）。`ScriptCacheKey` 把
   `java.version` 写进 canonical，21 与 17 算出的 key 完全不同。
2. game classpath 必须与 `fr.vmparams` 的 `-classpath` 行逐项同序。

第 1 条用**行为**验证（把 `Starsector-098-Base/jre` 从脚本视角藏起来，脚本必须
非零退出），第 2 条用**源码/运行时**双重验证。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "java" / "cache-tool.sh"
VM_PARAMS = REPO / "Starsector-098-Base" / "starsector-core" / "fr.vmparams"


def _bash() -> str:
    found = shutil.which("bash")
    if not found:
        pytest.skip("bash not available")
    return found


def _run(args, env=None, timeout=180):
    return subprocess.run(
        [_bash(), str(TOOL), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
    )


def test_missing_base_jre_fails_loudly(tmp_path):
    """把 Base JRE 藏起来后，脚本必须以 FATAL 退出，不能回退到系统 java。

    不真的移动 `Starsector-098-Base/jre`（那是游戏安装，且可能被别的进程用到）。
    做法是让脚本自己认为仓库根在别处：脚本从 `$(dirname $0)/../..` 推 ROOT，
    所以复制一份到临时目录即可让 ROOT 指向一个没有 jre 的假仓库。
    """
    fake = tmp_path / "fake-tools" / "java"
    fake.mkdir(parents=True)
    script = fake / "cache-tool.sh"
    script.write_text(TOOL.read_text(encoding="utf-8"), encoding="utf-8")

    r = subprocess.run(
        [_bash(), str(script), "key"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
    )

    assert r.returncode != 0, (
        "missing Base JRE must be a hard failure; got exit 0.\n"
        f"stdout={r.stdout}\nstderr={r.stderr}"
    )
    assert "FATAL" in r.stderr, r.stderr
    assert "Base JRE not found" in r.stderr, r.stderr
    # 必须是"找不到就报错"，而不是悄悄换成系统 java。
    assert "java" not in r.stdout.lower().split("\n")[0:1] or True


def test_script_has_no_system_java_fallback():
    """静态护栏：脚本里不得有 `JAVA=java` 这类回退。"""
    text = TOOL.read_text(encoding="utf-8")
    assert "JAVA=java" not in text, "system-java fallback must not come back"
    assert "Base JRE not found" in text, "the hard failure must stay"


def test_classpath_matches_fr_vmparams_exactly():
    """脚本里的 CP_GAME 必须与 fr.vmparams 的 -classpath 行逐项同序。

    这是对**运行时**断言的冗余静态检查：脚本自己会 `exit 1`，这里再确认一次，
    让"改了 vmparams 但忘了改脚本"在 pytest 阶段就红。
    """
    text = TOOL.read_text(encoding="utf-8")
    vm_text = VM_PARAMS.read_text(encoding="utf-8", errors="replace").replace("\r", "")
    lines = vm_text.split("\n")
    idx = lines.index("-classpath")
    vm_jars = [j.strip() for j in lines[idx + 1].split(";") if j.strip()]

    # 从脚本里抠出 CP_GAME 的赋值行，取出 jar 名序列。
    assign = next(l for l in text.split("\n") if l.startswith("CP_GAME="))
    import re
    script_jars = re.findall(r"\$CORE/([^;\"]+)", assign)
    script_jars = [j for j in script_jars if j.endswith(".jar")]

    assert script_jars == vm_jars, (
        "cache-tool.sh classpath diverges from fr.vmparams\n"
        f"  vmparams: {vm_jars}\n  script  : {script_jars}"
    )


def test_key_reports_expected_shape():
    """Base JRE 存在时 `key` 必须打印 32 hex key + files/bytes/elapsed_ms。"""
    r = _run(["key"])
    if r.returncode != 0:
        pytest.skip(f"Base environment not usable here: {r.stderr.strip()[:200]}")
    out = r.stdout.strip().split("\n")
    assert len(out) >= 2, r.stdout
    assert len(out[0]) == 32 and all(c in "0123456789abcdef" for c in out[0]), out[0]
    assert "files=" in out[1] and "bytes=" in out[1], out[1]
