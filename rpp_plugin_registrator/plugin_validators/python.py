
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from rpp_common import RPP_Plugin
from ..utils import import_module_from_path
from .common import validation_result


def _extract_plugin_type_from_mro(plugin_class: type, plugin_types: Dict[str, Any]) -> Optional[str]:
    """Helper function to extract plugin type from MRO based on known plugin types."""
    base_names = [x["FullyQualifiedBaseClassName"] for x in plugin_types.values()]
    for cls in plugin_class.__mro__:
        full_base = str(cls)
        if full_base in base_names:
            return next(
                (x["PluginType"] for x in plugin_types.values() if x["FullyQualifiedBaseClassName"] == full_base),
                None,
            )
    return None



def validate_python_plugin_instance(source_file: Path, class_name: str, plugin_types: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a Python plugin class and return validation data."""

    try:
        plugin_module = import_module_from_path(str(source_file))
    except Exception as e:
        return validation_result(False, f"Failed to load plugin module from '{source_file}': {e}")

    if not hasattr(plugin_module, class_name):
        return validation_result(False, f"Plugin class '{class_name}' not found in module")

    plugin_class = getattr(plugin_module, class_name)

    mro = [cls.__name__ for cls in plugin_class.__mro__]
    has_rpp_plugin = any(cls.__name__ == 'RPP_Plugin' for cls in plugin_class.__mro__)
    plugin_type = _extract_plugin_type_from_mro(plugin_class, plugin_types) or class_name
    result_data = {
        "mro": mro,
        "plugin_type": plugin_type,
        "class_name": class_name,
    }

    if not has_rpp_plugin:
        return validation_result(
            False,
            f"Plugin class '{class_name}' does not inherit from RPP_Plugin. MRO: {' -> '.join(mro)}",
            result_data,
        )

    try:
        instance = plugin_class()
    except TypeError as e:
        return validation_result(False, f"Failed to instantiate '{class_name}' with no arguments: {e}", result_data)
    except Exception as e:
        return validation_result(False, f"Exception during instantiation of '{class_name}': {e}", result_data)

    if not isinstance(instance, RPP_Plugin):
        instance_mro = [cls.__name__ for cls in instance.__class__.__mro__]
        result_data["instance_mro"] = instance_mro
        return validation_result(
            False,
            f"Instance of '{class_name}' is not an instance of RPP_Plugin. MRO: {' -> '.join(instance_mro)}",
            result_data,
        )

    return validation_result(True, None, result_data)
