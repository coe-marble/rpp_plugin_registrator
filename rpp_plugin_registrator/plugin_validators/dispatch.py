from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Union

from .common import validation_result
from .python import validate_python_plugin, validate_python_plugin_type


def validate_plugin(source_file: Union[str, Path], class_name: str, plugin_types: Dict[str, Any]) -> Dict[str, Any]:
    """Validate plugin class by inferring language from file extension."""
    if isinstance(source_file, str):
        source_file = Path(source_file)
    suffix = source_file.suffix.lower()
    if suffix == ".py":
        return validate_python_plugin(source_file, class_name, plugin_types)
    return validation_result(
        False,
        f"Unsupported plugin language for runtime validation: '{suffix}'",
        {}
    )


def validate_plugin_type(source_file: Union[str, Path], class_name: str) -> Dict[str, Any]:
    """Validate plugin type implementation from source file.

    For now this follows the same runtime validation path as regular plugins.
    """
    if isinstance(source_file, str):
        source_file = Path(source_file)
    suffix = source_file.suffix.lower()
    if suffix == ".py":
        return validate_python_plugin_type(source_file, class_name)
    return validation_result(
        False,
        f"Unsupported plugin language for runtime validation: '{suffix}'",
        {},
    )

