from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from rpp_py.parameter_description import ParameterDescription

from ..utils import to_snake_case


@dataclass(frozen=True)
class TypeInfo:
    name: str
    kind: str
    element_type: Optional[TypeInfo] = None
    capnp_type_display_name: Optional[str] = None


    def as_dict(self) -> Dict[str, Any]:
        result = {
            "Name": self.name,
            "Kind": self.kind,
        }
        if self.element_type is not None:
            result["ElementType"] = self.element_type.as_dict()
        if self.capnp_type_display_name is not None:
            result["CapnpTypeDisplayName"] = self.capnp_type_display_name
        return result

@dataclass(frozen=True)
class MethodInfo:
    name: str
    params: List[FieldInfo]
    results: List[FieldInfo]

    def as_dict(self) -> Dict[str, Any]:
        params = [param.as_dict() for param in self.params]
        results = [result.as_dict() for result in self.results]
        return {
            "Name": self.name,
            "Params": params,
            "Results": results
        }

@dataclass(frozen=True)
class FieldInfo:
    name: str
    type: TypeInfo

    def as_dict(self) -> Dict[str, Any]:
        return {
            "Name": self.name,
            "Type": self.type.as_dict()
        }

@dataclass(frozen=True)
class InterfaceInfo:
    name: str
    methods: List[MethodInfo]

@dataclass(frozen=True)
class StructInfo:
    name: str
    fields: List[FieldInfo]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "Name": self.name,
            "Fields": [field.as_dict() for field in self.fields]
        }

@dataclass(frozen=True)
class PluginTypeRegisterData:
    registry_plugin_type_file: str
    registry_plugin_type_file_id: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "RegistryPluginTypeFile": self.registry_plugin_type_file,
            "RegistryPluginTypeFileId": self.registry_plugin_type_file_id
        }


@dataclass(frozen=True)
class PluginRegisterData:
    plugin_shared_library_path: str
    plugin_type_shared_library_path: str
    plugin_metadata: dict

    def as_dict(self) -> Dict[str, Any]:
        return {
            "PluginSharedLibraryPath": self.plugin_shared_library_path,
            "PluginTypeSharedLibraryPath": self.plugin_type_shared_library_path,
            "PluginMetadata": self.plugin_metadata
        }

@dataclass(frozen=True)
class PluginTypeValidationData:

    def as_dict(self) -> Dict[str, Any]:
        return {}


@dataclass(frozen=True)
class PluginValidationData:
    plugin_type: str
    plugin_type_class_name: str
    plugin_type_source_file: str
    plugin_type_library: str
    fully_qualified_plugin_class_name: str
    fully_qualified_class_name: str
    class_name: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "PluginType": self.plugin_type,
            "PluginTypeClassName": self.plugin_type_class_name,
            "FullyQualifiedPluginClassName": self.fully_qualified_plugin_class_name,
            "FullyQualifiedClassName": self.fully_qualified_class_name,
            "ClassName": self.class_name,
            "PluginTypeLibrary": self.plugin_type_library,
            "PluginTypeSourceFile": self.plugin_type_source_file
        }

@dataclass(frozen=True)
class PluginTypeMetadata:
    type: str
    plugin_name: str
    interface_name: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "Type": self.type,
            "PluginName": self.plugin_name,
            "InterfaceName": self.interface_name
        }

@dataclass(frozen=True)
class ParsePluginData:
    source_file: str
    source_language: str
    plugins: List[Dict[str, Any]] = None
    parse_errors: Optional[List[str]] = None

@dataclass(frozen=True)
class ParsePluginResult:
    is_valid: bool
    message: Optional[str] = None
    data: Optional[ParsePluginData] = None



@dataclass(frozen=True)
class ParsePluginTypeData:
    source_file: str
    source_language: str
    script_handle: Any = None
    plugins: List[PluginTypeMetadata] = None
    interfaces: Dict[str, InterfaceInfo] = None
    structs: Dict[str, StructInfo] = None
    parse_errors: Optional[List[str]] = None
    dependencies: List[str] = None

@dataclass(frozen=True)
class ParsePluginTypeResult:
    is_valid: bool
    message: Optional[str] = None
    data: Optional[ParsePluginTypeData] = None

@dataclass
class PluginTypeValidationResult:
    is_valid: bool
    message: Optional[str] = None
    validation_data: Optional[PluginTypeValidationData] = None

