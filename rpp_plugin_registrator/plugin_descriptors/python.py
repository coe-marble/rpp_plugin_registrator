from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional

from numpy import full

from .core import (
    MethodParam,
    MethodSpec,
    annotation_to_text,
    build_description,
    extract_plugin_descriptions,
    extract_plugin_tag,
    read_text,
)


def parse_python_plugin(source_file: Path, plugin_id: Optional[str]) -> Dict[str, Any]:
    text = read_text(source_file)
    tree = ast.parse(text, filename=str(source_file))

    plugin_class: Optional[ast.ClassDef] = None
    plugin_base_names: List[str] = []

    def _base_name(base: ast.expr) -> Optional[str]:
        if isinstance(base, ast.Name):
            return base.id
        if isinstance(base, ast.Attribute):
            return base.attr
        return None

    def _class_has_plugin_markers(node: ast.ClassDef) -> bool:
        if extract_plugin_tag(node):
            return True
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name in {"name", "execute", "step"}:
                return True
        return False

    fallback_candidate: Optional[ast.ClassDef] = None
    fallback_base_names: List[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            base_names = [name for name in (_base_name(base) for base in node.bases) if name]
            if "RPP_Plugin" in base_names:
                plugin_class = node
                plugin_base_names = base_names
                break
            if fallback_candidate is None and _class_has_plugin_markers(node):
                fallback_candidate = node
                fallback_base_names = base_names

    if plugin_class is None:
        has_single_class = len([node for node in tree.body if isinstance(node, ast.ClassDef)]) == 1
        if has_single_class:
            plugin_class = next(node for node in tree.body if isinstance(node, ast.ClassDef))
            plugin_base_names = [_base_name(base) for base in plugin_class.bases if _base_name(base)]
        else:
            if fallback_candidate is not None:
                plugin_class = fallback_candidate
                plugin_base_names = fallback_base_names

    if plugin_class is None:
        raise ValueError(f"Could not locate a plugin class in '{source_file}'.")

    descriptions = extract_plugin_descriptions(plugin_class)
    methods: List[MethodSpec] = []
    plugin_name: Optional[str] = None

    is_casadi = False
    for item in plugin_class.body:
        if not isinstance(item, ast.FunctionDef):
            continue
        if item.name.startswith("_") or item.name.endswith("_"):
            continue

        if item.name == "casadi_plugin__":
            if isinstance(item.value, ast.Constant) and item.value.value is True:
                is_casadi = True
            continue

        params: List[MethodParam] = []
        for arg in item.args.args:
            if arg.arg != "self":
                params.append(MethodParam(name=arg.arg, type=annotation_to_text(arg.annotation)))

        methods.append(MethodSpec(name=item.name, return_type=annotation_to_text(item.returns), params=params))

        if item.name == "name":
            for stmt in item.body:
                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                    plugin_name = stmt.value.value
                    break

    resolved_name = plugin_name or plugin_class.name

    has_create = any(isinstance(node, ast.FunctionDef) and node.name == "create_plugin" for node in tree.body)
    has_destroy = any(isinstance(node, ast.FunctionDef) and node.name == "destroy_plugin" for node in tree.body)

    return build_description(
        plugin_name=resolved_name,
        language="python",
        source_file=source_file,
        class_name=plugin_class.name,
        base_class_name=plugin_base_names[0] if plugin_base_names else None,
        descriptions=descriptions,
        create_symbol="create_plugin" if has_create else "create_plugin",
        destroy_symbol="destroy_plugin" if has_destroy else "destroy_plugin",
        methods=methods,
        is_casadi=is_casadi,
    )
