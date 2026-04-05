from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

from .core import infer_language_from_path
from .cpp import parse_cpp_plugin
from .python import parse_python_plugin


def parse_plugin_file(source_file: Union[str, Path], plugin_id_override: Optional[str] = None) -> Dict[str, Any]:
    """Dispatcher function that detects language and parses plugin file."""
    if isinstance(source_file, str):
        source_file = Path(source_file)
    language = infer_language_from_path(source_file)
    if language == "python":
        return parse_python_plugin(source_file, plugin_id_override)
    if language == "cpp":
        return parse_cpp_plugin(source_file, plugin_id_override)
    raise ValueError(f"Unsupported source language for file '{source_file}'.")
