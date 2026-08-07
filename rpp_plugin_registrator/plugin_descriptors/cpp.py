from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from tree_sitter import Language, Parser
import tree_sitter_cpp as ts_cpp


from .core import (
    ParsePluginData,
    ParsePluginResult,
    build_base_plugin_description,
)


def early_unsuccessful_return(source_file: Path, error_message: str) -> ParsePluginResult:
    return ParsePluginResult(
        is_valid=False,
        message=error_message,
    )

def strip_type_modifiers(type_text: str) -> str:
    cleaned = re.sub(r"\b(const|volatile|typename|class|struct)\b", "", type_text)
    cleaned = cleaned.replace("&", "").replace("*", "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

def split_top_level_commas(text: str) -> List[str]:
    items: List[str] = []
    current: List[str] = []
    depth = 0
    for char in text:
        if char == "," and depth == 0:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
            continue
        if char in "(<[{":
            depth += 1
        elif char in ")>]}" and depth > 0:
            depth -= 1
        current.append(char)
    tail = "".join(current).strip()
    if tail:
        items.append(tail)
    return items

def iter_nodes(node):
    yield node
    for child in node.children:
        yield from iter_nodes(child)


def parse_cpp_plugin(source_file: Path, plugin_id: Optional[str]) -> ParsePluginResult:
    """Parse a C++ plugin file and return a ParsePluginResult."""

    _ = plugin_id

    source_text = source_file.read_text(encoding="utf-8")

    # Remove RPP_COMPONENTS and RPP_PARAMETERS macros from the source code to avoid parsing issues
    clean_code = re.sub(r'RPP_COMPONENTS\s*\([^)]+\);?', '// RPP_COMPONENTS REMOVED', source_text)
    clean_code = re.sub(r'RPP_PARAMETERS\s*\([^;]+\);?', '// RPP_PARAMETERS REMOVED', clean_code)


    source_bytes = clean_code.encode("utf-8")

    parser = Parser()
    parser.language = Language(ts_cpp.language())
    tree = parser.parse(source_bytes)
    root = tree.root_node

    type_aliases: Dict[str, str] = {}

    namespace_declarations = re.findall(r"^\s*namespace\s+([A-Za-z_][A-Za-z0-9_:]*)\s*\{", source_text, re.MULTILINE)
    using_namespaces = re.findall(r"^\s*using\s+namespace\s+([A-Za-z_][A-Za-z0-9_:]*)\s*;", source_text, re.MULTILINE)
    for alias_name, aliased_type in re.findall(r"^\s*using\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^;]+);", source_text, re.MULTILINE):
        type_aliases[alias_name] = strip_type_modifiers(aliased_type)


    def node_text(node) -> str:
        return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")

    def resolve_type_name(type_text: str) -> str:
        cleaned = strip_type_modifiers(type_text)
        if cleaned in type_aliases:
            return type_aliases[cleaned]
        return cleaned

    def extract_class_name(class_node) -> Optional[str]:
        text = node_text(class_node)
        match = re.search(r"\b(class|struct)\s+([A-Za-z_][A-Za-z0-9_:]*)", text)
        if match:
            return match.group(2).split("::")[-1]
        return None

    def extract_base_class_names(class_node) -> List[str]:
        text = node_text(class_node)
        header_match = re.search(r"\b(class|struct)\s+[A-Za-z_][A-Za-z0-9_:]*\s*:(.*?)\{", text, re.DOTALL)
        if not header_match:
            return []
        bases: List[str] = []
        for part in header_match.group(2).split(","):
            cleaned = re.sub(r"\b(public|protected|private|virtual)\b", "", part).strip()
            if cleaned:
                bases.append(resolve_type_name(cleaned.split()[-1]))
        return bases


    def parse_member_signature(signature: str, access: str) -> Dict[str, Any] | None:
        signature = signature.strip()
        if not signature or signature.startswith("using ") or signature.startswith("typedef "):
            return None
        if "{" in signature:
            signature = signature[: signature.rfind("{")].strip()
        if signature.endswith("}"):
            signature = signature[: signature.rfind("}")].strip()
        if "(" in signature and ")" in signature:
            prefix = signature[: signature.find("(")].strip()
            name = prefix.split()[-1]
            if "::" in name:
                name = name.split("::")[-1]
            return_type = prefix[: prefix.rfind(name)].strip() if name in prefix else ""
            return_type = resolve_type_name(return_type) if return_type else ""
            params = signature[signature.find("(") + 1 : signature.rfind(")")]
            return {
                "kind": "method",
                "Name": name,
                "AccessModifier": access,
                "ReturnType": return_type,
                "Signature": signature,
                "Parameters": split_top_level_commas(params),
            }
        if signature.endswith(";"):
            declaration = signature[:-1].strip()
            if not declaration:
                return None
            if " " in declaration:
                field_name = declaration.split()[-1]
                field_type = resolve_type_name(declaration[: declaration.rfind(field_name)].strip())
            else:
                field_name = declaration
                field_type = ""
            return {
                "kind": "field",
                "Name": field_name,
                "Type": field_type,
                "AccessModifier": access,
                "Declaration": signature,
            }
        return None

    def extract_members(class_node) -> Dict[str, List[Dict[str, Any]]]:
        body_node = None
        for child in class_node.children:
            if child.type == "field_declaration_list":
                body_node = child
                break
        if body_node is None:
            return {"methods": [], "fields": []}

        is_struct = node_text(class_node).lstrip().startswith("struct ")
        access = "public" if is_struct else "private"
        methods: List[Dict[str, Any]] = []
        fields: List[Dict[str, Any]] = []

        for child in body_node.children:
            if child.type == "access_specifier":
                access = node_text(child).replace(":", "").strip()
                continue


            if child.type not in {"function_definition", "field_declaration"}:
                continue

            parsed = parse_member_signature(node_text(child), access)
            if not parsed:
                continue
            if parsed["kind"] == "method":
                methods.append({k: v for k, v in parsed.items() if k != "kind"})
            else:
                fields.append({k: v for k, v in parsed.items() if k != "kind"})
        return {"methods": methods, "fields": fields}


    class_nodes = [node for node in iter_nodes(root) if node.type == "class_specifier"]
    if not class_nodes:
        return early_unsuccessful_return(
            source_file, f"Could not locate a C++ class implementation in '{source_file}'."
        )

    class_infos: List[Dict[str, Any]] = []
    for class_node in class_nodes:
        class_name = extract_class_name(class_node)
        if class_name is None:
            continue
        base_class_names = extract_base_class_names(class_node)
        public_members = extract_members(class_node)
        class_infos.append(
            {
                "Name": class_name,
                "BaseClassNames": base_class_names,
                "Methods": public_members["methods"],
                "Fields": public_members["fields"],
            }
        )

    if not class_infos:
        return early_unsuccessful_return(
            source_file, f"Could not extract any named C++ classes from '{source_file}'."
        )

    class_infos.sort(key=lambda item: (0 if item["BaseClassNames"] else 1, -len(item["Methods"]), item["Name"]))
    selected_class = class_infos[0]


    plugin_info = build_base_plugin_description(
        name=selected_class["Name"],
        language="cpp",
        source_file=source_file,
        class_name=selected_class["Name"],
        base_class_name=selected_class["BaseClassNames"][0] if selected_class["BaseClassNames"] else None,
        base_classes=selected_class["BaseClassNames"],
        description="No description provided.",
        is_casadi=False,
    )

    plugin_info: Dict[str, Any] = {
        **plugin_info,
        "Methods": selected_class["Methods"],
        "Fields": selected_class["Fields"],
        "ClassImplementations": class_infos,
        "Namespaces": namespace_declarations,
        "UsingNamespaces": using_namespaces,
        "TypeAliases": type_aliases,
        "Description": "No description provided.",
        "IsCasadi": False,
    }

    return ParsePluginResult(
        is_valid=True,
        message="Successfully parsed C++ plugin.",
        data=ParsePluginData(
            source_file=str(source_file),
            source_language="cpp",
            plugins=[plugin_info],
            parse_errors=[],
        ),
    )