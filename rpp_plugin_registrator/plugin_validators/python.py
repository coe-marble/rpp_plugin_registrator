
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from rpp_plugin_registrator.plugin_descriptors.core import (
    PluginInfo, PluginTypeInfo, PluginValidationData, PluginValidationResult
)

from ..utils import import_module_from_path


def _extract_plugin_type_from_mro(plugin_class: type, plugin_types: Dict[str, PluginTypeInfo]) -> Optional[str]:
    """Helper function to extract plugin type from MRO based on known plugin types."""
    base_names = [x["FullyQualifiedClassName"] for x in plugin_types.values()]
    for cls in plugin_class.__mro__:
        full_base = str(cls)
        if full_base in base_names:
            plugin = next((v for v in plugin_types.values() if v["FullyQualifiedClassName"] == full_base), None)
            return cls, plugin
    raise ValueError(f"Plugin class does not inherit from any known plugin type. MRO: {[cls.__name__ for cls in plugin_class.__mro__]}")



def _get_plugin_class(source_file: Path, class_name: str) -> Optional[type]:
    plugin_module = import_module_from_path(str(source_file))

    if not hasattr(plugin_module, class_name):
        raise ValueError(f"Class '{class_name}' not found in module '{plugin_module.__name__}' from file '{source_file}'.")

    return getattr(plugin_module, class_name)



def validate_python_plugin(desc: PluginInfo,
        plugin_types: Dict[str, PluginTypeInfo], **kwargs) -> PluginValidationResult:
    """Validate a Python plugin class and return validation data."""
    source_file = desc.info["SourceFile"]
    class_name = desc.info["ClassName"]

    try:
        plugin_class = _get_plugin_class(source_file, class_name)
    except ImportError as e:
        return PluginValidationResult(
            is_valid=False,
            message=f"Failed to import plugin class from '{source_file}': {e}",
            validation_data=None,
        )

    mro = [cls.__name__ for cls in plugin_class.__mro__]
    has_rpp_plugin = any(cls.__name__ == 'Plugin' for cls in plugin_class.__mro__)
    cls, plugin_type = _extract_plugin_type_from_mro(plugin_class, plugin_types)
    result_data = {
        "Mro": mro,
        "PluginType": plugin_type["PluginTypeName"],
        "ClassName": class_name,
        "FullyQualifiedClassName": str(plugin_class),
        "FullyQualifiedPluginClassName": str(cls),
        "PluginClassName": plugin_type["ClassName"],
        "PluginLibrary": plugin_type["Library"],
        "PluginSourceFile": plugin_type["SourceFile"],
    }

    if not has_rpp_plugin:
        return PluginValidationResult(
            is_valid=False,
            message=f"Plugin class '{class_name}' does not inherit from Plugin. MRO: {' -> '.join(mro)}",
            validation_data=result_data,
        )

    return PluginValidationResult(
        is_valid=True,
        message=None,
        validation_data=PluginValidationData(
            plugin_type=plugin_type["PluginTypeName"],
            plugin_type_library=plugin_type["Library"],
            plugin_type_class_name=plugin_type["ClassName"],
            plugin_type_source_file=plugin_type["SourceFile"],
            fully_qualified_plugin_class_name=str(cls),
            fully_qualified_class_name=str(plugin_class),
            class_name=class_name,
        )
    )
