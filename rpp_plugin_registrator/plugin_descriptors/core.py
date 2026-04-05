from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils import to_pascal_case, to_snake_case


@dataclass
class MethodParam:
    name: str
    type: str


@dataclass
class MethodSpec:
    name: str
    return_type: str
    params: List[MethodParam]


def normalize_plugin_id(name: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", name.lower())


def infer_language_from_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".cpp", ".cc", ".cxx", ".hpp", ".h"}:
        return "cpp"
    if suffix == ".py":
        return "python"
    raise ValueError(f"Unsupported source extension '{suffix}' for file '{path}'.")


def resolve_plugin_id_override(args: argparse.Namespace) -> Optional[str]:
    return getattr(args, "plugin_id", None) or getattr(args, "id", None)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def annotation_to_text(annotation: Optional[ast.expr]) -> str:
    if annotation is None:
        return "any"
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Attribute):
        value = annotation_to_text(annotation.value)
        return f"{value}.{annotation.attr}"
    if isinstance(annotation, ast.Subscript):
        value = annotation_to_text(annotation.value)
        if isinstance(annotation.slice, ast.Tuple):
            elements = ", ".join(annotation_to_text(elt) for elt in annotation.slice.elts)
            return f"{value}[{elements}]"
        return f"{value}[{annotation_to_text(annotation.slice)}]"
    if isinstance(annotation, ast.Constant):
        return str(annotation.value)
    return "any"


def class_literal_to_python(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return []


def extract_plugin_descriptions(plugin_class: ast.ClassDef) -> Dict[str, Any]:
    descriptions: Dict[str, Any] = {
        "param_description": [],
        "log_description": [],
        "input_description": [],
        "output_description": [],
    }
    for item in plugin_class.body:
        if not isinstance(item, ast.Assign):
            continue
        for target in item.targets:
            if isinstance(target, ast.Name) and target.id in descriptions:
                value = class_literal_to_python(item.value)
                descriptions[target.id] = value if isinstance(value, list) else []
    return descriptions


def extract_plugin_tag(plugin_class: ast.ClassDef) -> Optional[str]:
    for item in plugin_class.body:
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name) and target.id == "tag":
                    value = class_literal_to_python(item.value)
                    if isinstance(value, str):
                        return value
        if isinstance(item, ast.AnnAssign):
            target = item.target
            if isinstance(target, ast.Name) and target.id == "tag" and item.value is not None:
                value = class_literal_to_python(item.value)
                if isinstance(value, str):
                    return value
    return None


def build_description(
    plugin_name: str,
    language: str,
    source_file: Path,
    class_name: Optional[str],
    base_class_name: Optional[str],
    descriptions: Dict[str, Any],
    create_symbol: str,
    destroy_symbol: str,
    methods: List[MethodSpec],
    is_casadi: bool = False,
) -> Dict[str, Any]:

    plugin_obj = {
        "Name": plugin_name,
        "SourceLanguage": language,
        "SourceFile": str(source_file),
        "ClassName": class_name,
        "BaseClassName": base_class_name,
        "IsCasadi": is_casadi,
        "ParamDescription": descriptions.get("param_description", []),
        "LogDescription": descriptions.get("log_description", []),
        "InputDescription": descriptions.get("input_description", []),
        "OutputDescription": descriptions.get("output_description", []),
        "RppRegistration": {
            "Factory": {
                "CreateSymbol": create_symbol,
                "DestroySymbol": destroy_symbol,
            }
        },
        "Interface": {
            "Methods": [
                {
                    "Name": method.name,
                    "ReturnType": method.return_type,
                    "Params": [{"Name": param.name, "Type": param.type} for param in method.params],
                }
                for method in methods
            ]
        },
    }

    return {
        "SchemaVersion": 1,
        "Plugin": plugin_obj,
    }

def apply_library_context(plugin_info: Dict[str, Any], library: str) -> Dict[str, Any]:
    """Apply library context to a plugin info dictionary.

    Updates:
    - Id: <library>_<plugin_name> (lowercase)
    - PluginType: <library>::<ClassName>
    - Library: name of the library

    Args:
        plugin_info: Plugin metadata dictionary
        library: Library name/identifier

    Returns:
        Updated plugin_info with library context
    """
    library_lower = library.lower()
    plugin_class_name = plugin_info["ClassName"]

    # Generate new ID and plugin type
    id_source = plugin_class_name
    new_id = f"{library_lower}_{to_snake_case(id_source)}".lower()

    plugin_info["Id"] = new_id
    plugin_info["Library"] = library_lower
    plugin_info["PluginName"] = f"{library}::{plugin_class_name}"

    return plugin_info
