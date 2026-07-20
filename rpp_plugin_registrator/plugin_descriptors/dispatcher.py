from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from .core import infer_language_from_path, ParsePluginTypeResult, ParsePluginResult
from .cpp import parse_cpp_plugin
from .python import parse_python_plugin
from .capnp import parse_capnp_plugin


def parse_plugin_file(source_file: Union[str, Path], plugin_id_override: Optional[str] = None) -> ParsePluginResult:
    """Dispatcher function that detects language and parses plugin file."""
    if isinstance(source_file, str):
        source_file = Path(source_file)
    language = infer_language_from_path(source_file)
    if language == "python":
        return parse_python_plugin(source_file, plugin_id_override)
    if language == "cpp":
        return parse_cpp_plugin(source_file, plugin_id_override)
    raise ValueError(f"Unsupported source language for file '{source_file}'.")

def parse_plugin_type_file(source_file: Union[str, Path],
            plugin_id_override: Optional[str] = None,
            relative_to_source: bool = False) -> ParsePluginTypeResult:
    """Dispatcher function that detects language and parses plugin file."""
    if isinstance(source_file, str):
        source_file = Path(source_file)
    language = infer_language_from_path(source_file)
    if language is "capnp":
        return parse_capnp_plugin(source_file, plugin_id_override, relative_to_source=relative_to_source)
    raise ValueError(f"Unsupported source language for file '{source_file}'.")
