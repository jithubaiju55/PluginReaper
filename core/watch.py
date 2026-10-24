"""
PluginReaper — Simple watch mode: on file change, re-run doctor (optional rebuild).
Pure stdlib polling so no extra deps.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Dict, Optional


def _fingerprint(root: Path) -> Dict[str, float]:
    fp: Dict[str, float] = {}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".luau", ".lua"):
            continue
        if p.name.startswith("_"):
            continue
        try:
            fp[str(p.relative_to(root))] = p.stat().st_mtime
        except OSError:
            pass
    return fp


def watch_tree(
    root: Path,
    on_change: Callable[[Path], None],
    *,
    interval: float = 1.0,
    stop_after: Optional[float] = None,
) -> None:
    """
    Poll root for script mtime changes. Calls on_change(root) when anything changes.
    stop_after: optional seconds to auto-stop (for tests); None = run forever.
    """
    root = Path(root)
    prev = _fingerprint(root)
    start = time.time()
    print(f"[watch] monitoring {root} (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(interval)
            if stop_after is not None and (time.time() - start) >= stop_after:
                break
            cur = _fingerprint(root)
            if cur != prev:
                changed = [k for k in cur if cur.get(k) != prev.get(k)]
                changed += [k for k in prev if k not in cur]
                print(f"[watch] change detected ({len(changed)} path(s))")
                on_change(root)
                prev = cur
    except KeyboardInterrupt:
        print("\n[watch] stopped")
