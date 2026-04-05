from __future__ import annotations

from typing import Any, Dict
from pathlib import Path

from .python import register_python_plugin

from rpp_plugin_registrator.library_constants import LIBRARY_PLUGIN_TYPES_KEY
from rpp_plugin_registrator.payload_builders import build_registry_payload
from rpp_plugin_registrator import registry_paths as rp
from rpp_plugin_registrator.utils import load_json, write_json


def _load_registry_for_path(registry_path: Path) -> Dict[str, Any]:
    if not registry_path.exists():
        return build_registry_payload(rp.SCHEMA_VERSION)
    return load_json(registry_path)

def register_plugin(description: Dict[str, Any]) -> str:
    plugin = description.get("Plugin", {})
    source_language = str(plugin.get("SourceLanguage") or "python").lower()

    if source_language == "python":
        return register_python_plugin(description)
    else:
        raise ValueError(f"No registrator available for source language '{source_language}'.")