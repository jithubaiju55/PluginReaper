"""
PluginReaper v2 — Deep Script Analyzer
- require / GetService graph
- remote / HTTP / loadstring indicators
- obfuscation heuristics
- entry-point ranking
- dependency tree export
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .rbxm_parser import RbxModel, RbxInstance


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

RE_REQUIRE = re.compile(
    r"""require\s*\(\s*(?:script(?:\s*\.\s*[\w]+)+|game(?:\s*:\s*GetService\s*\(\s*["'][\w]+["']\s*\))?[\w\.\s:\[\]"']*|[\w\.]+)""",
    re.IGNORECASE,
)
RE_REQUIRE_SIMPLE = re.compile(r"""require\s*\(\s*([^)]+)\)""", re.IGNORECASE)
RE_GETSERVICE = re.compile(r"""GetService\s*\(\s*["']([^"']+)["']\s*\)""", re.IGNORECASE)
RE_HTTP = re.compile(
    r"""(?:HttpService|RequestAsync|GetAsync|PostAsync|HttpGet|HttpPost|game\s*:\s*HttpGet)""",
    re.IGNORECASE,
)
RE_LOADSTRING = re.compile(r"""loadstring\s*\(""", re.IGNORECASE)
RE_GETFENV = re.compile(r"""(?:getfenv|setfenv|getmetatable|setmetatable)\s*\(""", re.IGNORECASE)
RE_REMOTE = re.compile(
    r"""(?:RemoteEvent|RemoteFunction|BindableEvent|BindableFunction|UnreliableRemoteEvent)""",
    re.IGNORECASE,
)
RE_FIRE = re.compile(r"""(?:FireServer|InvokeServer|FireClient|InvokeClient|OnServerEvent|OnClientEvent)""", re.IGNORECASE)
RE_PLUGIN_API = re.compile(
    r"""(?:plugin\s*:\s*(?:CreateToolbar|CreateDockWidgetPluginGui|CreatePluginAction|Activate|Deactivate)|PluginGuiService|StudioService)""",
    re.IGNORECASE,
)
RE_OBFUS_HEX = re.compile(r"""\\x[0-9a-fA-F]{2}""")
RE_OBFUS_LONG_STRING = re.compile(r"""["'][^"']{120,}["']""")
RE_OBFUS_NUM_TABLE = re.compile(r"""\{\s*\d+\s*,\s*\d+\s*,\s*\d+""")


@dataclass
class ScriptReport:
    ref: int
    name: str
    class_name: str
    path: str = ""
    lines: int = 0
    chars: int = 0
    requires: List[str] = field(default_factory=list)
    services: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    risk_score: int = 0
    is_entry: bool = False
    has_source: bool = False


@dataclass
class AnalysisResult:
    scripts: List[ScriptReport] = field(default_factory=list)
    require_graph: Dict[str, List[str]] = field(default_factory=dict)
    service_usage: Dict[str, int] = field(default_factory=dict)
    high_risk: List[str] = field(default_factory=list)
    entry_points: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)


def _path_of(model: RbxModel, ref: int) -> str:
    parts: List[str] = []
    cur = model.instances.get(ref)
    seen = set()
    while cur and cur.referent not in seen:
        seen.add(cur.referent)
        parts.append(cur.name or cur.class_name)
        if cur.parent is None:
            break
        cur = model.instances.get(cur.parent)
    return "/".join(reversed(parts))


def analyze_script(inst: RbxInstance, model: RbxModel) -> ScriptReport:
    src = inst.source or ""
    report = ScriptReport(
        ref=inst.referent,
        name=inst.name or inst.class_name,
        class_name=inst.class_name,
        path=_path_of(model, inst.referent),
        lines=src.count("\n") + (1 if src else 0),
        chars=len(src),
        has_source=bool(src),
    )

    if not src:
        report.flags.append("NO_SOURCE")
        return report

    # requires
    for m in RE_REQUIRE_SIMPLE.finditer(src):
        arg = m.group(1).strip()
        if len(arg) < 120:
            report.requires.append(arg)

    # services
    for m in RE_GETSERVICE.finditer(src):
        report.services.append(m.group(1))

    # flags / risk
    risk = 0
    if RE_HTTP.search(src):
        report.flags.append("HTTP")
        risk += 25
    if RE_LOADSTRING.search(src):
        report.flags.append("LOADSTRING")
        risk += 40
    if RE_GETFENV.search(src):
        report.flags.append("ENV_TAMPER")
        risk += 30
    if RE_REMOTE.search(src) or RE_FIRE.search(src):
        report.flags.append("REMOTE")
        risk += 10
    if RE_PLUGIN_API.search(src):
        report.flags.append("PLUGIN_API")
        risk += 0  # normal for plugins
        report.is_entry = True

    # obfuscation signals
    hex_count = len(RE_OBFUS_HEX.findall(src))
    if hex_count > 15:
        report.flags.append("OBFUSC_HEX")
        risk += 20
    if len(RE_OBFUS_LONG_STRING.findall(src)) > 3:
        report.flags.append("OBFUSC_STRINGS")
        risk += 15
    if len(RE_OBFUS_NUM_TABLE.findall(src)) > 5:
        report.flags.append("OBFUSC_NUMTABLE")
        risk += 15

    # dense / minified
    if report.lines > 0 and report.chars / max(report.lines, 1) > 200:
        report.flags.append("MINIFIED")
        risk += 10

    report.risk_score = min(risk, 100)

    # entry heuristics
    low = (inst.name or "").lower()
    if low in ("init", "main", "launcher", "bootstrap", "plugin", "start", "loader"):
        report.is_entry = True
    if inst.class_name == "Script" and inst.parent is None:
        report.is_entry = True

    return report


def analyze_model(model: RbxModel) -> AnalysisResult:
    result = AnalysisResult()
    service_counts: Dict[str, int] = defaultdict(int)
    graph: Dict[str, List[str]] = defaultdict(list)

    scripts = model.get_scripts()
    for inst in scripts:
        rep = analyze_script(inst, model)
        result.scripts.append(rep)
        for s in rep.services:
            service_counts[s] += 1
        if rep.requires:
            graph[rep.path or rep.name] = rep.requires
        if rep.risk_score >= 40:
            result.high_risk.append(rep.path or rep.name)
        if rep.is_entry:
            result.entry_points.append(rep.path or rep.name)

    result.require_graph = dict(graph)
    result.service_usage = dict(sorted(service_counts.items(), key=lambda x: -x[1]))
    result.stats = {
        "total_scripts": len(scripts),
        "with_source": sum(1 for s in result.scripts if s.has_source),
        "total_lines": sum(s.lines for s in result.scripts),
        "flagged": sum(1 for s in result.scripts if s.flags),
        "high_risk_count": len(result.high_risk),
        "entry_points": len(result.entry_points),
    }
    return result


def write_analysis(result: AnalysisResult, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # full JSON
    payload = {
        "stats": result.stats,
        "entry_points": result.entry_points,
        "high_risk": result.high_risk,
        "service_usage": result.service_usage,
        "require_graph": result.require_graph,
        "scripts": [asdict(s) for s in sorted(result.scripts, key=lambda x: -x.risk_score)],
    }
    json_path = out_dir / "_analysis.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # human report
    lines = [
        "PluginReaper Deep Analysis",
        "=" * 50,
        f"Scripts        : {result.stats.get('total_scripts')}",
        f"With source    : {result.stats.get('with_source')}",
        f"Total lines    : {result.stats.get('total_lines')}",
        f"Flagged        : {result.stats.get('flagged')}",
        f"High risk      : {result.stats.get('high_risk_count')}",
        "",
        "ENTRY POINTS",
        "-" * 30,
    ]
    for e in result.entry_points[:30]:
        lines.append(f"  * {e}")
    if not result.entry_points:
        lines.append("  (none detected)")

    lines += ["", "HIGH RISK / INTERESTING", "-" * 30]
    risky = [s for s in result.scripts if s.risk_score >= 30]
    for s in sorted(risky, key=lambda x: -x.risk_score)[:40]:
        flags = ",".join(s.flags) if s.flags else "-"
        lines.append(f"  [{s.risk_score:3d}] {s.path or s.name}  ({flags})")
    if not risky:
        lines.append("  (none)")

    lines += ["", "TOP SERVICES", "-" * 30]
    for svc, cnt in list(result.service_usage.items())[:15]:
        lines.append(f"  {svc:30s} {cnt}")

    lines += ["", "REQUIRE GRAPH (sample)", "-" * 30]
    for src, deps in list(result.require_graph.items())[:25]:
        lines.append(f"  {src}")
        for d in deps[:8]:
            lines.append(f"      -> {d}")

    report_path = out_dir / "_analysis.txt"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
