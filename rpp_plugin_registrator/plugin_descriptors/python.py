from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional

from .core import (
    MethodInfo,
    FieldInfo,
    ParsePluginData,
    ParsePluginResult,
    annotation_to_type_info,
    build_base_plugin_description,
    read_text,
)


def parse_python_plugin(source_file: Path, plugin_id: Optional[str]) -> ParsePluginResult:
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

    fallback_candidate: Optional[ast.ClassDef] = None
    fallback_base_names: List[str] = []

    imported_plugin_types = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("rpp_plugin_types"):
                for alias in node.names:
                    imported_plugin_types.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("rpp_plugin_types"):
                    imported_plugin_types.add(alias.name.split(".")[-1])

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            base_names = [name for name in (_base_name(base) for base in node.bases) if name]
            if "Plugin" in base_names:
                plugin_class = node
                plugin_base_names = base_names
                break
            if any(base_name in imported_plugin_types for base_name in base_names):
                plugin_class = node
                plugin_base_names = base_names
                break


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

    methods: List[Dict[str, Any]] = []
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

        params: List[Dict[str, Any]] = []
        for arg in item.args.args:
            if arg.arg != "self":
                typ = annotation_to_type_info(arg.annotation)
                params.append(FieldInfo(name=arg.arg, type=typ))

        return_type = annotation_to_type_info(item.returns) if item.returns else None

        methods.append(MethodInfo(
            name=item.name,
            params=params,
            results=[FieldInfo(name="return", type=return_type)] if return_type else []
        ))


    desc = build_base_plugin_description(
        name=plugin_class.name,
        language="python",
        source_file=source_file,
        class_name=plugin_class.name,
        base_class_name=plugin_base_names[0] if plugin_base_names else None,
        base_classes=plugin_base_names,
        description="No description provided.",
        is_casadi=is_casadi,
    )

    desc = {
        **desc,
        "Methods": [method.as_dict() for method in methods],
        "Fields": [],
    }

    return ParsePluginResult(
        is_valid=True,
        message="Successfully parsed Python plugin.",
        data=ParsePluginData(
            source_file=str(source_file),
            source_language="python",
            plugins=[desc],
            parse_errors=[],
        ),
    )