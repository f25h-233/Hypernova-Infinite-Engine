#!/usr/bin/env python3
"""下载并校验 python.org 官方 embeddable 运行时，供发行包内置使用。

玩家机器上不一定有 Python，而 manifest 生成脚本需要它。发行包内置一份
Windows x64 的 embeddable 运行时，玩家双击批处理就能跑，不用装任何东西。

安全口径：
- 版本与 SHA256 在这里固定，不做"最新版"跟随。
- 下载后必须校验 SHA256，不匹配直接失败，绝不带着可疑文件打包。
- 缓存放在仓库 .cache/python-embed/（.gitignore 已忽略），不进 git。

用法：
    python -I tools/dist/fetch_python_embed.py            # 准备运行时
    python -I tools/dist/fetch_python_embed.py --print-path
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

PY_VERSION = "3.12.10"
PY_SHA256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
PY_FILENAME = f"python-{PY_VERSION}-embed-amd64.zip"

# 国内可达的两个独立镜像；两处下载到的文件 SHA256 一致才敢用。
MIRRORS = (
    f"https://mirrors.huaweicloud.com/python/{PY_VERSION}/{PY_FILENAME}",
    f"https://registry.npmmirror.com/-/binary/python/{PY_VERSION}/{PY_FILENAME}",
)

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache" / "python-embed"
ARCHIVE = CACHE / PY_FILENAME
RUNTIME = CACHE / "runtime"
MARKER = RUNTIME / ".hypernova-python"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def already_ready() -> bool:
    if not MARKER.is_file() or not (RUNTIME / "python.exe").is_file():
        return False
    return MARKER.read_text(encoding="utf-8").strip() == PY_SHA256


def download() -> Path:
    if ARCHIVE.is_file() and sha256_of(ARCHIVE) == PY_SHA256:
        print(f"cache hit: {ARCHIVE}")
        return ARCHIVE
    errors: list[str] = []
    for url in MIRRORS:
        print(f"下载 {url}")
        tmp = ARCHIVE.with_suffix(".part")
        try:
            with urllib.request.urlopen(url, timeout=120) as resp, open(tmp, "wb") as out:
                shutil.copyfileobj(resp, out)
            got = sha256_of(tmp)
            if got != PY_SHA256:
                tmp.unlink(missing_ok=True)
                errors.append(f"{url}: sha256 {got} != {PY_SHA256}")
                continue
            tmp.replace(ARCHIVE)
            print(f"OK sha256={got}")
            return ARCHIVE
        except Exception as exc:  # 网络错误一律换下一个镜像
            tmp.unlink(missing_ok=True)
            errors.append(f"{url}: {exc}")
    raise SystemExit("FATAL: 所有镜像都失败了\n" + "\n".join(errors))


def extract(archive: Path) -> Path:
    if RUNTIME.exists():
        shutil.rmtree(RUNTIME)
    RUNTIME.mkdir(parents=True)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(RUNTIME)
    exe = RUNTIME / "python.exe"
    if not exe.is_file():
        raise SystemExit(f"FATAL: 解压后没有 python.exe（{RUNTIME}）")
    MARKER.write_text(PY_SHA256 + "\n", encoding="utf-8")
    print(f"运行时就绪: {RUNTIME}")
    return RUNTIME


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--print-path", action="store_true", help="只打印运行时目录")
    args = ap.parse_args(argv)
    if args.print_path:
        print(RUNTIME)
        return 0 if already_ready() else 1
    if already_ready():
        print(f"cache hit: {RUNTIME}")
        return 0
    extract(download())
    return 0


if __name__ == "__main__":
    sys.exit(main())
