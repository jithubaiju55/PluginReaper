"""
PluginReaper - XML RBXMX/RBXLX Parser
Parses Roblox XML model format (version 4) into the same RbxModel used by the binary parser.
Handles ProtectedString / Source (including CDATA), full hierarchy, Name, etc.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .rbxm_parser import RbxInstance, RbxModel


SCRIPT_CLASSES = {"Script", "LocalScript", "ModuleScript", "CoreScript"}


def _text(elem: Optional[ET.Element]) -> str:
    if elem is None:
        return ""
    # ElementTree collapses CDATA into .text
    parts: List[str] = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _local(tag: str) -> str:
    """Strip namespace if present."""
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


class RbxmxParser:
    def __init__(self):
        self._ref_counter = 0
        self._referent_map: Dict[str, int] = {}

    def parse(self, path: Union[str, Path, bytes]) -> RbxModel:
        if isinstance(path, (str, Path)):
            data = Path(path).read_bytes()
        else:
            data = path

        # tolerate BOM / leading whitespace
        text = data.decode("utf-8", errors="replace").lstrip("\ufeff")
        if not text.lstrip().startswith("<"):
            raise ValueError("Not a valid XML Roblox file")

        # ElementTree is strict about some entities; pre-sanitize common issues
        text = self._preprocess(text)
        root = ET.fromstring(text)

        if _local(root.tag).lower() != "roblox":
            raise ValueError(f"Expected <roblox> root, got <{_local(root.tag)}>")

        model = RbxModel()
        model.metadata["format"] = "xml"
        model.metadata["version"] = root.attrib.get("version", "4")

        # Meta elements
        for child in root:
            tag = _local(child.tag)
            if tag == "Meta":
                name = child.attrib.get("name", "")
                model.metadata[name] = (child.text or "").strip()

        # Top-level Items
        for child in root:
            if _local(child.tag) == "Item":
                self._parse_item(child, model, parent_ref=None)

        # roots = instances with no parent
        for ref, inst in model.instances.items():
            if inst.parent is None:
                model.roots.append(ref)

        return model

    def _preprocess(self, text: str) -> str:
        """Light cleanup so ElementTree can swallow real-world rbxmx files."""
        # remove XML declaration issues / extra namespaces that break some parsers
        # keep content intact
        return text

    def _alloc_ref(self, referent_attr: Optional[str]) -> int:
        if referent_attr and referent_attr in self._referent_map:
            return self._referent_map[referent_attr]
        self._ref_counter += 1
        ref = self._ref_counter
        if referent_attr:
            self._referent_map[referent_attr] = ref
        return ref

    def _parse_item(
        self,
        elem: ET.Element,
        model: RbxModel,
        parent_ref: Optional[int],
    ) -> int:
        class_name = elem.attrib.get("class", "Instance")
        referent_attr = elem.attrib.get("referent")
        ref = self._alloc_ref(referent_attr)

        inst = RbxInstance(referent=ref, class_name=class_name)
        if class_name in SCRIPT_CLASSES:
            inst.is_script = True
        inst.parent = parent_ref

        # Properties
        for child in elem:
            tag = _local(child.tag)
            if tag == "Properties":
                self._parse_properties(child, inst)
            elif tag == "Item":
                child_ref = self._parse_item(child, model, parent_ref=ref)
                if child_ref not in inst.children:
                    inst.children.append(child_ref)

        model.instances[ref] = inst
        if parent_ref is not None and parent_ref in model.instances:
            parent = model.instances[parent_ref]
            if ref not in parent.children:
                parent.children.append(ref)

        return ref

    def _parse_properties(self, props_elem: ET.Element, inst: RbxInstance) -> None:
        for prop in props_elem:
            tag = _local(prop.tag)
            name = prop.attrib.get("name", "")
            if not name:
                continue

            value: Any = None

            if tag in ("string", "token", "BinaryString", "SharedString"):
                value = _text(prop)
            elif tag == "ProtectedString":
                # Source / Bytecode — preserve exact text (CDATA already expanded by ET)
                value = _text(prop)
            elif tag == "bool":
                value = (_text(prop).strip().lower() == "true")
            elif tag in ("int", "int64", "token"):
                try:
                    value = int(_text(prop).strip() or "0")
                except ValueError:
                    value = 0
            elif tag in ("float", "double"):
                try:
                    value = float(_text(prop).strip() or "0")
                except ValueError:
                    value = 0.0
            elif tag == "Content":
                # often <null></null> or url
                null = prop.find("null")
                if null is not None:
                    value = None
                else:
                    url = prop.find("url")
                    value = _text(url) if url is not None else _text(prop)
            else:
                # complex types — store raw text / nested structure lightly
                value = _text(prop) or None

            inst.properties[name] = value

            if name == "Name" and isinstance(value, str):
                inst.name = value
            elif name == "Source" and isinstance(value, str):
                # Heuristic: pure source vs possible binary garbage
                if value and not self._looks_like_bytecode(value):
                    inst.source = value
                else:
                    # treat as bytecode-ish / empty
                    if value:
                        try:
                            inst.bytecode = value.encode("utf-8", errors="surrogateescape")
                        except Exception:
                            inst.source = value
                    else:
                        inst.source = ""

    @staticmethod
    def _looks_like_bytecode(s: str) -> bool:
        if not s or len(s) < 4:
            return False
        # real Luau source is almost always printable
        sample = s[:200]
        non_print = sum(1 for c in sample if ord(c) < 9 or (13 < ord(c) < 32))
        return non_print > 8


def parse_rbxmx(path: Union[str, Path, bytes]) -> RbxModel:
    return RbxmxParser().parse(path)
