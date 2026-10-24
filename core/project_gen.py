"""
PluginReaper v2 — Rojo / project scaffold generator.
Turns extracted tree into a usable Rojo project layout.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def generate_rojo_project(extracted_root: Path, project_name: str = "RecoveredPlugin") -> Path:
    """
    Write default.project.json mapping the extracted folder into a Rojo tree.
    Scripts keep their suffixes (.server.luau / .client.luau / .luau).
    """
    extracted_root = Path(extracted_root)
    project = {
        "name": project_name,
        "tree": {
            "$className": "DataModel",
            "ServerStorage": {
                "$className": "ServerStorage",
                "PluginSource": {
                    "$path": ".",
                },
            },
        },
    }
    # Prefer pointing at the single root folder if there is exactly one non-meta dir
    dirs = [p for p in extracted_root.iterdir() if p.is_dir() and not p.name.startswith("_")]
    if len(dirs) == 1:
        project["tree"]["ServerStorage"]["PluginSource"]["$path"] = dirs[0].name

    out = extracted_root / "default.project.json"
    out.write_text(json.dumps(project, indent=2), encoding="utf-8")
    return out


def generate_readme(extracted_root: Path, meta: Dict[str, Any]) -> Path:
    lines = [
        f"# Recovered Plugin",
        "",
        "Extracted by **PluginReaper**.",
        "",
        "## Stats",
        f"- Instances: {meta.get('instance_count', '?')}",
        f"- Scripts: {meta.get('script_count', '?')}",
        f"- Format: {meta.get('metadata', {}).get('format', '?')}",
        "",
        "## Layout",
        "",
        "Script suffixes:",
        "- `.server.luau` → Script",
        "- `.client.luau` → LocalScript",
        "- `.luau` → ModuleScript",
        "",
        "Open `_analysis.txt` for entry points, risk flags, and require graph.",
        "",
        "## Rojo",
        "",
        "```bash",
        "rojo serve",
        "```",
        "",
        "Or sync `default.project.json` into Studio.",
    ]
    path = extracted_root / "README_RECOVERED.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def generate_script_index(extracted_root: Path) -> Path:
    """Flat index of every .luau file with size + path."""
    rows: List[str] = ["path,lines,bytes"]
    for p in sorted(extracted_root.rglob("*.luau")):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            lines = text.count("\n") + 1
            rows.append(f"{p.relative_to(extracted_root)},{lines},{p.stat().st_size}")
        except Exception:
            continue
    path = extracted_root / "_script_index.csv"
    path.write_text("\n".join(rows), encoding="utf-8")
    return path
