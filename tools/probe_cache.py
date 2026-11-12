"""读取图片文件头的持久缓存。

键是图片的绝对路径（Windows 下大小写不敏感），值是
``(size, mtime_ns, w, h)``。下一次生成 manifest 时，只有 size / mtime 变了
的图片才需要重新打开读文件头；新增一个 mod 时也只探测它的新图。

缓存文件是 manifest 的 sidecar：损坏、版本不符、换游戏目录都只会让缓存
失效并从零重建，绝不让生成失败。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

SCHEMA = 1
CACHE_NAME = "manifest-probe-cache-v1.json"

Entry = tuple[int, int, int, int]


def key_for(path: Path | str) -> str:
    """稳定的缓存键：词法绝对路径（不跟随 junction）+ 平台大小写规则。"""
    return os.path.normcase(os.path.abspath(os.fspath(path))).replace("\\", "/")


def load(path: Path | None, game_root: Path | str) -> dict[str, Entry]:
    if path is None:
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return {}
    if data.get("game_root") != key_for(game_root):
        return {}
    raw = data.get("entries")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Entry] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, list) or len(value) != 4:
            continue
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in value):
            continue
        size, mtime_ns, width, height = value
        if size < 0 or mtime_ns < 0 or width < 0 or height < 0:
            continue
        out[key] = (size, mtime_ns, width, height)
    return out


def save(path: Path | None, game_root: Path | str,
         entries: dict[str, Entry]) -> bool:
    """原子写入；任何 IO 失败都返回 False，不影响 manifest 生成。"""
    if path is None:
        return False
    payload = {
        "schema": SCHEMA,
        "game_root": key_for(game_root),
        "entries": {key: list(value) for key, value in sorted(entries.items())},
    }
    target = Path(path)
    tmp = target.with_name(target.name + ".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
            fh.flush()
        os.replace(tmp, target)
        return True
    except Exception:
        # 缓存只是加速手段：写盘/序列化失败都不能让 manifest 生成失败。
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False
