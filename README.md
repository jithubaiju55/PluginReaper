# PluginReaper

> **Reverse engineer any Roblox plugin. Scan it for malware. Edit the source. Ship it back.**

PluginReaper is the full loop for developers who like a plugin but wish it did more — and for anyone who installs free/reuploaded plugins and wants to know if they’re safe.

**Download / open → malware scan → extract → analyze → edit / patch → doctor → rebuild → install**

Everything runs locally. Nothing is executed for you. You stay in control.

---

## Contents

- [Why PluginReaper](#why-pluginreaper)
- [Install](#install)
- [Quick start](#quick-start)
- [Command reference](#command-reference)
- [Malware scanner](#malware-scanner)
- [Download for scanning](#download-for-scanning)
- [Extract output](#extract-output)
- [Developer workflow](#developer-workflow)
- [Patch examples](#patch-examples)
- [Analysis, doctor, and diff](#analysis-doctor-and-diff)
- [Supported formats](#supported-formats)
- [Project layout](#project-layout)
- [Tips](#tips)
- [Limitations](#limitations)
- [License and intent](#license-and-intent)

## Why PluginReaper

Two real problems:

| Problem | What you need |
| --- | --- |
| **Almost-perfect plugins** — you want one extra button, a fix, or a setting. Studio won’t give you the source. | Extract the plugin, make your change, and rebuild it. |
| **Dangerous free plugins** — YouTube “paid plugin free” reuploads often hide webhooks, `loadstring(HttpGet)`, clipboard stealers, or obfuscated loaders. They’re hard to spot by eye. | Scan the raw file and extracted source, then review a clear verdict. |

PluginReaper addresses both:

| Problem | PluginReaper solution |
| --- | --- |
| No source | Extract `.rbxm` / `.rbxmx` into a clean developer tree |
| Hidden malware | Raw file scan + full source scan with clear verdict |
| Slow edits | One-command patches (toolbar, settings, dock) |
| Fear of breaking install | Doctor + diff before rebuild |
| Shipping your fix | Rebuild to a Studio-loadable `.rbxmx` |

## Install

```powershell
pip install -r requirements.txt
```

**Optional — compressed binary plugins**

```powershell
pip install zstandard lz4
```

**Optional — bytecode → source:** put a Luau decompiler in `tools/` or on `PATH`.

**Requirements:** Python 3.10+

## Quick start

### Check a plugin before installing

```powershell
# Scan a file without extracting
python .\plugin_reaper.py --malware "C:\Downloads\free_plugin.rbxmx"

# Download an asset for local scanning only (never executes)
python .\plugin_reaper.py --download 1234567890 -o .\downloads
python .\plugin_reaper.py --download "https://example.com/plugin.rbxmx" -o .\downloads
```

### Extract, improve, and ship

```powershell
# Extract, analyze, and scan
python .\plugin_reaper.py "Eclipse Animator.rbxmx" -o .\recovered --clean --beautify
notepad .\recovered_analysis.txt
notepad .\recovered_malware_scan.txt

# Add the feature you wished existed
python .\plugin_reaper.py --patch .\recovered --patch-kind toolbar --button-name "ExportCSV"

# Health check
python .\plugin_reaper.py --doctor .\recovered

# Rebuild the plugin
python .\plugin_reaper.py --rebuild .\recovered -o .\MyPlugin_modded.rbxmx
```

Copy `MyPlugin_modded.rbxmx` to `%LOCALAPPDATA%\Roblox\Plugins\` or use **Studio → Save as Local Plugin**.

## Command reference

### Core

| Command | What it does |
| --- | --- |
| `plugin_reaper.py <file> -o ./out` | Extract plugin → source tree |
| `--clean` | Wipe output dir first |
| `--beautify` | Clean headers / whitespace |
| `--decompile` | Bytecode recovery pass |
| `--from-id <assetId>` | Extract from Studio InstalledPlugins cache |
| `--list-installed` | List cached plugins |
| `--rebuild ./out -o plugin.rbxmx` | Edited tree → installable plugin |

### Security

| Command | What it does |
| --- | --- |
| <code>--malware &lt;file&#124;folder&gt;</code> | Malware / abuse scan (raw and/or source) |
| `--malware file --tree ./out` | Combine raw file + extracted tree |
| <code>--download &lt;url&#124;id&gt; -o ./dir</code> | Download for scan only (no execute) |

### Developer speed

| Command | What it does |
| --- | --- |
| `--patch ./out --patch-kind toolbar` | Inject toolbar button stub |
| `--patch-kind settings` | Inject GetSetting/SetSetting helpers |
| `--patch-kind dock` | Inject dock widget + frame stub |
| `--doctor ./out` | Health check before rebuild |
| `--api-index ./out` | Services, plugin APIs, requires index |
| `--snapshot ./out` | Snapshot scripts for later diff |
| `--diff ./snap ./out` | Show what you changed |
| `--search ./out "query"` | Full-text search |
| `--search ./out "pattern" --regex` | Regex search |
| `--scan ./out` | Behavior pattern scan |
| `--watch ./out` | Re-run doctor on file changes |

## Malware scanner

Built for the exact threat model: reuploaded paid plugins with extra malicious code.

### What it detects

| Severity | Examples |
| --- | --- |
| **Critical** | Discord webhooks, `loadstring(HttpGet)`, clipboard steal APIs |
| **High** | `RequestAsync` exfil, `getfenv` / `setfenv`, `writefile`, debug abuse, heavy obfuscation |
| **Medium** | External HTTP hosts, numeric packers, teleport / purchase spam patterns |
| **Low / info** | Normal plugin APIs (toolbar, settings) |

### Scan modes

| Mode | Description |
| --- | --- |
| **Raw** | Scans `.rbxm` / `.rbxmx` bytes and embedded text without full reverse engineering. Fast pre-check. |
| **Tree** | Scans every extracted `.luau` after RE. Deep. |
| **Both** | Used when you pass `--malware file --tree ./recovered`, and automatically on extract. |

### Verdicts

| Verdict | Meaning |
| --- | --- |
| `clean` | No strong signals |
| `review` | Medium signals — read the report |
| `suspicious` | High-risk patterns — do not install blindly |
| `malicious` | Critical indicators (webhook / remote loader / exfil) |

Reports: `_malware_scan.txt`, `_malware_scan.json`.

> **Important:** A clean verdict is not a guarantee. Obfuscation evolves. Always treat random free reuploads as untrusted until you understand the source.

## Download for scanning

```powershell
python .\plugin_reaper.py --download 1234567890 -o .\downloads
python .\plugin_reaper.py --download "https://..." -o .\downloads
```

- Saves the file locally
- Runs a quick raw malware scan
- Does not execute plugin code
- Private/paid assets may fail on public assetdelivery — place the file manually and use `--malware` instead

Use this when someone sends a “free plugin” link and you want a verdict before Studio ever sees it.

## Extract output

```text
recovered/
├── <PluginRoot>/
│   ├── init.server.luau
│   └── ... hierarchy ...
├── _plugin_meta.json
├── _extraction_summary.txt
├── _analysis.txt / _analysis.json       # entry points, risk, require graph
├── _malware_scan.txt / .json            # security verdict
├── _doctor.txt                          # health before rebuild
├── _api_index.txt / .json               # GetService + plugin APIs
├── _script_index.csv
├── default.project.json                 # Rojo
└── README_RECOVERED.md
```

Script suffixes:

| Suffix | Class |
| --- | --- |
| `.server.luau` | Script |
| `.client.luau` | LocalScript |
| `.luau` | ModuleScript |

## Developer workflow

### The life-saver path

1. **Extract** — also runs malware scan, doctor, API index, and snapshot.
2. **Review** — read `_malware_scan.txt` and `_analysis.txt`.
3. **Modify** — use `--patch` or hand-edit `.luau` files.
4. **Verify** — run `--doctor` and compare with `--diff` against the snapshot.
5. **Rebuild** — create the `.rbxmx`.
6. **Install** — put it in the Plugins folder or publish as a local plugin.

## Patch examples

```powershell
python .\plugin_reaper.py --patch .\recovered --patch-kind toolbar --button-name "MyFeature" --tooltip "Does the thing"
python .\plugin_reaper.py --patch .\recovered --patch-kind settings
python .\plugin_reaper.py --patch .\recovered --patch-kind dock
```

Stubs are appended to the entry script (`init.server.luau` when present). Fill in the TODO section, then rebuild.

## Analysis, doctor, and diff

- **Analysis** ranks entry points, builds a require graph sample, maps `GetService` usage, and flags HTTP / loadstring / obfuscation / remotes.
- **Doctor** checks for empty scripts, missing entry points, unresolved `require(script...)` paths, and oversized files before you rebuild.
- **Diff** compares a snapshot to your current tree so you only ship intentional changes.

## Supported formats

| Input | Support |
| --- | --- |
| `.rbxmx` (XML) | Native |
| `.rbxm` (binary) | Native (LZ4/ZSTD with optional deps) |
| Source-stripped / bytecode | Hierarchy always; `.bc` dump; external decompiler via `--decompile` |

## Project layout

```text
PluginReaper/
├── plugin_reaper.py
├── requirements.txt
├── README.md
├── LICENSE
├── .gitignore
├── core/
│   ├── rbxm_parser.py / rbxmx_parser.py
│   ├── extractor.py / rebuild.py
│   ├── analyzer.py / search.py / decompiler.py
│   ├── malware_scan.py / downloader.py
│   ├── doctor.py / diffmap.py / api_index.py
│   ├── safe_patch.py / watch.py
│   └── project_gen.py / prettier.py
├── utils/paths.py
└── tools/ # optional decompilers
```

## Tips

- Run `--malware` on any plugin from a random YouTube/Discord link before installing.
- Prefer extract + read `_malware_scan.txt` + `_analysis.txt` before editing.
- Use `--patch` for the common “one more button” request, then edit the stub.
- Always run `--doctor` after large edits.
- Keep the original file; re-extract if a rebuild goes wrong.
- A clean verdict does not mean you have permission to redistribute someone else’s work.

## Limitations

- Rebuild writes `.rbxmx` (XML) — Studio accepts it as a plugin; binary write is not implemented.
- Rebuild is optimized for script-centric plugins (UI/value trees are not fully re-serialized).
- Malware scan is signature/heuristic-based — novel obfuscation can evade it.
- Download depends on public asset URLs; many paid assets won’t fetch without your own copy.
- Bytecode decompilation quality depends on the external tool you provide.

## License and intent

**MIT** — see `LICENSE`.

PluginReaper is a local RE, security-review, and development aid. Use it on plugins you have the right to inspect. The malware scanner exists so you can refuse bad files — not so you can redistribute cracked paid plugins. Respect authors and Roblox ToS.

---

*PluginReaper — extract, scan, improve, ship.*
