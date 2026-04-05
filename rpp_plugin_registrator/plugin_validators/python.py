
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from ..utils import import_module_from_path
from .common import validation_result


def _extract_plugin_type_from_mro(plugin_class: type, plugin_types: Dict[str, Any]) -> Optional[str]:
    """Helper function to extract plugin type from MRO based on known plugin types."""
    base_names = [x["FullyQualifiedClassName"] for x in plugin_types.values()]
    for cls in plugin_class.__mro__:
        full_base = str(cls)
        if full_base in base_names:
            plugin = next((v for v in plugin_types.values() if v["FullyQualifiedClassName"] == full_base), None)
            return cls, plugin
    raise ValueError(f"Plugin class does not inherit from any known plugin type. MRO: {[cls.__name__ for cls in plugin_class.__mro__]}")



def _get_plugin_class(source_file: Path, class_name: str) -> Optional[type]:
    try:
        plugin_module = import_module_from_path(str(source_file))
    except Exception as e:
        return validation_result(False, f"Failed to load plugin module from '{source_file}': {e}")

    if not hasattr(plugin_module, class_name):
        return validation_result(False, f"Plugin class '{class_name}' not found in module")

    return getattr(plugin_module, class_name)


def validate_python_plugin_type(source_file: Path, class_name: str) -> Dict[str, Any]:
    plugin_class = _get_plugin_class(source_file, class_name)

    mro = [cls.__name__ for cls in plugin_class.__mro__]
    has_rpp_plugin = any(cls.__name__ == 'RPP_Plugin' for cls in plugin_class.__mro__)
    err_msg = f"Plugin type class '{class_name}' does not inherit from RPP_Plugin. MRO: {' -> '.join(mro)}"
    result_data = {
        "Mro": mro,
        "ClassName": class_name,
        "FullyQualifiedClassName": str(plugin_class),
    }
    return validation_result(
        has_rpp_plugin,
        None if has_rpp_plugin else err_msg,
        result_data,
    )


def validate_python_plugin(source_file: Path, class_name: str, plugin_types: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a Python plugin class and return validation data."""

    plugin_class = _get_plugin_class(source_file, class_name)

    mro = [cls.__name__ for cls in plugin_class.__mro__]
    has_rpp_plugin = any(cls.__name__ == 'RPP_Plugin' for cls in plugin_class.__mro__)
    cls, plugin_type = _extract_plugin_type_from_mro(plugin_class, plugin_types)
    result_data = {
        "Mro": mro,
        "PluginType": plugin_type["PluginType"],
        "ClassName": class_name,
        "FullyQualifiedClassName": str(plugin_class),
        "FullyQualifiedPluginClassName": str(cls),
        "PluginClassName": plugin_type["ClassName"],
    }

    if not has_rpp_plugin:
        return validation_result(
            False,
            f"Plugin class '{class_name}' does not inherit from RPP_Plugin. MRO: {' -> '.join(mro)}",
            result_data,
        )

    return validation_result(True, None, result_data)
