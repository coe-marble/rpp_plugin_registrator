from __future__ import annotations

from typing import Any, Dict, List
from uuid import uuid4

from .library_constants import LIBRARY_PLUGIN_TYPES_KEY, LIBRARY_PLUGINS_KEY


def build_library_manifest(
    library: str,
    plugins: Dict[str, Any] | None = None,
    plugin_types: Dict[str, Any] | None = None,
    version: str = "0.0.1",
) -> Dict[str, Any]:
    return {
        "Library": library,
        LIBRARY_PLUGINS_KEY: plugins or {},
        LIBRARY_PLUGIN_TYPES_KEY: plugin_types or {},
        "Version": version,
    }


def build_library_package(
    library: str,
    version: str = "0.0.1",
    package_id: str | None = None,
    dependencies: List[str] | None = None,
    install: List[str] | None = None,
) -> Dict[str, Any]:
    return {
        "Library": library,
        "Id": package_id or str(uuid4()),
        "Version": version,
        "Dependencies": dependencies or [],
        "Install": install or [],
    }


def build_registry_payload(schema_version: int | str, system: str = "rpp") -> Dict[str, Any]:
    return {
        "SchemaVersion": schema_version,
        "System": system,
        LIBRARY_PLUGIN_TYPES_KEY: {},
    }


def build_initialization_payload(schema_version: int | str, initialized_plugins: List[str]) -> Dict[str, Any]:
    return {
        "SchemaVersion": schema_version,
        "Initialized": True,
        "InitializedPlugins": initialized_plugins,
    }


def build_plugin_info_payload(
    name: str,
    plugin_tag: str,
    component_path: str,
    source_language: str = "unknown",
    has_parameters: bool = False,
    description: str = "No description provided.",
    is_casadi: bool = False,
) -> Dict[str, Any]:
    return {
        "Name": name,
        "T": plugin_tag,
        "HasParameters": has_parameters,
        "Description": description,
        "IsCasadi": is_casadi,
        "ComponentPath": component_path,
        "Type": source_language,
    }


def build_library_plugin_entry(name: str, path: str, entry_type: str = "file") -> Dict[str, Any]:
    return {
        "Name": name,
        "Path": path,
        "Type": entry_type,
    }


def build_manifest_plugin_type_entry(
    description_file: str,
    name: str | None,
    source_language: str | None,
    class_name: str | None,
    plugin_type: str | None,
    library: str,
) -> Dict[str, Any]:
    return {
        "DescriptionFile": description_file,
        "Name": name,
        "SourceLanguage": source_language,
        "ClassName": class_name,
        "PluginType": plugin_type or class_name,
        "Library": library,
    }