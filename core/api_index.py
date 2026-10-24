"""
PluginReaper — API & dependency index for recovered plugins.
Builds a quick reference: every GetService, plugin API call, require target.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set


RE_GETSERVICE = re.compile(r"""GetService\s*\(\s*["']([^"']+)["']\s*\)""", re.I)
RE_PLUGIN = re.compile(
    r"""plugin\s*:\s*(CreateToolbar|CreateDockWidgetPluginGui|CreatePluginAction|"
    r"Activate|Deactivate|GetMouse|Select|PromptSaveSelection|OpenScript|"
    r"SetSetting|GetSetting|CreateButton)\b""",
    re.I,
)
RE_REQUIRE = re.compile(r"""require\s*\(\s*([^)]+?)\)""", re.I)
RE_FUNC = re.compile(r"""^(?:local\s+)?function\s+([A-Za-z_][\w\.:]*)\s*\(""", re.M)
RE_LOCAL_FUNC = re.compile(
    r"""local\s+function\s+([A-Za-z_]\w*)\s*\(|local\s+([A-Za-z_]\w*)\s*=\s*function\s*\(""",
    re.M,
)


def index_tree(root: Path) -> dict:
    root = Path(root)
    services: Dict[str, List[str]] = defaultdict(list)
    plugin_apis: Dict[str, List[str]] = defaultdict(list)
    requires: Dict[str, List[str]] = defaultdict(list)
    functions: Dict[str, List[str]] = defaultdict(list)

    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in (".luau", ".lua"):
            continue
        if path.name.startswith("_"):
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for m in RE_GETSERVICE.finditer(text):
            services[m.group(1)].append(rel)
        for m in RE_PLUGIN.finditer(text):
            plugin_apis[m.group(1)].append(rel)
        for m in RE_REQUIRE.finditer(text):
            arg = m.group(1).strip()
            if len(arg) < 100:
                requires[rel].append(arg)
        for m in RE_FUNC.finditer(text):
            functions[rel].append(m.group(1))
        for m in RE_LOCAL_FUNC.finditer(text):
            name = m.group(1) or m.group(2)
            if name:
                functions[rel].append(name)

    # dedupe preserve order
    def dedupe(seq: List[str]) -> List[str]:
        seen: Set[str] = set()
        out = []
        for x in seq:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    services = {k: dedupe(v) for k, v in services.items()}
    plugin_apis = {k: dedupe(v) for k, v in plugin_apis.items()}
    requires = {k: dedupe(v) for k, v in requires.items()}
    functions = {k: dedupe(v) for k, v in functions.items()}

    return {
        "services": dict(sorted(services.items(), key=lambda x: -len(x[1]))),
        "plugin_apis": dict(sorted(plugin_apis.items(), key=lambda x: -len(x[1]))),
        "requires": requires,
        "functions": {k: v[:40] for k, v in functions.items()},  # cap per file
        "stats": {
            "unique_services": len(services),
            "files_with_requires": len(requires),
            "files_indexed": len(set().union(*[set(v) for v in services.values()], set(requires.keys())) or set()),
        },
    }


def write_api_index(root: Path) -> Path:
    data = index_tree(root)
    out = Path(root) / "_api_index.json"
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")

    lines = [
        "PluginReaper API Index",
        "=" * 50,
        f"Services used : {data['stats']['unique_services']}",
        f"Files w/ require: {data['stats']['files_with_requires']}",
        "",
        "SERVICES",
        "-" * 30,
    ]
    for svc, files in list(data["services"].items())[:25]:
        lines.append(f"  {svc}  ({len(files)} files)")
        for f in files[:5]:
            lines.append(f"      {f}")
        if len(files) > 5:
            lines.append(f"      ... +{len(files)-5}")

    lines += ["", "PLUGIN APIS", "-" * 30]
    for api, files in data["plugin_apis"].items():
        lines.append(f"  plugin:{api}  ({len(files)})")
        for f in files[:4]:
            lines.append(f"      {f}")

    txt = Path(root) / "_api_index.txt"
    txt.write_text("\n".join(lines), encoding="utf-8")
    return txt
