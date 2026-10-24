"""
PluginReaper - Hierarchy Extractor + Clean Folder Builder
Rebuilds the original developer folder structure from parsed RBXM.
"""

from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Set

from .rbxm_parser import RbxModel, RbxInstance, parse_rbxm


SAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_name(name: str, fallback: str = "Unnamed") -> str:
    name = name.strip() or fallback
    name = SAFE_CHARS.sub("_", name)
    name = name.rstrip(". ")
    if not name:
        name = fallback
    return name[:120]


SCRIPT_EXTENSIONS = {
    "Script": ".server.luau",
    "LocalScript": ".client.luau",
    "ModuleScript": ".luau",
    "CoreScript": ".core.luau",
}


class PluginExtractor:
    def __init__(self, model: RbxModel, output_root: Path):
        self.model = model
        self.output_root = Path(output_root)
        self.stats = {
            "scripts_extracted": 0,
            "scripts_with_source": 0,
            "scripts_bytecode_only": 0,
            "folders_created": 0,
            "other_instances": 0,
        }
        self._used_names: Dict[Path, Set[str]] = {}

    def extract(self) -> Path:
        self.output_root.mkdir(parents=True, exist_ok=True)

        # Write metadata
        meta_path = self.output_root / "_plugin_meta.json"
        meta = {
            "instance_count": len(self.model.instances),
            "root_count": len(self.model.roots),
            "metadata": self.model.metadata,
            "script_count": len(self.model.get_scripts()),
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        for root_ref in self.model.roots:
            self._extract_instance(root_ref, self.output_root)

        # Summary
        summary = self.output_root / "_extraction_summary.txt"
        lines = [
            "PluginReaper Extraction Summary",
            "=" * 40,
            f"Scripts extracted      : {self.stats['scripts_extracted']}",
            f"  with Source string   : {self.stats['scripts_with_source']}",
            f"  bytecode only        : {self.stats['scripts_bytecode_only']}",
            f"Folders created        : {self.stats['folders_created']}",
            f"Other instances logged : {self.stats['other_instances']}",
            "",
            "Output layout mirrors the original plugin hierarchy.",
            "Scripts named with Roblox-style suffixes:",
            "  .server.luau  → Script",
            "  .client.luau  → LocalScript",
            "  .luau         → ModuleScript",
        ]
        summary.write_text("\n".join(lines), encoding="utf-8")
        return self.output_root

    def _unique_name(self, parent: Path, base: str, is_dir: bool = False) -> str:
        used = self._used_names.setdefault(parent, set())
        candidate = base
        counter = 1
        while candidate.lower() in used:
            stem = base
            if is_dir:
                candidate = f"{stem}_{counter}"
            else:
                # keep extension
                if "." in stem:
                    name, ext = stem.rsplit(".", 1)
                    candidate = f"{name}_{counter}.{ext}"
                else:
                    candidate = f"{stem}_{counter}"
            counter += 1
        used.add(candidate.lower())
        return candidate

    def _extract_instance(self, ref: int, parent_dir: Path) -> None:
        inst = self.model.instances.get(ref)
        if not inst:
            return

        name = sanitize_name(inst.name or inst.class_name)
        has_children = len(inst.children) > 0

        # Scripts that contain children (common for plugins: root Script + modules inside)
        # become a folder holding the script file + all descendants.
        if inst.is_script:
            if has_children:
                folder_name = self._unique_name(parent_dir, name, is_dir=True)
                folder_path = parent_dir / folder_name
                folder_path.mkdir(parents=True, exist_ok=True)
                self.stats["folders_created"] += 1
                # write the script itself as init / main inside its folder
                self._write_script(inst, folder_path, "init" if name.lower() != "init" else name)
                for child_ref in inst.children:
                    self._extract_instance(child_ref, folder_path)
            else:
                self._write_script(inst, parent_dir, name)
            return

        # Non-script structural / has children → folder
        structural = inst.class_name in (
            "Folder", "Model", "Configuration", "Tool", "ScreenGui",
            "Frame", "ScrollingFrame", "BillboardGui", "SurfaceGui",
            "PluginGui", "DockWidgetPluginGui", "PluginToolbar",
            "Plugin", "BindableEvent", "BindableFunction",
        ) or has_children

        if structural:
            folder_name = self._unique_name(parent_dir, name, is_dir=True)
            folder_path = parent_dir / folder_name
            folder_path.mkdir(parents=True, exist_ok=True)
            self.stats["folders_created"] += 1

            desc = {
                "class": inst.class_name,
                "name": inst.name,
                "properties": {
                    k: (v if not isinstance(v, bytes) else f"<bytes:{len(v)}>")
                    for k, v in inst.properties.items()
                    if k not in ("Source", "Bytecode")
                },
            }
            (folder_path / "_instance.json").write_text(
                json.dumps(desc, indent=2, default=str), encoding="utf-8"
            )

            for child_ref in inst.children:
                self._extract_instance(child_ref, folder_path)
        else:
            # Leaf non-script (Value objects, etc.) → log only
            self.stats["other_instances"] += 1
            leaf_dir = parent_dir / "_values"
            leaf_dir.mkdir(exist_ok=True)
            leaf_name = self._unique_name(leaf_dir, f"{name}_{inst.class_name}.json")
            payload = {
                "class": inst.class_name,
                "name": inst.name,
                "properties": {
                    k: (v if not isinstance(v, bytes) else f"<bytes:{len(v)}>")
                    for k, v in inst.properties.items()
                },
            }
            (leaf_dir / leaf_name).write_text(
                json.dumps(payload, indent=2, default=str), encoding="utf-8"
            )

    def _write_script(self, inst: RbxInstance, parent_dir: Path, name: str) -> None:
        ext = SCRIPT_EXTENSIONS.get(inst.class_name, ".luau")
        file_name = self._unique_name(parent_dir, f"{name}{ext}")
        file_path = parent_dir / file_name

        content: str = ""
        header_lines = [
            f"--[[",
            f"  PluginReaper extraction",
            f"  Class : {inst.class_name}",
            f"  Name  : {inst.name}",
            f"  Ref   : {inst.referent}",
            f"]]",
            "",
        ]

        if inst.source:
            content = inst.source
            self.stats["scripts_with_source"] += 1
        elif inst.bytecode:
            # Bytecode present — write raw + marker so decompiler can pick it up
            bc_path = file_path.with_suffix(file_path.suffix + ".bc")
            bc_path.write_bytes(inst.bytecode)
            content = (
                "--[[ BYTECODE ONLY — original Source was compiled / stripped ]]\n"
                f"-- Raw bytecode written to: {bc_path.name}\n"
                "-- Run PluginReaper decompiler stage to recover approximate source.\n"
            )
            self.stats["scripts_bytecode_only"] += 1
        else:
            content = "--[[ EMPTY SCRIPT — no Source or Bytecode found ]]\n"
            self.stats["scripts_with_source"] += 0

        final = "\n".join(header_lines) + content
        if not final.endswith("\n"):
            final += "\n"
        file_path.write_text(final, encoding="utf-8", errors="replace")
        self.stats["scripts_extracted"] += 1


def extract_plugin(
    input_path: Path,
    output_dir: Path,
) -> Path:
    """
    High-level: parse RBXM → rebuild clean developer-style folder tree.
    """
    model = parse_rbxm(input_path)
    extractor = PluginExtractor(model, output_dir)
    return extractor.extract()
