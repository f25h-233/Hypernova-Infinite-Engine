"""Starsector 方言 JSON 解析器。

本机实测（260mods 48,516 个 .json/.variant/.ship/.wpn/.system/.faction/.skill）
需要容忍的扩展：
  - '#'、'//' 行注释，'/* ... */' 块注释
  - 对象/数组尾逗号；';' 也可当分隔符
  - 单引号字符串；裸标识符值（如 RENDER_LOADED_MISSILES）
  - 数字：+100、.97、1.、0x1F、1.0f、033
  - 文件尾多余的 '}'/']'/','（游戏只读第一个值）

不支持：裸键里的空格、模板字符串。解析失败抛 ParseError。
"""
from __future__ import annotations

import re
from pathlib import Path

_BS = "\\"
_NUM = re.compile(
    r"[+-]?(?:(?:0[xX][0-9a-fA-F]+)|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)[fFdD]?"
)
_IDENT = re.compile(r"[A-Za-z0-9_$./%+*-]+")


class ParseError(ValueError):
    pass


class _Parser:
    def __init__(self, text: str):
        self.s = text
        self.i = 0
        self.n = len(text)

    def parse(self):
        self._ws()
        value = self._value()
        self._ws()
        while self.i < self.n and self.s[self.i] in ",;}];":
            self.i += 1
            self._ws()
        if self.i != self.n:
            raise ParseError(
                f"trailing data at offset {self.i}: {self.s[self.i:self.i + 40]!r}"
            )
        return value

    def _ws(self):
        while self.i < self.n:
            c = self.s[self.i]
            if c in " \t\r\n﻿":
                self.i += 1
            elif c == "#":
                while self.i < self.n and self.s[self.i] not in "\r\n":
                    self.i += 1
            elif c == "/" and self.i + 1 < self.n and self.s[self.i + 1] == "/":
                while self.i < self.n and self.s[self.i] not in "\r\n":
                    self.i += 1
            elif c == "/" and self.i + 1 < self.n and self.s[self.i + 1] == "*":
                end = self.s.find("*/", self.i + 2)
                if end < 0:
                    raise ParseError("unterminated block comment")
                self.i = end + 2
            else:
                return

    def _value(self):
        self._ws()
        if self.i >= self.n:
            raise ParseError("unexpected end of input")
        c = self.s[self.i]
        if c == "{":
            return self._object()
        if c == "[":
            return self._array()
        if c in "\"'":
            return self._string()
        if c in "-+." or c.isdigit():
            return self._number()
        if c.isalpha() or c in "_$":
            return self._identifier(as_key=False)
        raise ParseError(f"unexpected character {c!r} at offset {self.i}")

    def _object(self):
        self.i += 1
        out = {}
        self._ws()
        if self.i < self.n and self.s[self.i] == "}":
            self.i += 1
            return out
        while True:
            self._ws()
            if self.i >= self.n:
                raise ParseError("unterminated object")
            c = self.s[self.i]
            key = self._string() if c in "\"'" else self._identifier(as_key=True)
            self._ws()
            if self.i >= self.n or self.s[self.i] != ":":
                raise ParseError(f"expected ':' at offset {self.i}")
            self.i += 1
            out[key] = self._value()
            self._ws()
            if self.i < self.n and self.s[self.i] in ",;":
                self.i += 1
                self._ws()
                if self.i >= self.n:
                    return out
                if self.s[self.i] == "}":
                    self.i += 1
                    return out
                continue
            if self.i < self.n and self.s[self.i] == "}":
                self.i += 1
                return out
            raise ParseError(f"expected ',' or '}}' at offset {self.i}")

    def _array(self):
        self.i += 1
        out = []
        self._ws()
        if self.i < self.n and self.s[self.i] == "]":
            self.i += 1
            return out
        while True:
            out.append(self._value())
            self._ws()
            if self.i < self.n and self.s[self.i] in ",;":
                self.i += 1
                self._ws()
                if self.i >= self.n:
                    return out
                if self.s[self.i] == "]":
                    self.i += 1
                    return out
                continue
            if self.i < self.n and self.s[self.i] == "]":
                self.i += 1
                return out
            raise ParseError(f"expected ',' or ']' at offset {self.i}")

    def _string(self):
        quote = self.s[self.i]
        self.i += 1
        buf: list[str] = []
        escapes = {
            '"': '"',
            "'": "'",
            "\\": "\\",
            "/": "/",
            "b": "\b",
            "f": "\f",
            "n": "\n",
            "r": "\r",
            "t": "\t",
        }
        while self.i < self.n:
            c = self.s[self.i]
            if c == _BS:
                if self.i + 1 >= self.n:
                    raise ParseError("unterminated escape")
                esc = self.s[self.i + 1]
                if esc == "u":
                    hexs = self.s[self.i + 2:self.i + 6]
                    if len(hexs) == 4 and all(ch in "0123456789abcdefABCDEF" for ch in hexs):
                        buf.append(chr(int(hexs, 16)))
                        self.i += 6
                        continue
                    buf.append("u")
                    self.i += 2
                    continue
                buf.append(escapes.get(esc, esc))
                self.i += 2
                continue
            if c == quote:
                self.i += 1
                return "".join(buf)
            buf.append(c)
            self.i += 1
        raise ParseError("unterminated string")

    def _number(self):
        m = _NUM.match(self.s, self.i)
        if not m:
            raise ParseError(f"bad number at offset {self.i}")
        self.i = m.end()
        text = m.group(0)
        if text.lower().lstrip("+-").startswith("0x"):
            return int(text, 16)
        text = text.rstrip("fFdD")
        if any(ch in text for ch in ".eE"):
            return float(text)
        return int(text)

    def _identifier(self, as_key: bool) -> str:
        m = _IDENT.match(self.s, self.i)
        if not m:
            raise ParseError(f"bad identifier at offset {self.i}")
        self.i = m.end()
        token = m.group(0)
        if not as_key:
            low = token.lower()
            if low == "true":
                return True
            if low == "false":
                return False
            if low == "null":
                return None
        return token


def loads(text: str):
    return _Parser(text).parse()


def load(path: str | Path):
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        return loads(fh.read())
