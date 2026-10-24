"""
PluginReaper — Diff original extract vs edited tree.
Shows exactly what the developer changed before rebuild.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


SCRIPT_EXTS = {".luau", ".lua"}


@dataclass
class FileDiff:
    path: str
    status: str  # added | removed | modified | unchanged
    old_lines: int = 0
    new_lines: int = 0
    old_hash: str = ""
    new_hash: str = ""


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def _line_count(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def _collect_scripts(root: Path) -> Dict[str, Path]:
    out: Dict[str, Path] = {}
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in SCRIPT_EXTS:
            continue
        if p.name.startswith("_"):
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        out[rel] = p
    return out


def diff_trees(original: Path, edited: Path) -> List[FileDiff]:
    """
    Compare two extracted trees (e.g. first extract snapshot vs current edits).
    """
    a = _collect_scripts(Path(original))
    b = _collect_scripts(Path(edited))
    all_paths = sorted(set(a) | set(b))
    results: List[FileDiff] = []

    for rel in all_paths:
        pa, pb = a.get(rel), b.get(rel)
        if pa and not pb:
            text = pa.read_text(encoding="utf-8", errors="replace")
            results.append(
                FileDiff(rel, "removed", _line_count(text), 0, _hash_text(text), "")
            )
        elif pb and not pa:
            text = pb.read_text(encoding="utf-8", errors="replace")
            results.append(
                FileDiff(rel, "added", 0, _line_count(text), "", _hash_text(text))
            )
        else:
            ta = pa.read_text(encoding="utf-8", errors="replace")
            tb = pb.read_text(encoding="utf-8", errors="replace")
            ha, hb = _hash_text(ta), _hash_text(tb)
            status = "unchanged" if ha == hb else "modified"
            results.append(
                FileDiff(rel, status, _line_count(ta), _line_count(tb), ha, hb)
            )
    return results


def write_diff_report(diffs: List[FileDiff], out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    added = [d for d in diffs if d.status == "added"]
    removed = [d for d in diffs if d.status == "removed"]
    modified = [d for d in diffs if d.status == "modified"]
    unchanged = [d for d in diffs if d.status == "unchanged"]

    lines = [
        "PluginReaper Diff Report",
        "=" * 50,
        f"Added     : {len(added)}",
        f"Removed   : {len(removed)}",
        f"Modified  : {len(modified)}",
        f"Unchanged : {len(unchanged)}",
        "",
    ]
    if added:
        lines += ["ADDED", "-" * 30]
        for d in added:
            lines.append(f"  + {d.path}  ({d.new_lines} lines)")
        lines.append("")
    if removed:
        lines += ["REMOVED", "-" * 30]
        for d in removed:
            lines.append(f"  - {d.path}  ({d.old_lines} lines)")
        lines.append("")
    if modified:
        lines += ["MODIFIED", "-" * 30]
        for d in modified:
            delta = d.new_lines - d.old_lines
            sign = f"+{delta}" if delta >= 0 else str(delta)
            lines.append(f"  ~ {d.path}  {d.old_lines} → {d.new_lines} lines ({sign})")
        lines.append("")

    path = out_dir / "_diff.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "_diff.json").write_text(
        json.dumps([asdict(d) for d in diffs], indent=2), encoding="utf-8"
    )
    return path


def snapshot_tree(src: Path, dest: Path) -> Path:
    """Copy only script files to a snapshot folder for later diff."""
    import shutil

    src, dest = Path(src), Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    scripts = _collect_scripts(src)
    for rel, p in scripts.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(p.read_bytes())
    return dest
