from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

SCHEMA_VERSION = 1
RPP_HOME = Path.home() / ".rpp"
INITIALIZED_MARKER_FILENAME = ".initialized"
USE_ROS2_COMPILATION = False
RPP_CPP_CORE_PATH = None

LIBRARY_PACKAGE_FILENAME = "package.json"
LIBRARY_PLUGINS_FILENAME = "plugins.json"
LIBRARY_MANIFEST_FILENAME = "manifest.json"

LIBRARY_PLUGINS_KEY = "Plugins"
LIBRARY_PLUGIN_TYPES_KEY = "PluginTypes"



def get_app_registry_json_path() -> Path:
    return (RPP_HOME / "registry" / "rpp_plugin_types.json").resolve()

def get_app_library_manifest_path_json(lib_name: str) -> Path:
    return RPP_HOME / "registry" / "libraries" / lib_name / "manifest.json"

def get_app_registry_plugin_type_json_path(plugin_type_name) -> Path:
    lib_name, plugin_type_name = plugin_type_name.split("::", 1)
    return (RPP_HOME / "registry" / "libraries" / lib_name / "rpp_plugin_types" / f"{plugin_type_name}.json").resolve()

def get_app_registry_plugin_json_path(plugin_name) -> Path:
    lib_name, plugin_name = plugin_name.split("::", 1)
    return (RPP_HOME / "registry" / "libraries" / lib_name / "rpp_plugins" / f"{plugin_name}.json").resolve()

def get_app_registry_path() -> Path:
    return (RPP_HOME / "registry").resolve()

def get_app_capnp_interfaces_path() -> Path:
    return (RPP_HOME / "registry" / "capnp").resolve()

def get_app_libraries_path() -> Path:
    return (RPP_HOME / "libraries").resolve()

def get_app_config_path() -> Path:
    return (RPP_HOME / "config.json").resolve()

def get_app_interfaces_path() -> Path:
    return (RPP_HOME / "interfaces").resolve()

def get_rpp_paths() -> Dict[str, Path]:
    return {
        "home": RPP_HOME,
        "descriptions": RPP_HOME / "descriptions",
        "interfaces": RPP_HOME / "interfaces",
        "registry": get_app_registry_path(),
        "libraries": get_app_libraries_path(),
    }

def resolve_output_path(path_text: Optional[str], default_path: Path) -> Path:
    if path_text:
        return Path(path_text).expanduser().resolve()
    return default_path.resolve()


def get_library_manager() -> 'LibraryManager':
    if __INIT_SET.get("library_manager") is None:
        raise RuntimeError("Library manager has not been set. Please call 'load_and_set_config' first.")
    return __INIT_SET["library_manager"]


def get_setting(setting_name: str) -> Optional[str]:
    if setting_name not in __INIT_SET["settings"]:
        raise ValueError(f"Setting '{setting_name}' is not a valid setting."
            + f" Available settings: {__INIT_SET['settings'].keys()}")
    return __INIT_SET["settings"][setting_name]

def set_to_config(setting_name: str, setting_value: str) -> None:

    import rpp_plugin_registrator.registry_config as rp
    if setting_name not in __INIT_SET["settings"]:
        raise ValueError(f"Setting '{setting_name}' is not a valid setting."
            + f" Available settings: {__INIT_SET['settings'].keys()}")
    config_path = get_app_config_path()
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
    else:
        config_data = {}

    if setting_value in ["true", "True"]:
        setting_value = True
    elif setting_value in ["false", "False"]:
        setting_value = False

    config_data[setting_name] = setting_value
    __INIT_SET["settings"][setting_name] = setting_value
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f)
    return True

def get_config():
    config_path = get_app_config_path()
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
    else:
        config_data = {}
    return config_data

def load_and_set_config(library_manager) -> Dict[str, str]:

    if __INIT_SET.get("config_loaded", False):
        return
    __INIT_SET["library_manager"] = library_manager
    __INIT_SET["config_loaded"] = True
    import rpp_plugin_registrator.registry_config as rp
    config_path = get_app_config_path()
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
    else:
        config_data = {}
    for key, value in config_data.items():
        if key in __INIT_SET["settings"]:
            __INIT_SET["settings"][key] = value

__INIT_SET = {}
def reset_module() -> None:
    __INIT_SET.clear()
    set_defaults()

def set_defaults() -> None:
    __INIT_SET["settings"] = {
        "USE_ROS2_COMPILATION": USE_ROS2_COMPILATION,
        "RPP_CPP_CORE_PATH": RPP_CPP_CORE_PATH,
    }
reset_module()