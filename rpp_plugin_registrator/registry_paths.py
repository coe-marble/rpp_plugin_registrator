from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

SCHEMA_VERSION = 1
RPP_HOME = Path.home() / ".rpp"
INITIALIZED_MARKER_FILENAME = ".initialized"


def get_app_registry_plugin_types_json_path() -> Path:
    return (RPP_HOME / "registry" / "rpp_plugin_types.registry.json").resolve()

def get_app_registry_path() -> Path:
    return (RPP_HOME / "registry").resolve()

def get_app_capnp_interfaces_path() -> Path:
    return (RPP_HOME / "registry" / "capnp").resolve()

def get_app_libraries_path() -> Path:
    return (RPP_HOME / "libraries").resolve()

def get_app_interfaces_path() -> Path:
    return (RPP_HOME / "interfaces").resolve()

def get_rpp_paths() -> Dict[str, Path]:
    return {
        "home": RPP_HOME,
        "descriptions": RPP_HOME / "descriptions",
        "interfaces": RPP_HOME / "interfaces",
        "registry": get_app_registry_plugin_types_json_path(),
        "libraries": get_app_libraries_path(),
    }

def resolve_output_path(path_text: Optional[str], default_path: Path) -> Path:
    if path_text:
        return Path(path_text).expanduser().resolve()
    return default_path.resolve()
