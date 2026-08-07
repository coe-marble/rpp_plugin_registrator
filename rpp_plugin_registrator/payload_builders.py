from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from .plugin_descriptors.core import PluginTypeMetadata, InterfaceInfo
from .registry_config import (
    LIBRARY_PLUGINS_KEY,
    LIBRARY_PLUGIN_TYPES_KEY,
    get_app_registry_path
)

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
) -> Dict[str, Any]:
    return {
        "Library": library,
        "Id": str(uuid4()),
        "Version": version,
        "Dependencies": [],
        "RosDependencies": [],
        "Install": [],
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
    source_file: str = "",
    description: str = "No description provided.",
    is_casadi: bool = False,

) -> Dict[str, Any]:
    return {
        "Name": name,
        "PluginName": plugin_name,
        "Library": library,
        "Description": description,
        "SourceFile": source_file,
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
    plugin: Dict[str, Any]
) -> Dict[str, Any]:
    path = str(Path(plugin["RegistryPluginTypeFile"])
               .relative_to(get_app_registry_path())),
    return {
        "Name": plugin["Name"],
        "PluginTypeName": plugin["PluginTypeName"],
        "Library": plugin["Library"],
        "ClassName": plugin["ClassName"],
        "FullyQualifiedClassName": plugin["FullyQualifiedClassName"],
        "RegistryPluginTypeFile": path[0],
    }

def build_library_manifest_plugin_entry(
    plugin: Dict[str, Any]
) -> Dict[str, Any]:
    return {
        "Name": plugin["Name"],
        "PluginName": plugin["PluginName"],
        "PluginType": plugin["PluginType"],
        "PluginTypeLibrary": plugin["PluginTypeLibrary"],
        "Library": plugin["Library"],
        "Description": plugin["Description"],
        "SourceFile": plugin["SourceFile"],
        "IsCasadi": plugin["IsCasadi"],
        "SourceLanguage": plugin["SourceLanguage"],
    }



def build_registry_plugin_type_entry(info: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "Id": info.get("Id"),
        "Name": info.get("Name"),
        "SourceFile": info.get("SourceFile"),
        "ClassName": info.get("ClassName"),
        "PluginTypeName": info.get("PluginTypeName"),
        "Library": info.get("Library"),
        "SourceLanguage": info.get("SourceLanguage"),
        "FullyQualifiedClassName": info.get("FullyQualifiedClassName"),
    }

def build_registry_plugin_entry(info: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "Id": info.get("Id"),
        "Name": info.get("Name"),
        "PluginName": info.get("PluginName"),
        "Library": info.get("Library"),
        "Description": info.get("Description"),
        "SourceFile": info.get("SourceFile"),
        "IsCasadi": info.get("IsCasadi"),
        "SourceLanguage": info.get("SourceLanguage"),
    }

def build_library_plugin_file_plugin_type_entry(name: str, path: str, entry_type: str = "file") -> Dict[str, Any]:
    return {
        "Name": name,
        "Path": path,
        "Type": entry_type,
    }