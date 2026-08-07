from __future__ import annotations

from typing import Any, Dict
import shutil

from rpp_plugin_registrator.plugin_descriptors.core import (
    PluginInfo, PluginTypeInfo,
    PluginValidationResult, PluginValidationData
)
from ..plugin_registrator.cpp import (
    compile_cpp_plugin,
    get_tmp_dir_for_compilation
)

def early_return_invalid(message: str) -> PluginValidationResult:
    return PluginValidationResult(
        is_valid=False,
        message=message,
        validation_data=None
    )

def extract_plugin_type(desc, plugin_types) -> str | None:
    for base_class_name in desc.info.get("BaseClasses"):
        if base_class_name is None:
            continue
        base_class_name_candidate = base_class_name
        if base_class_name_candidate in plugin_types:
            return base_class_name_candidate

        splits = base_class_name.split("::")
        if len(splits) >= 2:
            base_class_name_candidate = f"{splits[-2]}::{splits[-1]}"
            if base_class_name_candidate in plugin_types:
                return base_class_name_candidate

        # try with namespaces
        for ns in desc.info.get("UsingNamespaces", []):
            if ns:
                base_class_name_candidate = f"{ns}::{base_class_name}"
                if base_class_name_candidate in plugin_types:
                    return base_class_name_candidate

    return None

def make_fully_qualified_class_name_with_lib(fully_qualified_class_name: str, library_name: str) -> str:
    return f"{library_name}::{fully_qualified_class_name}"

def validate_cpp_plugin(desc: PluginInfo, plugin_types: Dict[str, PluginTypeInfo],
        desired_library: str | None = None, persist_compiled_files: bool = False, **kwargs) -> Dict[str, Any]:
    """Validate a C++ plugin class and return validation data."""
    source_file = desc.info.get("SourceFile")
    class_name = desc.info.get("ClassName")

    plugin_type = extract_plugin_type(desc, plugin_types)
    if plugin_type is None:
        return early_return_invalid(
            f"Plugin class '{class_name}' does not inherit from any known plugin type."
        )

    plugin_type_info = plugin_types[plugin_type]
    suppress_warnings = True
    tmp_out_dir = get_tmp_dir_for_compilation(source_file, class_name)
    if not tmp_out_dir.exists():
        tmp_out_dir.mkdir(parents=True, exist_ok=True)
    # try and compile the plugin source file to check for errors
    cmd = []
    try:
        compile_error, cmd, _ = compile_cpp_plugin(
            source_file=source_file,
            library_name=desired_library,
            plugin_type_name=plugin_type,
            plugin_type_library=plugin_type_info.get("Library"),
            out_dir=tmp_out_dir,
            class_name=class_name,
            suppress_warnings=suppress_warnings
        )
        if compile_error:
            if tmp_out_dir.exists():
                shutil.rmtree(str(tmp_out_dir))
            return early_return_invalid(compile_error)
    except Exception as e:
        full_command = " ".join(cmd)
        if tmp_out_dir.exists():
            shutil.rmtree(str(tmp_out_dir))
        return early_return_invalid(
            f"Error during compilation of plugin class '{class_name}' "
            + f"in file '{source_file}'.\nCommand: {full_command}\nError: {str(e)}"
        )

    if not persist_compiled_files and tmp_out_dir.exists():
        shutil.rmtree(str(tmp_out_dir))

    return PluginValidationResult(
        is_valid=True,
        message="C++ plugin validation not implemented yet.",
        validation_data=PluginValidationData(
            plugin_type=plugin_type,
            plugin_type_library=plugin_type_info.get("Library"),
            plugin_type_class_name=plugin_type_info.get("ClassName"),
            plugin_type_source_file=plugin_type_info.get("SourceFile"),
            fully_qualified_plugin_class_name=plugin_type_info.get("FullyQualifiedClassName"),
            fully_qualified_class_name=plugin_type,
            class_name=class_name,
        )
    )

