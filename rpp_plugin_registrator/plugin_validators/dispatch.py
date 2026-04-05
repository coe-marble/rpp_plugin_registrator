from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .common import validation_result
from .python import validate_python_plugin_instance


def validate_plugin_instance(source_file: Path, class_name: str, plugin_types: Dict[str, Any]) -> Dict[str, Any]:
    """Validate plugin class by inferring language from file extension."""
    suffix = source_file.suffix.lower()
    if suffix == ".py":
        return validate_python_plugin_instance(source_file, class_name, plugin_types)
    return validation_result(
        False,
        f"Unsupported plugin language for runtime validation: '{suffix}'",
        {
            "class_name": class_name,
            "source_file": str(source_file),
        },
    )
