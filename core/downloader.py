"""
PluginReaper — Download plugin models for local scanning.

Supports:
  - Roblox asset delivery URLs
  - Direct .rbxm / .rbxmx links
  - Asset ID via Roblox economy/assetdelivery (best-effort)

Never auto-executes downloaded code. Scan-only workflow.
"""

from __future__ import annotations

import re
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Tuple


ASSET_ID_RE = re.compile(r"(?:www\.)?roblox\.com/(?:library|catalog|store/asset|bundles)/(\d+)", re.I)
ASSET_ID_PLAIN = re.compile(r"^\d{5,}$")
CREATE_ASSET = re.compile(r"create\.roblox\.com/.*?(\d{5,})", re.I)


def extract_asset_id(url_or_id: str) -> Optional[str]:
    s = url_or_id.strip()
    if ASSET_ID_PLAIN.match(s):
        return s
    for pat in (ASSET_ID_RE, CREATE_ASSET):
        m = pat.search(s)
        if m:
            return m.group(1)
    # assetdelivery URL
    m = re.search(r"id=(\d+)", s)
    if m:
        return m.group(1)
    return None


def _fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "PluginReaper/2.0 (local security scanner; offline analysis)",
            "Accept": "*/*",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def download_plugin(
    url_or_id: str,
    dest_dir: Path,
    *,
    filename: Optional[str] = None,
) -> Tuple[Path, str]:
    """
    Download a plugin/model file for scanning.
    Returns (path, note).
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    asset_id = extract_asset_id(url_or_id)
    data: Optional[bytes] = None
    note = ""

    candidates = []
    if asset_id:
        # Official asset delivery (may require auth for some assets; try public)
        candidates.append(
            (
                f"https://assetdelivery.roblox.com/v1/asset/?id={asset_id}",
                f"assetdelivery:{asset_id}",
            )
        )
        candidates.append(
            (
                f"https://www.roblox.com/asset/?id={asset_id}",
                f"roblox-asset:{asset_id}",
            )
        )
    if url_or_id.startswith("http://") or url_or_id.startswith("https://"):
        candidates.insert(0, (url_or_id, "direct-url"))

    last_err = None
    for url, label in candidates:
        try:
            data = _fetch(url)
            note = f"fetched via {label} ({len(data)} bytes)"
            break
        except Exception as e:
            last_err = e
            continue

    if data is None:
        raise RuntimeError(
            f"Download failed. Last error: {last_err}. "
            "Try a direct .rbxm/.rbxmx URL, or place the file locally and scan it."
        )

    # detect format
    if data.lstrip().startswith(b"<"):
        ext = ".rbxmx"
    elif data.startswith(b"<roblox!"):
        ext = ".rbxm"
    else:
        # often assetdelivery returns binary rbxm without caring
        ext = ".rbxm"

    name = filename or (f"asset_{asset_id}{ext}" if asset_id else f"download{ext}")
    if not name.endswith((".rbxm", ".rbxmx")):
        name += ext

    out = dest_dir / name
    out.write_bytes(data)
    return out, note
