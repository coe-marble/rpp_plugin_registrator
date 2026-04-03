from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


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
    plugin_id: str,
    plugin_name: str,
    language: str,
    source_file: Path,
    class_name: Optional[str],
    descriptions: Dict[str, Any],
    create_symbol: str,
    destroy_symbol: str,
    methods: List[MethodSpec],
) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "plugin": {
            "id": plugin_id,
            "name": plugin_name,
            "source_language": language,
            "source_file": str(source_file),
            "class_name": class_name,
            "param_description": descriptions.get("param_description", []),
            "log_description": descriptions.get("log_description", []),
            "input_description": descriptions.get("input_description", []),
            "output_description": descriptions.get("output_description", []),
            "rpp_registration": {
                "factory": {
                    "create_symbol": create_symbol,
                    "destroy_symbol": destroy_symbol,
                }
            },
            "interface": {
                "methods": [
                    {
                        "name": method.name,
                        "return_type": method.return_type,
                        "params": [{"name": param.name, "type": param.type} for param in method.params],
                    }
                    for method in methods
                ]
            },
        },
    }


def parse_cpp_plugin(source_file: Path, plugin_id: Optional[str]) -> Dict[str, Any]:
    text = read_text(source_file)

    class_match = re.search(
        r"class\\s+([A-Za-z_][A-Za-z0-9_]*)\\s*(?:final\\s*)?:\\s*public\\s+rpp::Plugin",
        text,
        re.MULTILINE,
    )
    class_name = class_match.group(1) if class_match else None

    name_match = re.search(
        r"name\\s*\\(\\s*\\)\\s*const\\s*override\\s*\\{[\\s\\S]*?return\\s+\"([^\"]+)\"\\s*;",
        text,
        re.MULTILINE,
    )
    plugin_name = name_match.group(1) if name_match else (plugin_id or (class_name or source_file.stem))

    has_execute = bool(
        re.search(
            r"execute\\s*\\(\\s*const\\s+std::string\\s*&\\s*[A-Za-z_][A-Za-z0-9_]*\\s*\\)\\s*override",
            text,
            re.MULTILINE,
        )
    )

    methods: List[MethodSpec] = [MethodSpec(name="name", return_type="string", params=[])]
    if has_execute:
        methods.append(
            MethodSpec(
                name="execute",
                return_type="string",
                params=[MethodParam(name="input", type="string")],
            )
        )

    return build_description(
        plugin_id=plugin_id or normalize_plugin_id(plugin_name),
        plugin_name=plugin_name,
        language="cpp",
        source_file=source_file,
        class_name=class_name,
        descriptions={
            "param_description": [],
            "log_description": [],
            "input_description": [],
            "output_description": [],
        },
        create_symbol="create_plugin",
        destroy_symbol="destroy_plugin",
        methods=methods,
    )


def parse_python_plugin(source_file: Path, plugin_id: Optional[str]) -> Dict[str, Any]:
    text = read_text(source_file)
    tree = ast.parse(text, filename=str(source_file))

    plugin_class: Optional[ast.ClassDef] = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            base_names = {base.id for base in node.bases if isinstance(base, ast.Name)}
            if "RPP_Plugin" in base_names:
                plugin_class = node
                break

    if plugin_class is None:
        raise ValueError(
            f"Could not locate a plugin class deriving from RPP_Plugin in '{source_file}'."
        )

    descriptions = extract_plugin_descriptions(plugin_class)
    plugin_tag = extract_plugin_tag(plugin_class)
    methods: List[MethodSpec] = []
    plugin_name: Optional[str] = None

    for item in plugin_class.body:
        if not isinstance(item, ast.FunctionDef):
            continue
        if item.name.startswith("_") or item.name.endswith("_"):
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
    resolved_plugin_id = plugin_id or plugin_tag or normalize_plugin_id(resolved_name)

    has_create = any(isinstance(node, ast.FunctionDef) and node.name == "create_plugin" for node in tree.body)
    has_destroy = any(isinstance(node, ast.FunctionDef) and node.name == "destroy_plugin" for node in tree.body)

    return build_description(
        plugin_id=resolved_plugin_id,
        plugin_name=resolved_name,
        language="python",
        source_file=source_file,
        class_name=plugin_class.name,
        descriptions=descriptions,
        create_symbol="create_plugin" if has_create else "create_plugin",
        destroy_symbol="destroy_plugin" if has_destroy else "destroy_plugin",
        methods=methods,
    )
