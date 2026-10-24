"""
PluginReaper — Doctor: health check on extracted / edited tree before rebuild.
Catches empty scripts, broken requires, missing init, huge files, etc.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List


@dataclass
class Issue:
    severity: str  # error | warn | info
    path: str
    message: str


RE_REQUIRE_SCRIPT = re.compile(
    r"""require\s*\(\s*script((?:\s*\.\s*\w+)+)\s*\)""", re.I
)


def doctor_tree(root: Path) -> List[Issue]:
    root = Path(root)
    issues: List[Issue] = []
    scripts = list(root.rglob("*.luau")) + list(root.rglob("*.lua"))
    scripts = [p for p in scripts if not p.name.startswith("_")]

    if not scripts:
        issues.append(Issue("error", ".", "No .luau/.lua scripts found in tree"))
        return issues

    # entry point presence
    has_init = any(p.name.startswith("init.") for p in scripts)
    has_server = any(p.name.endswith(".server.luau") or p.name.endswith(".server.lua") for p in scripts)
    if not has_init and not has_server:
        issues.append(
            Issue("warn", ".", "No init.* or *.server.luau entry script found")
        )

    for path in scripts:
        rel = str(path.relative_to(root)).replace("\\", "/")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            issues.append(Issue("error", rel, f"Cannot read: {e}"))
            continue

        stripped = text.strip()
        if not stripped or stripped.startswith("--[[ EMPTY") or "BYTECODE ONLY" in stripped[:200]:
            issues.append(Issue("warn", rel, "Empty or bytecode-only placeholder"))
            continue

        lines = text.count("\n") + 1
        if lines > 5000:
            issues.append(Issue("warn", rel, f"Very large script ({lines} lines)"))

        # relative requires — check path exists roughly
        for m in RE_REQUIRE_SCRIPT.finditer(text):
            chain = m.group(1).replace(" ", "").split(".")
            chain = [c for c in chain if c]
            # script.foo.bar → sibling/child under same parent
            cur = path.parent
            ok = True
            for part in chain:
                # try folder or script file
                folder = cur / part
                file_candidates = [
                    cur / f"{part}.luau",
                    cur / f"{part}.server.luau",
                    cur / f"{part}.client.luau",
                    cur / f"{part}.lua",
                    folder / "init.luau",
                    folder / "init.server.luau",
                ]
                if folder.is_dir():
                    cur = folder
                    continue
                found = next((c for c in file_candidates if c.is_file()), None)
                if found:
                    break
                ok = False
                break
            if not ok:
                issues.append(
                    Issue(
                        "info",
                        rel,
                        f"require(script{m.group(1)}) may not resolve on disk (check after rebuild)",
                    )
                )

        # obvious syntax red flags
        if text.count("function") > text.count("end") + 5:
            issues.append(Issue("info", rel, "Possible unbalanced function/end count"))

    return issues


def write_doctor_report(issues: List[Issue], root: Path) -> Path:
    root = Path(root)
    errors = [i for i in issues if i.severity == "error"]
    warns = [i for i in issues if i.severity == "warn"]
    infos = [i for i in issues if i.severity == "info"]

    lines = [
        "PluginReaper Doctor",
        "=" * 50,
        f"Errors : {len(errors)}",
        f"Warns  : {len(warns)}",
        f"Info   : {len(infos)}",
        "",
    ]
    for label, group in (("ERRORS", errors), ("WARNINGS", warns), ("INFO", infos)):
        if not group:
            continue
        lines.append(label)
        lines.append("-" * 30)
        for i in group:
            lines.append(f"  [{i.severity}] {i.path}")
            lines.append(f"           {i.message}")
        lines.append("")

    if not issues:
        lines.append("All clear. Tree looks healthy for rebuild.")

    path = root / "_doctor.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
