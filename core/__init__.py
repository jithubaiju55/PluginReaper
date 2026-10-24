from .rbxm_parser import parse_rbxm, RbxModel, RbxInstance, RbxmParser
from .rbxmx_parser import parse_rbxmx, RbxmxParser
from .extractor import extract_plugin, PluginExtractor
from .decompiler import decompile_bytecode, process_bytecode_files, find_external_decompiler
from .analyzer import analyze_model, write_analysis, AnalysisResult
from .search import search_tree, scan_patterns
from .project_gen import generate_rojo_project, generate_script_index
from .prettier import clean_tree
from .rebuild import rebuild_plugin
from .diffmap import diff_trees, write_diff_report, snapshot_tree
from .api_index import write_api_index
from .safe_patch import inject_toolbar_button, inject_settings_helpers, inject_dock_widget
from .doctor import doctor_tree, write_doctor_report


__all__ = [
    "parse_rbxm", "parse_rbxmx", "RbxModel", "RbxInstance", "RbxmParser", "RbxmxParser",
    "extract_plugin", "PluginExtractor",
    "decompile_bytecode", "process_bytecode_files", "find_external_decompiler",
    "analyze_model", "write_analysis", "AnalysisResult",
    "search_tree", "scan_patterns",
    "generate_rojo_project", "generate_script_index", "clean_tree",
    "rebuild_plugin",
    "diff_trees", "write_diff_report", "snapshot_tree",
    "write_api_index", "doctor_tree", "write_doctor_report",
]
