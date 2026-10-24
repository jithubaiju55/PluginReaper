"""
PluginReaper v2 — Rebuild extracted source tree back into a loadable .rbxmx plugin.

Workflow for developers:
  1. Extract plugin → edit sources / add features
  2. rebuild → .rbxmx
  3. Studio: Plugins folder or right-click → Save as Local Plugin / Publish

Supports the folder layout produced by PluginExtractor:
  - *.server.luau  → Script
  - *.client.luau  → LocalScript
  - *.luau         → ModuleScript
  - directories        → Folder (or original class from _instance.json)
  - init.server.luau inside a folder named after a former Script root
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape


SCRIPT_SUFFIXES = {
    ".server.luau": "Script",
    ".client.luau": "LocalScript",
    ".core.luau": "CoreScript",
    ".luau": "ModuleScript",
    ".server.lua": "Script",
    ".client.lua": "LocalScript",
    ".lua": "ModuleScript",
}

SKIP_NAMES = {
    "_plugin_meta.json",
    "_extraction_summary.txt",
    "_analysis.txt",
    "_analysis.json",
    "_script_index.csv",
    "_scan_results.json",
    "_instance.json",
    "default.project.json",
    "README_RECOVERED.md",
    "README.md",
}


def _new_referent() -> str:
    return "RBX" + uuid.uuid4().hex.upper()


def _cdata_source(src: str) -> str:
    """Wrap source in CDATA; split if ]]> appears (Roblox-safe)."""
    if "]]>" not in src:
        return f"<![CDATA[{src}]]>"
    # split around ]]>
    parts = src.split("]]>")
    chunks = []
    for i, part in enumerate(parts):
        if i < len(parts) - 1:
            chunks.append(f"<![CDATA[{part}]]]]><![CDATA[>")
        else:
            chunks.append(f"<![CDATA[{part}]]>")
    return "".join(chunks)


def _xml_string(s: str) -> str:
    return escape(s, {"\"": "&quot;", "'": "&apos;"})


def _class_for_file(path: Path) -> Optional[str]:
    name = path.name.lower()
    for suf, cls in SCRIPT_SUFFIXES.items():
        if name.endswith(suf):
            return cls
    return None


def _script_display_name(path: Path) -> str:
    name = path.name
    for suf in sorted(SCRIPT_SUFFIXES.keys(), key=len, reverse=True):
        if name.lower().endswith(suf):
            return name[: -len(suf)]
    return path.stem


def _load_instance_meta(folder: Path) -> Dict[str, Any]:
    meta_path = folder / "_instance.json"
    if meta_path.is_file():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _read_source(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    # strip PluginReaper header if present
    if text.startswith("--[[") and "PluginReaper extraction" in text[:240]:
        end = text.find("]]")
        if end != -1:
            text = text[end + 2 :].lstrip("\n")
    return text


class RbxmxBuilder:
    def __init__(self):
        self.lines: List[str] = []
        self.indent = 0

    def _w(self, line: str = "") -> None:
        self.lines.append(("\t" * self.indent) + line)

    def build_from_tree(self, root_dir: Path) -> str:
        self.lines = []
        self._w('<?xml version="1.0" encoding="utf-8"?>')
        self._w(
            '<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" '
            'version="4">'
        )
        self.indent += 1
        self._w('<Meta name="ExplicitAutoJoints">true</Meta>')
        self._w("<External>null</External>")
        self._w("<External>nil</External>")

        # Prefer single top-level content folder; else emit all children of root_dir
        entries = [
            p
            for p in sorted(root_dir.iterdir(), key=lambda x: x.name.lower())
            if p.name not in SKIP_NAMES and not p.name.startswith(".")
        ]
        # skip pure meta files already filtered; also skip _values dumps
        entries = [p for p in entries if p.name != "_values"]

        for entry in entries:
            self._emit_path(entry)

        self.indent -= 1
        self._w("</roblox>")
        return "\n".join(self.lines) + "\n"

    def _emit_path(self, path: Path) -> None:
        if path.is_file():
            cls = _class_for_file(path)
            if not cls:
                return  # ignore non-script files at this level
            self._emit_script(path, cls)
            return

        if not path.is_dir():
            return

        meta = _load_instance_meta(path)
        # If this folder represents a former Script (has init.server.luau / init.luau)
        init_script = None
        for candidate in (
            "init.server.luau",
            "init.client.luau",
            "init.luau",
            "init.server.lua",
            "init.lua",
        ):
            p = path / candidate
            if p.is_file():
                init_script = p
                break

        if init_script is not None:
            cls = _class_for_file(init_script) or "Script"
            name = meta.get("name") or path.name
            self._emit_script_with_children(init_script, cls, name, path)
            return

        # Normal folder / structural instance
        class_name = meta.get("class") or "Folder"
        name = meta.get("name") or path.name
        ref = _new_referent()
        self._w(f'<Item class="{_xml_string(class_name)}" referent="{ref}">')
        self.indent += 1
        self._w("<Properties>")
        self.indent += 1
        self._w(f'<string name="Name">{_xml_string(name)}</string>')
        # preserve a few useful bools if present
        props = meta.get("properties") or {}
        if "Disabled" in props and class_name in ("Script", "LocalScript", "ModuleScript"):
            val = "true" if props["Disabled"] else "false"
            self._w(f'<bool name="Disabled">{val}</bool>')
        self.indent -= 1
        self._w("</Properties>")

        for child in sorted(path.iterdir(), key=lambda x: x.name.lower()):
            if child.name in SKIP_NAMES or child.name.startswith("."):
                continue
            if child.name == "_values":
                continue
            self._emit_path(child)

        self.indent -= 1
        self._w("</Item>")

    def _emit_script(self, path: Path, class_name: str, name: Optional[str] = None) -> None:
        name = name or _script_display_name(path)
        source = _read_source(path)
        ref = _new_referent()
        self._w(f'<Item class="{_xml_string(class_name)}" referent="{ref}">')
        self.indent += 1
        self._w("<Properties>")
        self.indent += 1
        self._w(f'<string name="Name">{_xml_string(name)}</string>')
        self._w('<bool name="Disabled">false</bool>')
        self._w(f'<ProtectedString name="Source">{_cdata_source(source)}</ProtectedString>')
        self.indent -= 1
        self._w("</Properties>")
        self.indent -= 1
        self._w("</Item>")

    def _emit_script_with_children(
        self,
        init_path: Path,
        class_name: str,
        name: str,
        folder: Path,
    ) -> None:
        source = _read_source(init_path)
        ref = _new_referent()
        self._w(f'<Item class="{_xml_string(class_name)}" referent="{ref}">')
        self.indent += 1
        self._w("<Properties>")
        self.indent += 1
        self._w(f'<string name="Name">{_xml_string(name)}</string>')
        self._w('<bool name="Disabled">false</bool>')
        self._w(f'<ProtectedString name="Source">{_cdata_source(source)}</ProtectedString>')
        self.indent -= 1
        self._w("</Properties>")

        for child in sorted(folder.iterdir(), key=lambda x: x.name.lower()):
            if child.name in SKIP_NAMES or child.name.startswith("."):
                continue
            if child == init_path:
                continue
            if child.name.startswith("init.") and _class_for_file(child):
                continue
            self._emit_path(child)

        self.indent -= 1
        self._w("</Item>")


def rebuild_plugin(
    extracted_dir: Path,
    output_path: Path,
) -> Path:
    """
    Convert an extracted PluginReaper tree back into a Studio-loadable .rbxmx plugin.
    """
    extracted_dir = Path(extracted_dir)
    output_path = Path(output_path)
    if output_path.suffix.lower() not in (".rbxmx", ".rbxm"):
        output_path = output_path.with_suffix(".rbxmx")

    builder = RbxmxBuilder()
    xml = builder.build_from_tree(extracted_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(xml, encoding="utf-8")
    return output_path
