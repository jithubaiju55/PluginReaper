"""
PluginReaper v2 — Full-text search + pattern scanner across extracted tree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Pattern, Union


@dataclass
class Hit:
    file: str
    line: int
    text: str
    match: str


def search_tree(
    root: Path,
    query: str,
    *,
    regex: bool = False,
    case_insensitive: bool = True,
    extensions: Optional[Iterable[str]] = None,
    max_hits: int = 500,
) -> List[Hit]:
    root = Path(root)
    exts = set(extensions or {".luau", ".lua", ".txt", ".json"})
    flags = re.IGNORECASE if case_insensitive else 0
    if regex:
        pattern: Pattern = re.compile(query, flags)
    else:
        pattern = re.compile(re.escape(query), flags)

    hits: List[Hit] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in exts and path.suffix != "":
            continue
        if path.name.startswith("_") and path.suffix == ".json":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            m = pattern.search(line)
            if m:
                hits.append(
                    Hit(
                        file=str(path.relative_to(root)),
                        line=i,
                        text=line.strip()[:200],
                        match=m.group(0)[:80],
                    )
                )
                if len(hits) >= max_hits:
                    return hits
    return hits


def scan_patterns(root: Path) -> dict:
    """Built-in security / behavior pattern scan."""
    patterns = {
        "http": r"HttpService|RequestAsync|HttpGet|PostAsync",
        "loadstring": r"loadstring\s*\(",
        "getfenv": r"getfenv\s*\(|setfenv\s*\(",
        "remote": r"FireServer|InvokeServer|OnServerEvent|RemoteEvent",
        "require_http": r"require\s*\(\s*.*Http",
        "marketplace": r"MarketplaceService|PromptPurchase|PromptGamePass",
        "teleport": r"TeleportService|TeleportAsync",
        "datastore": r"DataStoreService|GetDataStore",
        "plugin_save": r"plugin\s*:\s*SetSetting|plugin\s*:\s*GetSetting",
    }
    results = {}
    for name, pat in patterns.items():
        hits = search_tree(root, pat, regex=True, max_hits=50)
        results[name] = [
            {"file": h.file, "line": h.line, "text": h.text} for h in hits
        ]
    return results
