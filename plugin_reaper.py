#!/usr/bin/env python3
"""
PluginReaper v2 — Peak Roblox Plugin Reverse Engineering Tool

Extract any .rbxm / .rbxmx plugin into a clean developer source tree.
Deep analysis, search, Rojo scaffold, source cleaning.

Usage:
  python plugin_reaper.py <plugin.rbxm|rbxmx> -o ./out [--decompile] [--beautify] [--clean]
  python plugin_reaper.py --from-id <assetId> -o ./out
  python plugin_reaper.py --list-installed
  python plugin_reaper.py --search ./recovered "loadstring"
  python plugin_reaper.py --scan ./recovered
"""

from __future__ import annotations

import argparse
import json
import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.rbxm_parser import parse_rbxm
from core.extractor import extract_plugin, PluginExtractor
from core.decompiler import process_bytecode_files, find_external_decompiler
from core.analyzer import analyze_model, write_analysis
from core.search import search_tree, scan_patterns
from core.project_gen import generate_rojo_project, generate_readme, generate_script_index
from core.prettier import clean_tree
from core.rebuild import rebuild_plugin
from utils.paths import (
    find_plugin_rbxm,
    list_installed_plugins,
    get_local_plugins_dir,
    get_installed_plugins_dir,
)


BANNER = r"""
╔══════════════════════════════════════════════════════════╗
║           PluginReaper  v2.0  —  PEAK EDITION            ║
║   extract • analyze • search • rojo • recover            ║
╚══════════════════════════════════════════════════════════╝
"""


def cmd_extract(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"[!] File not found: {input_path}")
        return 1

    out_dir = Path(args.output) if args.output else Path("output") / input_path.stem
    if out_dir.exists() and args.clean:
        shutil.rmtree(out_dir)

    print(f"[*] Parsing {input_path.name} ...")
    try:
        model = parse_rbxm(input_path)
    except Exception as e:
        print(f"[!] Parse failed: {e}")
        return 1

    fmt = model.metadata.get("format", "binary")
    scripts = model.get_scripts()
    print(f"[+] Format    : {fmt}")
    print(f"[+] Instances : {len(model.instances)}")
    print(f"[+] Scripts   : {len(scripts)}")
    print(f"[+] Roots     : {len(model.roots)}")

    print(f"[*] Extracting hierarchy → {out_dir}")
    extractor = PluginExtractor(model, out_dir)
    result = extractor.extract()

    if args.decompile:
        print("[*] Bytecode recovery pass ...")
        n = process_bytecode_files(result)
        print(f"[+] Processed {n} bytecode file(s)")
        tool = find_external_decompiler()
        if tool:
            print(f"[+] External decompiler: {tool}")
        else:
            print("[*] No external decompiler on PATH — inspection reports only")

    print("[*] Deep analysis ...")
    analysis = analyze_model(model)
    report = write_analysis(analysis, result)
    print(f"[+] Analysis  → {report.name}")
    print(f"    entries   : {analysis.stats.get('entry_points')}")
    print(f"    high risk : {analysis.stats.get('high_risk_count')}")
    print(f"    lines     : {analysis.stats.get('total_lines')}")

    generate_rojo_project(result, project_name=input_path.stem)
    generate_script_index(result)
    meta = {
        "instance_count": len(model.instances),
        "script_count": len(scripts),
        "metadata": model.metadata,
    }
    generate_readme(result, meta)
    print("[+] Rojo project + script index written")

    if args.beautify:
        n = clean_tree(result, strip_header=True)
        print(f"[+] Beautified {n} source file(s)")

    print()
    print(f"[✓] Done → {result.resolve()}")
    print(f"    open _analysis.txt for entry points / risk / require graph")
    return 0


def cmd_from_id(args: argparse.Namespace) -> int:
    rbxm = find_plugin_rbxm(args.asset_id)
    if not rbxm:
        print(f"[!] Plugin {args.asset_id} not found in InstalledPlugins cache.")
        root = get_installed_plugins_dir()
        if root:
            print(f"    Searched: {root}")
        return 1
    print(f"[+] Found: {rbxm}")
    args.input = str(rbxm)
    return cmd_extract(args)


