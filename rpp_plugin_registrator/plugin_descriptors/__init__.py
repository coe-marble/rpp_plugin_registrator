from __future__ import annotations

from .core import (
    MethodParam,
    MethodSpec,
    annotation_to_text,
    apply_library_context,
    build_description,
    class_literal_to_python,
    extract_plugin_descriptions,
    extract_plugin_tag,
    infer_language_from_path,
    normalize_plugin_id,
    read_text,
    resolve_plugin_id_override,
)
from .cpp import parse_cpp_plugin
from .dispatcher import parse_plugin_file
from .python import parse_python_plugin

__all__ = [
    "MethodParam",
    "MethodSpec",
    "annotation_to_text",
    "apply_library_context",
    "build_description",
    "class_literal_to_python",
    "extract_plugin_descriptions",
    "extract_plugin_tag",
    "infer_language_from_path",
    "normalize_plugin_id",
    "read_text",
    "resolve_plugin_id_override",
    "parse_cpp_plugin",
    "parse_python_plugin",
    "parse_plugin_file",
]
