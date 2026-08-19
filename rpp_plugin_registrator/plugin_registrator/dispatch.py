from __future__ import annotations

from typing import Any, Dict

from rpp_plugin_registrator.plugin_descriptors.core import PluginInfo, PluginRegisterData, PluginTypeInfo, PluginRegistrationResult, PluginTypeRegistrationResult


from .python import register_python_plugin, unregister_python_plugin, \
    generate_python_plugin_interface, remove_python_plugin_interface
from .capnp import register_capnp_plugin_type, unregister_capnp_plugin_type
from .cpp import register_cpp_plugin, unregister_cpp_plugin, \
    generate_cpp_plugin_interface, remove_cpp_plugin_interface, \
    get_plugin_type_shared_library_path

def register_plugin(plugin_info: PluginInfo) -> PluginRegistrationResult:
    source_language = plugin_info.info["SourceLanguage"]

    if source_language == "python":
        result = register_python_plugin(plugin_info)
    elif source_language == "cpp":
        result = register_cpp_plugin(plugin_info)
    else:
        raise ValueError(f"No registrator available for source language '{source_language}'.")
    if result.register_data.plugin_type_shared_library_path is None:
        shared_lib_path = get_plugin_type_shared_library_path(
            plugin_info.validation_data.plugin_type_library,
            plugin_info.validation_data.plugin_type_class_name
        )
        result.register_data = PluginRegisterData(
            plugin_shared_library_path=result.register_data.plugin_shared_library_path,
            plugin_type_shared_library_path=str(shared_lib_path),
            plugin_metadata=result.register_data.plugin_metadata
        )
    return result

def unregister_plugin(plugin_info: Dict[str, Any]) -> bool:
    source_language = plugin_info["SourceLanguage"]

    if source_language == "python":
        return unregister_python_plugin(plugin_info)
    elif source_language == "cpp":
        return unregister_cpp_plugin(plugin_info)
    else:
        raise ValueError(f"No unregistrator available for source language '{source_language}'.")

def register_plugin_type(plugin_type_info: PluginTypeInfo,
        override: bool = False) -> PluginTypeRegistrationResult:
    source_language = plugin_type_info.info["SourceLanguage"].lower()

    if source_language == "capnp":
        register_data = register_capnp_plugin_type(plugin_type_info, override=override)
    else:
        raise ValueError(f"No registrator available for source language '{source_language}'.")

    return register_data

def unregister_plugin_type(plugin_type_info: Dict[str, str]) -> None:
    source_language = plugin_type_info.get("SourceLanguage", "capnp").lower()

    if source_language == "capnp":
        unregister_capnp_plugin_type(plugin_type_info)
    else:
        raise ValueError(f"No unregistrator available for source language '{source_language}'.")

def generate_plugin_type_interface(plugin_type_info: PluginTypeInfo, languages: list = None) -> None:
    if languages is None:
        languages = ["all"]

    is_supporting_file = plugin_type_info.info.get("IsSupportingFile", False)
    if not is_supporting_file:
        if "python" in languages or "all" in languages:
            generate_python_plugin_interface(plugin_type_info)
        if "cpp" in languages or "all" in languages:
            generate_cpp_plugin_interface(plugin_type_info)

def remove_plugin_type_interface(plugin_type_info: Dict[str, str], languages: list = None) -> None:
    if languages is None:
        languages = ["all"]

    if "python" in languages or "all" in languages:
        remove_python_plugin_interface(plugin_type_info)
    if "cpp" in languages or "all" in languages:
        remove_cpp_plugin_interface(plugin_type_info)