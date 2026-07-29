from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Union

from rpp_plugin_registrator.plugin_descriptors.core import (
    PluginInfo, PluginTypeInfo,
    PluginValidationResult, PluginTypeValidationResult,
    PluginValidationData, PluginTypeValidationData
)

from .python import validate_python_plugin
from .cpp import validate_cpp_plugin
from rpp_plugin_registrator.supported_plugins_and_types import (
    get_supported_plugin_extensions,
    get_supported_plugin_type_extensions
)

def unsucessful_plugin_early_return(message: str) -> PluginValidationResult:
    return PluginValidationResult(
        is_valid=False,
        message=message,
        validation_data=None
    )

def unsucessful_plugin_type_early_return(message: str) -> PluginTypeValidationResult:
    return PluginTypeValidationResult(
        is_valid=False,
        message=message,
        validation_data=None
    )

def validate_plugin(desc: PluginInfo, plugin_types: Dict[str, Any],
        desired_library: str | None = None,persist_compiled_files: bool = False) -> PluginValidationResult:
    """Validate plugin class by inferring language from file extension."""
    source_file = desc.info.get("SourceFile")
    if isinstance(source_file, str):
        source_file = Path(source_file)
    suffix = source_file.suffix.lower()

    extensions = get_supported_plugin_extensions()
    if suffix not in extensions:
        return unsucessful_plugin_early_return(f"Unsupported plugin language for runtime validation: '{suffix}'")

    try:
        if suffix == ".py":
            return validate_python_plugin(desc, plugin_types,
                desired_library=desired_library, persist_compiled_files=persist_compiled_files)
        elif suffix in {".cpp", ".c", ".hpp", ".h"}:
            return validate_cpp_plugin(desc, plugin_types,
                desired_library=desired_library, persist_compiled_files=persist_compiled_files)
    except Exception as e:
        return unsucessful_plugin_early_return(f"Error during plugin validation: {str(e)}")


def validate_plugin_type(description: PluginTypeInfo) -> PluginTypeValidationResult:
    """Validate plugin type implementation from source file.

    For now this follows the same runtime validation path as regular plugins.
    """
    source_file = description.info.get("SourceFile")
    if isinstance(source_file, str):
        source_file = Path(source_file)
    suffix = source_file.suffix.lower()
    extensions = get_supported_plugin_type_extensions()
    if suffix not in extensions:
        return unsucessful_plugin_type_early_return(
            f"Unsupported plugin type language for runtime validation: '{suffix}'")
    try:

        if suffix == ".capnp":
            # Cap'n Proto plugin types are validated at registration time by attempting to parse the file and extract the annotation
            return PluginTypeValidationResult(
                is_valid=True,
                message=None,
                validation_data=PluginTypeValidationData(
                ),
            )
    except Exception as e:
        return unsucessful_plugin_type_early_return(f"Error during plugin type validation: {str(e)}")