@dataclass
class PluginTypeRegistrationResult:
    success: bool
    message: Optional[str] = None
    register_data: Optional[PluginTypeRegisterData] = None

@dataclass
class PluginValidationResult:
    is_valid: bool
    message: Optional[str] = None
    validation_data: Optional[PluginValidationData] = None

@dataclass
class PluginRegistrationResult:
    success: bool
    message: Optional[str] = None
    register_data: Optional[PluginRegisterData] = None

@dataclass
class PluginTypeInfo:
    info: Dict[str, Any]
    parse_data: ParsePluginTypeData | None = None
    validation_data: PluginTypeValidationData | None = None
    register_data: PluginTypeRegisterData | None = None

    def get_interface(self) -> Optional[InterfaceInfo]:
        if self.parse_data and self.parse_data.interfaces:
            # interface inside capnp does not have a library name
            interface_name = self.info.get("ClassName")
            if interface_name:
                return self.parse_data.interfaces.get(interface_name)
        return None

@dataclass
class PluginInfo:
    info: Dict[str, Any]
    parse_data: ParsePluginData | None = None
    validation_data: PluginValidationData | None = None
    register_data: PluginRegisterData | None = None


def plugin_id_from_name(plugin_name: str) -> str:
    """Convert PluginType to snake_case plugin_id for folder naming."""
    return to_snake_case(plugin_name)


def infer_language_from_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".cpp", ".cc", ".cxx", ".hpp", ".h"}:
        return "cpp"
    if suffix == ".py":
        return "python"
    if suffix == ".capnp":
        return "capnp"
    raise ValueError(f"Unsupported source extension '{suffix}' for file '{path}'.")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def annotation_to_type_info(annotation: Optional[ast.expr]) -> TypeInfo:
    # kind can be "unknown", "primitive", "list", or "struct"
    if annotation is None:
        return TypeInfo(name="None", kind="unknown")
    if isinstance(annotation, ast.Name):
        return TypeInfo(name=annotation.id, kind="primitive")
    if isinstance(annotation, ast.Subscript):
        if isinstance(annotation.value, ast.Name) and annotation.value.id == "List":
            element_type = annotation_to_type_info(annotation.slice)
            return TypeInfo(name="List", kind="list", element_type=element_type)
    return TypeInfo(name=ast.unparse(annotation), kind="unknown")

def eval_python_expression(node: ast.AST) -> Any:
    try:
        expression = ast.Expression(body=node.value)
        ast.fix_missing_locations(expression)
        source_code = compile(expression, filename="<ast>", mode="eval")
        context = {"Parameter": ParameterDescription}
        evaluated = eval(source_code, {"__builtins__": {}}, context)
    except (Exception) as e:
        print(f"Error occurred while evaluating literal: {e}")
        return []
    return evaluated


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
                value = eval_python_expression(item)
                descriptions[target.id] = value if isinstance(value, list) else []
    return descriptions


def build_base_plugin_description(
    name: str,
    language: str,
    source_file: Path,
    class_name: Optional[str],
    base_class_name: Optional[str],
    base_classes: Optional[List[str]],
    description: str,
    is_casadi: bool = False,
) -> Dict[str, Any]:

    return {
        "SchemaVersion": 1,
        "Name": name,
        "SourceLanguage": language,
        "SourceFile": str(source_file),
        "ClassName": class_name,
        "BaseClassName": base_class_name,
        "BaseClasses": base_classes,
        "Description": description,
        "IsCasadi": is_casadi,
    }

def apply_library_context_to_plugin(plugin_info: Dict[str, Any], library: str) -> Dict[str, Any]:
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
    plugin_class_name = plugin_info["ClassName"]

    plugin_info["Library"] = library
    plugin_info["PluginName"] = f"{library}::{plugin_class_name}"
    plugin_info["Id"] = plugin_id_from_name(plugin_info["PluginName"])

    return plugin_info


def apply_library_context_to_plugin_type(
        plugin_type_info: Dict[str, Any], library: str) -> Dict[str, Any]:
    """Apply library context to a plugin type info dictionary."""

    class_name = plugin_type_info.get("ClassName")
    plugin_type_info["Library"] = library
    plugin_type_info["PluginTypeName"] = f"{library}::{class_name}"
    plugin_type_info["Id"] = plugin_id_from_name(plugin_type_info["PluginTypeName"])
    plugin_type_info["FullyQualifiedClassName"] = f"<class 'rpp_plugin_types.{library}.{class_name}.{class_name}'>" if class_name else None
    return plugin_type_info