def cmd_list_installed(args: argparse.Namespace) -> int:
    plugins = list_installed_plugins()
    if not plugins:
        print("[*] No installed plugins in cache.")
        print(f"    Expected: {get_installed_plugins_dir()}")
        return 0
    print(f"[+] {len(plugins)} cached plugin(s):\n")
    for p in sorted(plugins, key=lambda x: x["id"]):
        print(f"  {p['id']:>12}  {p['size']/1024:8.1f} KB  {p['path']}")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.scan_dir)
    if not root.is_dir():
        print(f"[!] Not a directory: {root}")
        return 1
    print(f"[*] Pattern scan → {root}")
    results = scan_patterns(root)
    total = 0
    for name, hits in results.items():
        if hits:
            total += len(hits)
            print(f"\n[{name}] {len(hits)} hit(s)")
            for h in hits[:8]:
                print(f"  {h['file']}:{h['line']}  {h['text'][:100]}")
            if len(hits) > 8:
                print(f"  ... +{len(hits)-8} more")
    out = root / "_scan_results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n[+] {total} total hits → {out}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    root = Path(args.search_dir)
    if not root.is_dir():
        print(f"[!] Not a directory: {root}")
        return 1
    hits = search_tree(
        root,
        args.query,
        regex=args.regex,
        case_insensitive=not args.case_sensitive,
        max_hits=args.max_hits,
    )
    print(f"[*] Search '{args.query}' → {len(hits)} hit(s)\n")
    for h in hits:
        print(f"  {h.file}:{h.line}")
        print(f"    {h.text}")
    return 0



def cmd_rebuild(args: argparse.Namespace) -> int:
    src = Path(args.rebuild_dir)
    if not src.is_dir():
        print(f"[!] Not a directory: {src}")
        return 1
    out = Path(args.output) if args.output else src.parent / f"{src.name}_plugin.rbxmx"
    print(f"[*] Rebuilding plugin from {src}")
    try:
        result = rebuild_plugin(src, out)
    except Exception as e:
        print(f"[!] Rebuild failed: {e}")
        return 1
    print(f"[✓] Plugin written → {result.resolve()}")
    print("    Install: copy to %LOCALAPPDATA%\\Roblox\\Plugins\\")
    print("    Or in Studio: right-click model → Save as Local Plugin / Publish as Plugin")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser(
        description="PluginReaper v2 — peak Roblox plugin reverse engineering",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input", nargs="?", help="Path to .rbxm / .rbxmx")
    parser.add_argument("-o", "--output", help="Output directory")
    parser.add_argument("--decompile", action="store_true", help="Bytecode recovery pass")
    parser.add_argument("--beautify", action="store_true", help="Clean extracted sources")
    parser.add_argument("--clean", action="store_true", help="Wipe output dir first")
    parser.add_argument("--from-id", dest="asset_id", help="Extract from InstalledPlugins by asset ID")
    parser.add_argument("--list-installed", action="store_true")
    parser.add_argument("--scan-plugins", action="store_true", help="List local plugin locations")
    parser.add_argument("--rebuild", dest="rebuild_dir", help="Rebuild extracted tree back into .rbxmx plugin")
    parser.add_argument("--scan", dest="scan_dir", help="Security pattern scan on extracted tree")
    parser.add_argument("--search", dest="search_dir", help="Directory to search")
    parser.add_argument("query", nargs="?", help="Search query (with --search)")
    parser.add_argument("--regex", action="store_true", help="Treat search query as regex")
    parser.add_argument("--case-sensitive", action="store_true")
    parser.add_argument("--max-hits", type=int, default=200)

    args = parser.parse_args()
    print(BANNER)

    if args.list_installed or args.scan_plugins:
        return cmd_list_installed(args)
    if args.scan_dir:
        return cmd_scan(args)
    if args.search_dir:
        if not args.query:
            print("[!] --search needs a query")
            return 1
        return cmd_search(args)
    if args.asset_id:
        return cmd_from_id(args)
    if not args.input:
        parser.print_help()
        return 1
    return cmd_extract(args)


if __name__ == "__main__":
    sys.exit(main())
