"""
PluginReaper - Luau Bytecode Decompiler Bridge
Attempts recovery when Source is stripped and only bytecode remains.

Strategy (in priority order):
1. External high-quality offline decompiler if present on PATH or configured
2. Basic disassembly + constant recovery (always available, pure Python)
3. Mark file for manual / external pass

This module never phones home. Everything stays local.
"""

from __future__ import annotations

import struct
import subprocess
import shutil
from pathlib import Path
from typing import List, Optional, Tuple


# Known good offline tools (user can drop binaries next to PluginReaper)
EXTERNAL_DECOMPILERS = [
    "luau-decompiler",          # PumbaaDev
    "luauDec",
    "unluau",
    "Oracle",
]


def find_external_decompiler() -> Optional[str]:
    for name in EXTERNAL_DECOMPILERS:
        path = shutil.which(name)
        if path:
            return path
    # also check local tools/ folder
    local = Path(__file__).resolve().parent.parent / "tools"
    if local.is_dir():
        for name in EXTERNAL_DECOMPILERS:
            candidate = local / name
            if candidate.exists():
                return str(candidate)
            # windows
            candidate = local / f"{name}.exe"
            if candidate.exists():
                return str(candidate)
    return None


def decompile_with_external(bytecode: bytes, tool: str) -> Optional[str]:
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".luac", delete=False) as tmp:
        tmp.write(bytecode)
        tmp_path = tmp.name
    try:
        # most tools accept: tool input.luac -o output.luau
        out_path = tmp_path + ".luau"
        result = subprocess.run(
            [tool, tmp_path, "-o", out_path],
            capture_output=True,
            timeout=60,
        )
        if result.returncode == 0 and Path(out_path).exists():
            return Path(out_path).read_text(encoding="utf-8", errors="replace")
        # alternative: tool just prints to stdout
        if result.stdout:
            return result.stdout.decode("utf-8", errors="replace")
    except Exception:
        pass
    finally:
        Path(tmp_path).unlink(missing_ok=True)
        Path(tmp_path + ".luau").unlink(missing_ok=True)
    return None


# ---------------------------------------------------------------------------
# Minimal pure-Python Luau bytecode inspector
# (not a full decompiler — recovers strings, numbers, function headers)
# ---------------------------------------------------------------------------

def _read_varint(data: bytes, offset: int) -> Tuple[int, int]:
    result = 0
    shift = 0
    while offset < len(data):
        b = data[offset]
        offset += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, offset


def inspect_bytecode(bytecode: bytes) -> str:
    """
    Produce a readable inspection report + recovered constants.
    Useful when no external decompiler is available.
    """
    lines: List[str] = [
        "--[[ PluginReaper Bytecode Inspection ]]",
        f"-- Size: {len(bytecode)} bytes",
        "",
    ]

    if not bytecode:
        lines.append("-- empty")
        return "\n".join(lines)

    # Luau bytecode typically starts with version byte
    version = bytecode[0] if bytecode else 0
    lines.append(f"-- Bytecode version byte: {version}")

    # Recover printable strings (naive but effective for constants)
    strings: List[str] = []
    i = 0
    while i < len(bytecode) - 4:
        # length-prefixed strings are common
        try:
            length = struct.unpack_from("<I", bytecode, i)[0]
            if 4 <= length <= 512 and i + 4 + length <= len(bytecode):
                chunk = bytecode[i + 4 : i + 4 + length]
                if all(32 <= b < 127 or b in (9, 10, 13) for b in chunk):
                    s = chunk.decode("ascii", errors="ignore")
                    if len(s) >= 3 and s not in strings:
                        strings.append(s)
                    i += 4 + length
                    continue
        except Exception:
            pass
        i += 1

    # also scan for raw ASCII runs
    current = []
    for b in bytecode:
        if 32 <= b < 127:
            current.append(chr(b))
        else:
            if len(current) >= 6:
                s = "".join(current)
                if s not in strings:
                    strings.append(s)
            current = []
    if len(current) >= 6:
        s = "".join(current)
        if s not in strings:
            strings.append(s)

    if strings:
        lines.append("-- Recovered string constants:")
        for s in strings[:80]:
            safe = s.replace("\n", "\\n").replace("\r", "\\r")
            lines.append(f"--   {safe!r}")
        if len(strings) > 80:
            lines.append(f"--   ... and {len(strings) - 80} more")
    else:
        lines.append("-- No obvious string constants recovered")

    lines.append("")
    lines.append("-- To fully decompile: place a Luau decompiler binary")
    lines.append("-- (luau-decompiler / Oracle / etc.) in PluginReaper/tools/")
    lines.append("-- or on PATH, then re-run with --decompile")
    lines.append("")
    lines.append("return nil -- placeholder; replace after external decompile")

    return "\n".join(lines)


def decompile_bytecode(bytecode: bytes) -> str:
    """
    Best-effort decompile. Returns recovered source or inspection report.
    """
    tool = find_external_decompiler()
    if tool:
        result = decompile_with_external(bytecode, tool)
        if result and len(result.strip()) > 20:
            header = (
                "--[[ Decompiled by external tool via PluginReaper ]]\n"
                f"-- Tool: {tool}\n\n"
            )
            return header + result

    return inspect_bytecode(bytecode)


def process_bytecode_files(root: Path) -> int:
    """
    Walk an extraction folder, find *.bc files, produce sibling .luau recoveries.
    Returns number of files processed.
    """
    count = 0
    for bc_path in root.rglob("*.bc"):
        bytecode = bc_path.read_bytes()
        recovered = decompile_bytecode(bytecode)
        # write next to the original script that referenced it
        out_path = bc_path.with_suffix("")  # strip .bc → leaves .luau or .server.luau etc
        if not out_path.suffix:
            out_path = out_path.with_suffix(".luau")
        # if a placeholder already exists, overwrite with better content
        out_path.write_text(recovered, encoding="utf-8")
        count += 1
    return count
