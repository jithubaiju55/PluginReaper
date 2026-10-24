"""
PluginReaper - Binary RBXM/RBXL Parser
Pure Python implementation of Roblox binary model format (Version 0).
Handles LZ4 + ZSTD compression. Extracts full instance tree + Source/Bytecode.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import zstandard as zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False

try:
    import lz4.block
    HAS_LZ4 = True
except ImportError:
    HAS_LZ4 = False


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _read_u8(data: bytes, offset: int) -> Tuple[int, int]:
    return data[offset], offset + 1


def _read_u16(data: bytes, offset: int) -> Tuple[int, int]:
    return struct.unpack_from("<H", data, offset)[0], offset + 2


def _read_i32(data: bytes, offset: int) -> Tuple[int, int]:
    return struct.unpack_from("<i", data, offset)[0], offset + 4


def _read_u32(data: bytes, offset: int) -> Tuple[int, int]:
    return struct.unpack_from("<I", data, offset)[0], offset + 4


def _read_f32(data: bytes, offset: int) -> Tuple[float, int]:
    return struct.unpack_from("<f", data, offset)[0], offset + 4


def _read_f64(data: bytes, offset: int) -> Tuple[float, int]:
    return struct.unpack_from("<d", data, offset)[0], offset + 8


def _read_string(data: bytes, offset: int) -> Tuple[str, int]:
    length, offset = _read_u32(data, offset)
    s = data[offset : offset + length]
    offset += length
    try:
        return s.decode("utf-8"), offset
    except UnicodeDecodeError:
        return s.decode("latin-1", errors="replace"), offset


def _read_bytes(data: bytes, offset: int) -> Tuple[bytes, int]:
    length, offset = _read_u32(data, offset)
    b = data[offset : offset + length]
    return b, offset + length


def _interleaved_i32(data: bytes, count: int, offset: int) -> Tuple[List[int], int]:
    """Roblox interleaves 4-byte integers for better RLE."""
    raw = data[offset : offset + count * 4]
    offset += count * 4
    result = []
    for i in range(count):
        b0 = raw[i]
        b1 = raw[count + i]
        b2 = raw[2 * count + i]
        b3 = raw[3 * count + i]
        val = (b0 << 24) | (b1 << 16) | (b2 << 8) | b3
        # sign extend
        if val & 0x80000000:
            val = val - 0x100000000
        result.append(val)
    return result, offset


def _interleaved_u32(data: bytes, count: int, offset: int) -> Tuple[List[int], int]:
    raw = data[offset : offset + count * 4]
    offset += count * 4
    result = []
    for i in range(count):
        b0 = raw[i]
        b1 = raw[count + i]
        b2 = raw[2 * count + i]
        b3 = raw[3 * count + i]
        val = (b0 << 24) | (b1 << 16) | (b2 << 8) | b3
        result.append(val)
    return result, offset


# ---------------------------------------------------------------------------
# Compression
# ---------------------------------------------------------------------------

def _decompress_chunk(compressed: bytes, uncompressed_len: int) -> bytes:
    if not compressed:
        return b""
    # LZ4 magic
    if compressed[:4] == b"\x02\x08\x00\x00" or (HAS_LZ4 and compressed[0] == 0x02):
        if HAS_LZ4:
            try:
                return lz4.block.decompress(compressed, uncompressed_size=uncompressed_len)
            except Exception:
                pass
        # fallback pure-python attempt fails often; try zlib
    # ZSTD
    if HAS_ZSTD:
        try:
            dctx = zstd.ZstdDecompressor()
            return dctx.decompress(compressed, max_output_size=uncompressed_len)
        except Exception:
            pass
    # raw / already uncompressed
    if len(compressed) == uncompressed_len:
        return compressed
    # last resort zlib
    try:
        return zlib.decompress(compressed)
    except Exception:
        return compressed


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RbxInstance:
    referent: int
    class_name: str
    name: str = ""
    parent: Optional[int] = None
    children: List[int] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)
    # convenience
    source: Optional[str] = None
    bytecode: Optional[bytes] = None
    is_script: bool = False


@dataclass
class RbxModel:
    instances: Dict[int, RbxInstance] = field(default_factory=dict)
    roots: List[int] = field(default_factory=list)
    class_counts: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, str] = field(default_factory=dict)

    def get_scripts(self) -> List[RbxInstance]:
        return [inst for inst in self.instances.values() if inst.is_script]

    def walk(self, root_ref: Optional[int] = None) -> List[RbxInstance]:
        result = []
        def _recurse(ref: int, depth: int = 0):
            inst = self.instances.get(ref)
            if not inst:
                return
            result.append(inst)
            for child in inst.children:
                _recurse(child, depth + 1)
        if root_ref is not None:
            _recurse(root_ref)
        else:
            for r in self.roots:
                _recurse(r)
        return result


# ---------------------------------------------------------------------------
# Property type handlers (common ones)
# ---------------------------------------------------------------------------

PROPERTY_TYPES = {
    0x01: "string",
    0x02: "bool",
    0x03: "int",
    0x04: "float",
    0x05: "double",
    0x06: "UDim",
    0x07: "UDim2",
    0x08: "Ray",
    0x09: "Faces",
    0x0A: "Axes",
    0x0B: "BrickColor",
    0x0C: "Color3",
    0x0D: "Vector2",
    0x0E: "Vector3",
    0x0F: "Vector2int16",
    0x10: "Vector3int16",
    0x11: "CFrame",
    0x12: "Enum",
    0x13: "Referent",
    0x14: "Vector3",  # legacy
    0x15: "NumberSequence",
    0x16: "ColorSequence",
    0x17: "NumberRange",
    0x18: "Rect",
    0x19: "PhysicalProperties",
    0x1A: "Color3uint8",
    0x1B: "int64",
    0x1C: "SharedString",
    0x1D: "ProtectedString",  # Source / Bytecode
    0x1E: "OptionalCoordinateFrame",
    0x1F: "UniqueId",
    0x20: "Font",
}


def _parse_property_values(
    prop_type: int,
    count: int,
    data: bytes,
    offset: int,
    shared_strings: Optional[List[bytes]] = None,
) -> Tuple[List[Any], int]:
    values: List[Any] = []

    if prop_type == 0x01:  # String
        for _ in range(count):
            s, offset = _read_string(data, offset)
            values.append(s)
    elif prop_type == 0x02:  # Bool
        for _ in range(count):
            v, offset = _read_u8(data, offset)
            values.append(bool(v))
    elif prop_type == 0x03:  # Int32
        vals, offset = _interleaved_i32(data, count, offset)
        values = vals
    elif prop_type == 0x04:  # Float
        for _ in range(count):
            v, offset = _read_f32(data, offset)
            values.append(v)
    elif prop_type == 0x05:  # Double
        for _ in range(count):
            v, offset = _read_f64(data, offset)
            values.append(v)
    elif prop_type == 0x1D:  # ProtectedString (Source / compiled)
        for _ in range(count):
            raw, offset = _read_bytes(data, offset)
            # Heuristic: if mostly printable → source string, else bytecode
            try:
                text = raw.decode("utf-8")
                if all(c.isprintable() or c in "\n\r\t" for c in text[:200]):
                    values.append(("source", text))
                else:
                    values.append(("bytecode", raw))
            except Exception:
                values.append(("bytecode", raw))
    elif prop_type == 0x1C:  # SharedString
        idxs, offset = _interleaved_u32(data, count, offset)
        for idx in idxs:
            if shared_strings and 0 <= idx < len(shared_strings):
                values.append(shared_strings[idx])
            else:
                values.append(b"")
    elif prop_type == 0x13:  # Referent
        vals, offset = _interleaved_i32(data, count, offset)
        values = vals
    else:
        # Skip unknown by reading remaining as opaque
        # For safety we just store None and advance best-effort
        # Most unknown types are fixed size; we leave offset untouched for caller to recover
        values = [None] * count

    return values, offset


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

class RbxmParser:
    MAGIC = b"<roblox!"

    def __init__(self):
        self.shared_strings: List[bytes] = []

    def parse(self, path: Union[str, Path, bytes]) -> RbxModel:
        # Prefer unified auto-detect entry so XML never hits this class path.
        return parse_rbxm(path)

    def _parse_bytes(self, data: bytes) -> RbxModel:
        if not data.startswith(self.MAGIC):
            raise ValueError("Invalid Roblox binary file (missing <roblox! magic)")

        offset = 8  # skip magic
        # signature 6 bytes
        offset += 6
        version, offset = _read_u16(data, offset)
        class_count, offset = _read_i32(data, offset)
        instance_count, offset = _read_i32(data, offset)
        offset += 8  # reserved

        model = RbxModel()
        # Temporary storage
        class_map: Dict[int, Dict[str, Any]] = {}  # class_id → info
        referent_to_class: Dict[int, int] = {}
        instances: Dict[int, RbxInstance] = {}

        # Parse chunks
        while offset < len(data):
            if offset + 16 > len(data):
                break
            chunk_name = data[offset : offset + 4]
            offset += 4
            comp_len, offset = _read_u32(data, offset)
            uncomp_len, offset = _read_u32(data, offset)
            offset += 4  # reserved

            compressed = data[offset : offset + comp_len]
            offset += comp_len

            if comp_len == 0 and uncomp_len == 0:
                body = b""
            elif comp_len == uncomp_len or not compressed:
                body = compressed
            else:
                body = _decompress_chunk(compressed, uncomp_len)

            name = chunk_name.decode("ascii", errors="ignore").rstrip("\x00")

            if name == "META":
                self._parse_meta(body, model)
            elif name == "SSTR":
                self._parse_sstr(body)
            elif name == "INST":
                self._parse_inst(body, class_map, instances, referent_to_class)
            elif name == "PROP":
                self._parse_prop(body, class_map, instances)
            elif name == "PRNT":
                self._parse_prnt(body, instances, model)
            elif name == "END\x00":
                break

        model.instances = instances
        # Build roots
        for ref, inst in instances.items():
            if inst.parent is None:
                model.roots.append(ref)
        return model

    def _parse_meta(self, body: bytes, model: RbxModel):
        offset = 0
        count, offset = _read_u32(body, offset)
        for _ in range(count):
            key, offset = _read_string(body, offset)
            val, offset = _read_string(body, offset)
            model.metadata[key] = val

    def _parse_sstr(self, body: bytes):
        offset = 0
        version, offset = _read_u32(body, offset)
        count, offset = _read_u32(body, offset)
        self.shared_strings = []
        for _ in range(count):
            # hash 16 bytes + length + data
            offset += 16
            raw, offset = _read_bytes(body, offset)
            self.shared_strings.append(raw)

    def _parse_inst(
        self,
        body: bytes,
        class_map: Dict,
        instances: Dict[int, RbxInstance],
        referent_to_class: Dict[int, int],
    ):
        offset = 0
        class_id, offset = _read_u32(body, offset)
        class_name, offset = _read_string(body, offset)
        object_format, offset = _read_u8(body, offset)
        instance_count, offset = _read_u32(body, offset)

        referents, offset = _interleaved_i32(body, instance_count, offset)

        class_map[class_id] = {
            "name": class_name,
            "referents": referents,
            "format": object_format,
        }

        for ref in referents:
            inst = RbxInstance(referent=ref, class_name=class_name)
            if class_name in ("Script", "LocalScript", "ModuleScript", "CoreScript"):
                inst.is_script = True
            instances[ref] = inst
            referent_to_class[ref] = class_id

    def _parse_prop(self, body: bytes, class_map: Dict, instances: Dict[int, RbxInstance]):
        offset = 0
        class_id, offset = _read_u32(body, offset)
        prop_name, offset = _read_string(body, offset)
        prop_type, offset = _read_u8(body, offset)

        info = class_map.get(class_id)
        if not info:
            return
        referents = info["referents"]
        count = len(referents)

        values, _ = _parse_property_values(
            prop_type, count, body, offset, self.shared_strings
        )

        for i, ref in enumerate(referents):
            if i >= len(values):
                break
            inst = instances.get(ref)
            if not inst:
                continue
            val = values[i]
            inst.properties[prop_name] = val

            if prop_name == "Name" and isinstance(val, str):
                inst.name = val
            elif prop_name == "Source":
                if isinstance(val, tuple):
                    kind, payload = val
                    if kind == "source":
                        inst.source = payload
                    else:
                        inst.bytecode = payload
                elif isinstance(val, str):
                    inst.source = val
                elif isinstance(val, bytes):
                    inst.bytecode = val
            elif prop_name == "Bytecode" and isinstance(val, (bytes, tuple)):
                if isinstance(val, tuple):
                    inst.bytecode = val[1]
                else:
                    inst.bytecode = val

    def _parse_prnt(self, body: bytes, instances: Dict[int, RbxInstance], model: RbxModel):
        offset = 0
        version, offset = _read_u8(body, offset)
        count, offset = _read_u32(body, offset)

        children, offset = _interleaved_i32(body, count, offset)
        parents, offset = _interleaved_i32(body, count, offset)

        for child_ref, parent_ref in zip(children, parents):
            child = instances.get(child_ref)
            if not child:
                continue
            if parent_ref == -1 or parent_ref not in instances:
                child.parent = None
                if child_ref not in model.roots:
                    model.roots.append(child_ref)
            else:
                child.parent = parent_ref
                parent = instances[parent_ref]
                if child_ref not in parent.children:
                    parent.children.append(child_ref)


def parse_rbxm(path: Union[str, Path, bytes]) -> RbxModel:
    """
    Unified entry: auto-detect binary (.rbxm) vs XML (.rbxmx) and parse.
    """
    if isinstance(path, (str, Path)):
        raw = Path(path).read_bytes()
    else:
        raw = path

    stripped = raw.lstrip()
    # XML detection
    if stripped.startswith(b"<") or stripped.startswith(b"\xef\xbb\xbf<"):
        from .rbxmx_parser import parse_rbxmx
        return parse_rbxmx(raw)

    # Binary
    if not raw.startswith(b"<roblox!"):
        # last chance: maybe XML with BOM already stripped poorly
        if b"<roblox" in raw[:200]:
            from .rbxmx_parser import parse_rbxmx
            return parse_rbxmx(raw)
        raise ValueError(
            "Unrecognized Roblox file. Expected binary .rbxm (<roblox!) or XML .rbxmx."
        )

    return RbxmParser().parse(raw)
