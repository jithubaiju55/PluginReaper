# PluginReaper Architecture

## Goal

Turn any Roblox plugin (protected or open) into a clean, readable source tree that looks like the original developer’s project layout.

## Pipeline

```
Input (.rbxm / cached Plugin.rbxm)
        │
        ▼
┌───────────────────┐
│  RBXM Binary      │  core/rbxm_parser.py
│  Parser           │  • Header + chunk stream
│                   │  • INST / PROP / PRNT / SSTR / META
│                   │  • LZ4 + ZSTD decompression
└─────────┬─────────┘
          │  RbxModel (instances + hierarchy + Source/Bytecode)
          ▼
┌───────────────────┐
│  Hierarchy        │  core/extractor.py
│  Extractor        │  • Walk tree
│                   │  • Folders for structural instances
│                   │  • .luau files for scripts
│                   │  • Sanitize names, unique collision handling
└─────────┬─────────┘
          │  Clean folder tree
          ▼
┌───────────────────┐
│  Bytecode         │  core/decompiler.py  (optional --decompile)
│  Recovery         │  • External tool bridge
│                   │  • Pure-Python constant inspector
└───────────────────┘
```

## Binary Format (Version 0)

- Magic: `<roblox!`
- Chunks: name[4] + compressedLen + uncompressedLen + body
- Key chunks used:
  - `INST` — class → list of instance referents
  - `PROP` — property values (including ProtectedString = Source/Bytecode)
  - `PRNT` — parent/child links
  - `SSTR` — shared string table
  - `META` — file metadata

## Script Handling

| Class         | Output suffix   |
|---------------|-----------------|
| Script        | .server.luau    |
| LocalScript   | .client.luau    |
| ModuleScript  | .luau           |
| CoreScript    | .core.luau      |

When only bytecode is present the extractor writes:

- `Name.server.luau` (placeholder comment)
- `Name.server.luau.bc` (raw bytecode)

`--decompile` then overwrites the placeholder with recovered source or an inspection report.

## Path Resolution

`utils/paths.py` locates:

- InstalledPlugins cache (per user ID)
- Local Plugins folder
- Studio Versions / BuiltInPlugins

So `--from-id` and `--list-installed` work without the user hunting files.

## Design Rules

- Zero network
- Zero code execution of the target plugin
- Stdlib-first; compression libs are optional but recommended
- Output must be immediately readable by a human developer
