"""
PluginReaper path helpers — locate Roblox plugin caches on Windows / Linux / macOS.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional


def get_roblox_versions_dir() -> Optional[Path]:
    """Studio versions folder (contains BuiltInPlugins)."""
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            p = Path(local) / "Roblox" / "Versions"
            if p.is_dir():
                return p
    # Linux / Wine / macOS common paths
    candidates = [
        Path.home() / ".local" / "share" / "roblox" / "versions",
        Path.home() / "Library" / "Application Support" / "Roblox" / "Versions",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


def get_installed_plugins_dir(user_id: Optional[str] = None) -> Optional[Path]:
    """
    %LOCALAPPDATA%\\Roblox\\<userId>\\InstalledPlugins
    Each plugin is a folder named by asset ID containing version subfolders + Plugin.rbxm
    """
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if not local:
            return None
        base = Path(local) / "Roblox"
        if user_id:
            p = base / user_id / "InstalledPlugins"
            return p if p.is_dir() else None
        # auto-detect first numeric folder
        if base.is_dir():
            for child in base.iterdir():
                if child.is_dir() and child.name.isdigit():
                    candidate = child / "InstalledPlugins"
                    if candidate.is_dir():
                        return candidate
    return None


def get_local_plugins_dir() -> Optional[Path]:
    """User Plugins folder (local .rbxm plugins)."""
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            p = Path(local) / "Roblox" / "Plugins"
            return p if p.is_dir() else p  # may not exist yet
    return Path.home() / ".local" / "share" / "roblox" / "plugins"


def find_plugin_rbxm(plugin_id: str) -> Optional[Path]:
    """Locate Plugin.rbxm for a given asset ID inside InstalledPlugins."""
    root = get_installed_plugins_dir()
    if not root:
        return None
    plugin_folder = root / plugin_id
    if not plugin_folder.is_dir():
        return None
    # newest version first
    versions = sorted(
        [d for d in plugin_folder.iterdir() if d.is_dir()],
        key=lambda d: d.name,
        reverse=True,
    )
    for v in versions:
        candidate = v / "Plugin.rbxm"
        if candidate.is_file():
            return candidate
    # sometimes directly in folder
    direct = plugin_folder / "Plugin.rbxm"
    if direct.is_file():
        return direct
    return None


def list_installed_plugins() -> List[dict]:
    """Return list of {id, path, size} for all cached plugins."""
    root = get_installed_plugins_dir()
    results = []
    if not root or not root.is_dir():
        return results
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        rbxm = find_plugin_rbxm(folder.name)
        if rbxm:
            results.append({
                "id": folder.name,
                "path": str(rbxm),
                "size": rbxm.stat().st_size,
            })
    return results
