"""
PluginReaper v2 — Lightweight Luau source cleaner.
Not a full formatter; focuses on readability after extraction.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List


def strip_reaper_header(src: str) -> str:
    """Remove PluginReaper extraction banner if present."""
    if src.startswith("--[[") and "PluginReaper extraction" in src[:200]:
        end = src.find("]]")
        if end != -1:
            rest = src[end + 2 :]
            return rest.lstrip("\n")
    return src


def basic_beautify(src: str) -> str:
    """
    Light cleanup:
    - normalize newlines
    - trim trailing whitespace
    - collapse 3+ blank lines to 2
    - ensure final newline
    """
    src = src.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in src.split("\n")]
    out: List[str] = []
    blank_run = 0
    for ln in lines:
        if ln.strip() == "":
            blank_run += 1
            if blank_run <= 2:
                out.append("")
        else:
            blank_run = 0
            out.append(ln)
    text = "\n".join(out)
    if not text.endswith("\n"):
        text += "\n"
    return text


def clean_file(path: Path, *, strip_header: bool = False) -> bool:
    try:
        original = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    text = original
    if strip_header:
        text = strip_reaper_header(text)
    text = basic_beautify(text)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def clean_tree(root: Path, *, strip_header: bool = False) -> int:
    n = 0
    for p in root.rglob("*.luau"):
        if clean_file(p, strip_header=strip_header):
            n += 1
    for p in root.rglob("*.lua"):
        if clean_file(p, strip_header=strip_header):
            n += 1
    return n
