from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from .library_constants import LIBRARY_PLUGIN_TYPES_KEY, LIBRARY_PLUGINS_KEY
from .plugin_descriptors.core import PluginTypeMetadata, InterfaceInfo


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
    plugin_name: str,
    library: str,
    source_language: str = "unknown",
    plugin_path: str = "",
    description: str = "No description provided.",
    is_casadi: bool = False,

) -> Dict[str, Any]:
    return {
        "Name": name,
        "PluginName": plugin_name,
        "Library": library,
        "Description": description,
        "PluginPath": plugin_path,
        "IsCasadi": is_casadi,
        "SourceLanguage": source_language,
    }


def build_plugin_type_info_payload(
    plugin_desc: PluginTypeMetadata,
    interface_desc: InterfaceInfo,
    source_file: Path,
) -> Dict[str, Any]:
    return {
        "Name": plugin_desc.plugin_name,
        "SourceFile": str(source_file.resolve()),
        "ClassName": plugin_desc.interface_name,
        "SourceLanguage": plugin_desc.type,
        "Methods": [method.as_dict() for method in interface_desc.methods],
    }



def build_library_manifest_plugin_type_entry(
    plugin: Dict[str, Any],
    description_path: Path,
    library: str,
) -> Dict[str, Any]:
    return {
        "Id": plugin.get("Id"),
        "Name": plugin.get("Name"),
        "DescriptionFile": str(description_path.resolve()),
        "SourceLanguage": plugin.get("SourceLanguage"),
        "ClassName": plugin.get("ClassName"),
        "PluginTypeName": plugin.get("PluginTypeName"),
        "FullyQualifiedClassName": plugin.get("FullyQualifiedClassName"),
        "Factory": plugin.get("RppRegistration", {}).get("Factory", {}),
        "Library": library,
    }



def build_registry_plugin_type_entry(info: Dict[str, Any]) -> Dict[str, Any]:
    registration = info.get("RppRegistration", {})
    factory = registration.get("Factory", {})
    entry = {
        "Id": info.get("Id"),
        "Name": info.get("Name"),
        "SourceFile": info.get("SourceFile"),
        "ClassName": info.get("ClassName"),
        "PluginTypeName": info.get("PluginTypeName"),
        "Factory": factory,
        "Library": info.get("Library"),
        "FullyQualifiedClassName": info.get("FullyQualifiedClassName"),
    }

    return entry

def build_library_plugin_file_plugin_type_entry(name: str, path: str, entry_type: str = "file") -> Dict[str, Any]:
    return {
        "Name": name,
        "Path": path,
        "Type": entry_type,
    }