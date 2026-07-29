from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from cairo import HAS_ATSUI_FONT
from rpp_common.py.descriptors import ParameterDescription
from rpp_plugin_registrator.plugin_descriptors.core import (
    PluginInfo, PluginRegisterData, PluginRegistrationResult, PluginTypeInfo
)
from rpp_plugin_registrator.registry_config import get_app_interfaces_path
from ..utils import import_module_from_path


def parse_plugin_parameters(params: list) -> Dict[str, Any]:

    def parse_parameter_value(name: str, value: Any) -> Any:
        ret_value = {"name": name, "default_value": value, "type": None}
        if isinstance(value, bool):
            ret_value["type"] = "bool"
            return ret_value
        if isinstance(value, int):
            ret_value["type"] = "int"
            return ret_value
        if isinstance(value, float):
            ret_value["type"] = "float"
            return ret_value
        if isinstance(value, str):
            ret_value["type"] = "string"
            return ret_value
        if isinstance(value, list):
            ret_value["type"] = "array"
            ret_value["default_value"] = [parse_parameter_value(f"{name}[{i}]", v) for i, v in enumerate(value)]
            ret_value["element_type"] = ret_value["default_value"][0]["type"] if ret_value["default_value"] else None
            return ret_value

        if hasattr(value, "__dict__"):
            dict_value = value.__dict__
        else:
            dict_value = value

        if isinstance(dict_value, dict):
            ret_value["type"] = "object"
            ret_value["fields"] = {}
            del ret_value["default_value"]
            for k, v in dict_value.items():
                if not isinstance(k, str):
                    raise ValueError(f"Dictionary keys must be strings. Got: {k} ({type(k)})")
                ret_value["fields"][k] = parse_parameter_value(k, v)
        return ret_value

    ret_params = {}
    for param in params:
        if not isinstance(param, ParameterDescription):
            raise ValueError("Each parameter must be a ParameterDescription"
                + f" instance. Got: {param} ({type(param)})")
        ret_params[param.name] = parse_parameter_value(param.name, param.default_value)
    return ret_params



def parse_plugin_components(comps: Dict[str, str]):
    """Parse plugin components from the provided dictionary.

    Args:
        comps (Dict[str, str]): A dictionary containing component names and their corresponding types.

    Returns:
        Dict[str, str]: A dictionary with component names as keys and their types as values.
    """
    parsed_components = {}
    for comp_name, comp_type in comps.items():
        if not isinstance(comp_name, str):
            raise ValueError("Component names be strings.")
        if not isinstance(comp_type, str) \
            and not (isinstance(comp_type, list) and all(isinstance(t, str) for t in comp_type)):
            raise ValueError("Component types must be strings or lists of strings."
                + f" Got: {comp_type} ({type(comp_type)})")
        parsed_components[comp_name] = comp_type
    return parsed_components




def add_to_init_file(directory: str, class_name: str) -> None:
    if not directory:
        raise ValueError("Directory path must be provided.")

    Path(directory).mkdir(parents=True, exist_ok=True)
    init_file_path = directory / "__init__.py"
    if not init_file_path.exists():
        init_file_path.write_text("# Auto-generated __init__.py\n", encoding="utf-8")

    line = f"from .{class_name} import {class_name}\n"
    with init_file_path.open("r+", encoding="utf-8") as f:
        lines = f.readlines()
        if line not in lines:
            f.write(line)

def remove_from_init_file(directory: str, class_name: str) -> None:
    if not directory:
        raise ValueError("Directory path must be provided.")
    init_file_path = directory / "__init__.py"
    if not init_file_path.exists():
        return  # Nothing to remove
    line_to_remove = f"from .{class_name} import {class_name}\n"
    with init_file_path.open("r+", encoding="utf-8") as f:
        lines = f.readlines()
        if line_to_remove in lines:
            lines.remove(line_to_remove)
            f.seek(0)
            f.truncate()
            f.writelines(lines)

def generate_python_plugin_interface(plugin_type_info: PluginTypeInfo) -> bool:
    """Register a Python plugin by adding its information to the registry."""
    info = plugin_type_info.info
    lib_name = info["Library"]
    class_name = info["ClassName"]
    interfaces_path = get_app_interfaces_path() / "python" / "rpp_plugin_types" / lib_name
    add_to_init_file(interfaces_path, class_name)
    return True

def remove_python_plugin_interface(plugin_type_info: PluginTypeInfo) -> bool:
    """Unregister a Python plugin by removing its information from the registry."""

    info = plugin_type_info.info
    lib_name = info["Library"]
    class_name = info["ClassName"]
    interfaces_path = get_app_interfaces_path() / "python" / "rpp_plugin_types" / lib_name
    remove_from_init_file(interfaces_path, class_name)
    return True


def register_python_plugin(info: PluginInfo) -> PluginRegistrationResult:
    """Register a Python plugin by adding its information to the registry."""

    source_file = Path(info.info["SourceFile"])
    class_name = info.info["ClassName"]
    if not source_file.exists():
        return PluginRegistrationResult(
            success=False,
            message=f"Source file '{source_file}' does not exist.",
        )

    module = import_module_from_path(str(source_file))

    module_class = getattr(module, class_name, None)
    if module_class is None:
        return PluginRegistrationResult(
            success=False,
            message=f"Class '{class_name}' not found in module '{module.__name__}'.",
        )

    metadata = {
        "Parameters" : parse_plugin_parameters(getattr(module_class, "PARAMETERS", [])),
        "Components" : parse_plugin_components(getattr(module_class, "COMPONENTS", {})),
    }

    return PluginRegistrationResult(
        success=True,
        message=f"Python plugin '{info.info['Name']}' registered successfully.",
        register_data=PluginRegisterData(
            plugin_shared_library_path=None,
            plugin_type_shared_library_path=None,
            plugin_metadata=metadata,
        )
    )

def unregister_python_plugin(plugin_info: PluginInfo) -> bool:
    return True
