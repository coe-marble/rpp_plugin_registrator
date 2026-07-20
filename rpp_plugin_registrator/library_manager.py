from __future__ import annotations

import json
from typing import Union
import json5
import os, sys
import shutil
import warnings
from pathlib import Path
from dataclasses import dataclass
import rpp_plugin_registrator.registry_paths as rp
from rpp_plugin_registrator import plugin_type_registrator as ptyp_reg_api
from rpp_plugin_registrator import plugin_registrator as p_reg_api
from rpp_plugin_registrator.plugin_descriptors.core import PluginInfo, apply_library_context_to_plugin
from rpp_plugin_registrator.utils import to_pascal_case
from rpp_plugin_registrator.plugin_descriptors import parse_plugin_file
from rpp_plugin_registrator.plugin_descriptors import plugin_id_from_name as plugin_id_from_name_util
from rpp_plugin_registrator.plugin_validators import validate_plugin
from rpp_plugin_registrator.utils import import_module_from_path, load_json5, write_json
from rpp_plugin_registrator.supported_plugins_and_types import (
    get_supported_plugin_type_extensions,
    get_supported_plugin_extensions
)

from rpp_plugin_registrator.library_constants import (
    LIBRARY_MANIFEST_FILENAME,
    LIBRARY_PACKAGE_FILENAME,
    LIBRARY_PLUGINS_FILENAME,
    LIBRARY_PLUGIN_TYPES_KEY,
    LIBRARY_PLUGINS_KEY,
)
from rpp_plugin_registrator.payload_builders import (
    build_library_manifest,
    build_library_package,
    build_library_plugin_file_plugin_type_entry,
    build_plugin_info_payload,
)

@dataclass
class LibraryHandle:
    path: Path
    name: str


class LibraryManager:
    """Manages plugin libraries, plugins and plugin types in the RPP environment."""

    rpp_home = None
    registry_path = None

    def __init__(self, rpp_home: Path | None = None, source_libraries : bool = True, init_anot_only: bool = False):
        self.rpp_home = Path(rpp_home).expanduser().resolve() if rpp_home is not None else rp.RPP_HOME
        rp.RPP_HOME = self.rpp_home


        self.registry_path = rp.get_app_registry_plugin_types_json_path()
        self._ensure_layout(init_anot_only=init_anot_only)
        if source_libraries:
            self._source_registered_libraries()

    @property
    def is_long_generation(self):
        return False

    @property
    def is_long_library_management(self):
        return False

    @staticmethod
    def _manifest_plugins(manifest_data):
        return manifest_data.get(LIBRARY_PLUGINS_KEY, {})

    @staticmethod
    def _manifest_plugin_types(manifest_data):
        return manifest_data.get(LIBRARY_PLUGIN_TYPES_KEY, {})

    @staticmethod
    def _manifest_path(library_path):
        return os.path.join(library_path, 'autogen', LIBRARY_MANIFEST_FILENAME)

    @staticmethod
    def _package_path(library_path):
        return os.path.join(library_path, LIBRARY_PACKAGE_FILENAME)

    @staticmethod
    def _plugins_path(library_path):
        return os.path.join(library_path, LIBRARY_PLUGINS_FILENAME)

    @staticmethod
    def _lib_name_from_path(library_path):
        return Path(library_path).name


    def _source_registered_libraries(self):
        library_autogen_path = rp.get_app_interfaces_path()
        python_autogen_path = library_autogen_path / "python"
        if not python_autogen_path.exists():
            python_autogen_path.mkdir(parents=True, exist_ok=True)
        abs_path = os.path.abspath(str(python_autogen_path))
        if abs_path not in sys.path:
            sys.path.append(abs_path)


    # Plugin methods
    def parse_plugin_name(self, plugin_name):
        """Parse a plugin type name into library and name."""
        if "::" not in plugin_name:
            raise ValueError(f"Invalid plugin type name '{plugin_name}'. Expected format 'Library::TypeName'.")
        lib_name, type_name = plugin_name.split("::", 1)
        return lib_name, type_name

    def get_type_of_plugin(self, plugin_name):
        """Get the plugin type of a registered plugin."""
        lib_name, plugin_name_in_lib = self.parse_plugin_name(plugin_name)
        lib_path = self.get_library_path(lib_name)
        if lib_path is None:
            raise ValueError(f"Library '{lib_name}' does not exist.")
        manifest_file = self._manifest_path(lib_path)
        if not os.path.isfile(manifest_file):
            raise ValueError(f"Library at '{lib_path}' does not contain a valid {LIBRARY_MANIFEST_FILENAME} file")

    def ensure_library_structure(self, lib_path, lib_name):

        autogen_folder = os.path.join(lib_path, 'autogen')
        if not os.path.exists(autogen_folder):
            os.makedirs(autogen_folder)

        src_folder = os.path.join(lib_path, 'src')
        if not os.path.exists(src_folder):
            os.makedirs(src_folder)

        lib_folder = os.path.join(lib_path, lib_name)
        if not os.path.exists(lib_folder):
            os.makedirs(lib_folder)

        if not os.path.exists(self._plugins_path(lib_path)):
            plugins_txt = _PLUGINS_TEMPLATE.replace('{{library_name}}', lib_name)
            with open(self._plugins_path(lib_path), 'w') as f:
                f.write(plugins_txt)

        if not os.path.exists(self._package_path(lib_path)):
            lib_meta = build_library_package(lib_name)
            write_json(Path(self._package_path(lib_path)), lib_meta, indent=4, sort_keys=False)

        if not os.path.exists(self._manifest_path(lib_path)):
            manifest = build_library_manifest(lib_name)
            write_json(Path(self._manifest_path(lib_path)), manifest, indent=4, sort_keys=False)

    def _ensure_layout(self, init_anot_only: bool = False):
        """Ensure required directory structure exists."""
        types = ptyp_reg_api.ensure_rpp_layout(init_anot_only=init_anot_only)
        first = types[0] if types else None
        if first is None:
            return
        lib_name = first.get("Library")
        self.add_to_manifest(lib_name=lib_name, plugin_type_or_list=types)

    # Library Query Methods
    def get_available_plugins(self):
        """Get all available plugins from registered libraries."""
        reg = rp.get_app_libraries_path()
        fs = os.listdir(reg)
        plugins = {}
        for n in fs:
            if n in ['.', '..', 'slprj']:
                continue
            full_path = os.path.join(reg, n)
            manifest_file = None
            if os.path.isdir(full_path):
                manifest_file = self._manifest_path(full_path)
            elif n.endswith('.json'):
                with open(full_path, 'r') as f:
                    s = json5.load(f)
                    lib = s['Path']
                    manifest_file = self._manifest_path(lib)
            if os.path.isfile(manifest_file):
                with open(manifest_file, 'r') as f:
                    data = json5.load(f)
                    registry = self._manifest_plugins(data)
                    pt_dict = {}
                    for k, v in registry.items():
                        plugin_type = v["PluginType"]
                        if plugin_type not in pt_dict:
                            pt_dict[plugin_type] = []
                        pt_dict[plugin_type].append(v)
                    plugins[data["Library"]] = pt_dict
        return plugins

    def get_library_path(self, lib_name):
        """Get the path to a library by name."""
        if self.is_valid_plugin_library(lib_name):
            return lib_name

        reg = rp.get_app_libraries_path()
        fs = os.listdir(str(reg.resolve()))

        for n in fs:
            if n in ['.', '..', 'slprj']:
                continue
            if not (n == lib_name or n == f"{lib_name}.json"):
                continue

            full_path = os.path.join(reg, n)
            if os.path.isdir(full_path):
                return full_path
            elif n.endswith('.json'):
                with open(full_path, 'r') as f:
                    s = load_json5(Path(full_path))
                    lib = s['Path']
                    return lib
        return None


    def is_valid_plugin_library(self, path):
        """Check if a path is a valid plugin library."""
        if path is None:
            return False
        return os.path.isfile(self._package_path(path)) and \
            os.path.isfile(self._plugins_path(path))

    def list_plugin_libraries(self):
        """List all registered plugin libraries."""
        libs = []
        reg = rp.get_app_libraries_path()
        fs = os.listdir(reg)

        for n in fs:
            if n in ['.', '..', 'slprj']:
                continue
            full_path = os.path.join(reg, n)
            if os.path.isdir(full_path):
                if self.is_valid_plugin_library(full_path):
                    info = self.get_library_info(full_path, only_registered=True)
                    libs.append({
                        "Name": info['Library'],
                        "Type": "install",
                        "Path": full_path,
                        "Version": info['Version']
                    })
            elif n.endswith('.json'):
                with open(full_path, 'r') as f:
                    s = load_json5(Path(full_path))
                    lib = s['Path']
                    if os.path.isdir(lib) and self.is_valid_plugin_library(lib):
                        info = self.get_library_info(lib, only_registered=True)
                        libs.append({
                            "Name": info['Library'],
                            "Type": "link",
                            "Path": lib,
                            "Version": info['Version']
                        })
        return libs

    # Plugin File Methods
    def is_supported_plugin_file(self, plugin_file: Union[str, Path]) -> bool:
        """Check if a file is a supported plugin file."""
        plugin_file = str(plugin_file)
        supported_extensions = get_supported_plugin_extensions()
        ext = os.path.splitext(plugin_file)[1].lower()
        return ext in supported_extensions

    def is_supported_plugin_type_file(self, plugin_file: Union[str, Path]) -> bool:
        """Check if a file is a supported plugin type file."""
        plugin_file = str(plugin_file)
        supported_extensions = get_supported_plugin_type_extensions()
        ext = os.path.splitext(plugin_file)[1].lower()
        return ext in supported_extensions


    def get_plugin_info_from_file(self, plugin_file,
            plugin_name=None, persist_compiled_files=False) -> PluginInfo:
        """Get plugin information from a plugin file."""
        parse_result = parse_plugin_file(plugin_file)

        if not parse_result.is_valid:
            raise ValueError(f"Failed to parse plugin file '{plugin_file}':\n{parse_result.message}")

        plugins = parse_result.data.plugins
        if len(plugins) == 0:
            raise ValueError(f"No plugin found in '{plugin_file}'.")

        if plugin_name is not None:
            if len(plugins) > 1:
                raise ValueError(f"Multiple plugins found in '{plugin_file}'. Please specify a plugin name.")
            for _, desc in plugins:
                plugin = desc.get("Plugin", {})
                if plugin.get("Name") == plugin_name:
                    break
            else:
                raise ValueError(f"Plugin '{plugin_name}' not found in '{plugin_file}'.")
        else:
            desc = plugins[0]

        plugin_info = PluginInfo(
            info=desc
        )
        plugin_types = ptyp_reg_api.get_plugin_types()
        validation = validate_plugin(plugin_info,
                plugin_types=plugin_types,
                persist_compiled_files=persist_compiled_files
        )
        if not validation.is_valid:
            error_message = validation.message or "Unknown plugin validation error"
            raise ValueError(error_message)

        plugin_info.validation_data = validation.validation_data


        return plugin_info

    def plugin_id_from_name(self, plugin_name: str) -> str:
        return plugin_id_from_name_util(plugin_name)

    def get_plugin_class(self, plugin_path: str, class_name: str = None):
        """Get the plugin class from a plugin file."""
        if not os.path.exists(plugin_path):
            raise ValueError(f"Plugin path '{plugin_path}' does not exist.")

        if class_name is None:
            file_stem = os.path.splitext(os.path.basename(plugin_path))[0]
            class_name = to_pascal_case(file_stem)
        plugin_module = import_module_from_path(plugin_path)
        if hasattr(plugin_module, class_name):
            return getattr(plugin_module, class_name)

        raise ValueError(f"Plugin class '{class_name}' was not found in '{plugin_path}'.")

    def get_plugin_class_from_info(self, info):
        """Get plugin class from plugin info dictionary."""
        plugin_path = self.get_plugin_path_absolute(info["PluginPath"], info["Library"])
        class_name = info["ClassName"]
        return self.get_plugin_class(plugin_path, class_name)


    def get_plugin_components_from_lib(self, plugin_name, lib_name_or_path=None):
        info = self.get_plugin_info_from_lib(plugin_name, lib_name_or_path)
        return info.get("PluginMetadata", {}).get("Components", {})

    def get_plugin_parameters_from_lib(self, plugin_name, lib_name_or_path=None):
        info = self.get_plugin_info_from_lib(plugin_name, lib_name_or_path)
        return info.get("PluginMetadata", {}).get("Parameters", {})

    def get_plugin_path_absolute(self, plugin_path_relative_to_library: str, library: str) -> Path:
        lib_path = self.get_library_path(library)
        if not self.is_valid_plugin_library(lib_path):
            raise ValueError(f"Library '{library}' is not a valid library")

        return Path(lib_path) / plugin_path_relative_to_library

    # Library Info Methods
    def get_library_info(self, lib_name_or_path, only_registered=True):
        """Get library metadata information."""
        if only_registered:
            if self.is_valid_plugin_library(lib_name_or_path):
                path = lib_name_or_path
            else:
                path = self.get_library_path(lib_name_or_path)
            if not os.path.isdir(lib_name_or_path) and not os.path.isdir(path):
                raise ValueError(f"Library '{lib_name_or_path}' is not a valid library")
            info = load_json5(Path(self._package_path(path)))
        else:
            if self.is_valid_plugin_library(lib_name_or_path):
                info = load_json5(Path(self._package_path(lib_name_or_path)))
            else:
                raise ValueError(f"Path '{lib_name_or_path}' is not a valid library")
        return info

    def get_plugin_info_from_lib(self, plugin_name, lib_name_or_path=None):
        """Get plugin information from a specific library."""
        if lib_name_or_path is None:
            lib_name_or_path, plugin_name = self.parse_plugin_name(plugin_name)

        lib_path = self.get_library_path(lib_name_or_path)
        if not self.is_valid_plugin_library(lib_path):
            raise ValueError(f"Library '{lib_name_or_path}' is not a valid library")
        lib_name = self._lib_name_from_path(lib_path)
        manifest = self.load_lib_manifest(lib_path)

        registry = self._manifest_plugins(manifest)
        plugin_name = f"{lib_name}::{plugin_name}"
        info = registry.get(plugin_name, None)
        if info is None:
            raise ValueError(f"Plugin '{plugin_name}' not found in library '{lib_name}'")
        return info

    def get_plugin_type_info_from_lib(self, plugin_type_name, lib_name_or_path=None):
        """Get plugin type information from a specific library."""
        if lib_name_or_path is None:
            lib_name_or_path, plugin_type_name = self.parse_plugin_name(plugin_type_name)
        lib_path = self.get_library_path(lib_name_or_path)
        lib_name = self._lib_name_from_path(lib_path)
        manifest = self.load_lib_manifest(lib_path)

        plugin_types = self._manifest_plugin_types(manifest)
        plugin_type = f"{lib_name}::{plugin_type_name}"
        info =  plugin_types.get(plugin_type, None)
        if info is None:
            raise ValueError(f"Plugin type '{plugin_type_name}' not found in library '{lib_name}'")
        return info

    # Library Management Methods
    def refresh_plugin_library(self, lib_name, throw=True):
        """Refresh a plugin library's manifest."""
        path = self.get_library_path(lib_name)
        if not self.is_valid_plugin_library(path):
            raise ValueError(f"Library '{lib_name}' is not a valid library")

        plugins = load_json5(Path(self._plugins_path(path)))

        exts = get_supported_plugin_type_extensions()
        for plugin_type_path in self._iter_registration_files(path,
                plugins.get(LIBRARY_PLUGIN_TYPES_KEY, []), exts, "Plugin type"):
            infos = ptyp_reg_api.register_plugin_type_from_source(plugin_type_path, lib_name)
            self.add_to_manifest(lib_name, plugin_type_or_list=infos)

        exts = get_supported_plugin_extensions()
        for comp_path in self._iter_registration_files(path,
                plugins.get(LIBRARY_PLUGINS_KEY, []), exts, "Plugin"):
            try:
                comp_info = self.get_plugin_info_from_file(comp_path, persist_compiled_files=True)
            except Exception as e:
                warnings.warn(f"Failed to get plugin info from '{comp_path}': {e}")
                if throw:
                    raise e
                continue
            self.register_plugin(comp_info, lib_name, append_to_json=False, append_to_manifest=True)

    def register_plugin_library(self, path, link_register=False, ask_dialog=True):
        """Register a plugin library."""
        reg_path = rp.get_app_libraries_path()
        lib_path = Path(path).resolve()
        dest_path = Path(reg_path) / lib_path.name

        if not link_register:
            if dest_path.exists():
                raise FileExistsError(f"Library '{lib_path.name}' already exists in registry")
            shutil.copytree(lib_path, dest_path)
            lib_path = dest_path
        else:
            json_path = dest_path.with_suffix('.json')
            info = self.get_library_info(lib_path, only_registered=False)
            if json_path.exists():
                raise FileExistsError(f"Library '{lib_path.name}' already exists in registry")
            with open(json_path, 'w') as f:
                json.dump({
                    'Path': str(lib_path),
                    'Library': info['Library'],
                    'Version': info.get('Version', '0.0.1')
                }, f, indent=4)

        autogen_path = lib_path / 'autogen'
        if autogen_path.exists():
            shutil.rmtree(autogen_path)
        self.ensure_library_structure(lib_path, lib_path.name)

        try:
            self.refresh_plugin_library(lib_path.name)
        except Exception as e:
            if link_register:
                if json_path.exists():
                    json_path.unlink()
            else:
                if dest_path.exists():
                    shutil.rmtree(dest_path)
            raise e

        return str(lib_path)

    def remove_plugin_library(self, lib_name):
        """Remove a plugin library from registry."""
        reg = rp.get_app_libraries_path()
        lib_folder = os.path.join(reg, lib_name)
        lib_json = os.path.join(reg, f"{lib_name}.json")
        if os.path.isdir(lib_folder):
            shutil.rmtree(lib_folder)
            return lib_folder
        elif os.path.isfile(lib_json):
            os.remove(lib_json)
            return lib_json
        else:
            raise FileNotFoundError(f"Library '{lib_name}' not found in registry")

    def get_or_create_plugin_library(self, lib_name, library_path=None, close_after_creation=False):
        """Get or create a plugin library."""
        path = self.get_library_path(lib_name)
        if path is not None:
            return LibraryHandle(path=path, name=lib_name)

        root_dir = rp.get_app_libraries_path() if library_path is None else library_path

        path = os.path.join(root_dir, lib_name)
        if not os.path.exists(path):
            os.makedirs(path)


        self.ensure_library_structure(path, lib_name)

        if library_path is not None:
            self.register_plugin_library(path, link_register=True, ask_dialog=False)

        return LibraryHandle(path=Path(path), name=lib_name)


    def get_library_plugins(self, lib_name_or_path, source_language=None):
        """Get all plugins from a specific library."""
        lib_path = self.get_library_path(lib_name_or_path)
        if not self.is_valid_plugin_library(lib_path):
            raise ValueError(f"Library '{lib_name_or_path}' is not a valid library")
        manifest = self.load_lib_manifest(lib_path)
        plugins = self._manifest_plugins(manifest)
        return self._filter_by_source_language(plugins, source_language)

    def get_library_plugin_types(self, lib_name_or_path, source_language=None):
        """Get all plugin types from a specific library."""
        lib_path = self.get_library_path(lib_name_or_path)
        if not self.is_valid_plugin_library(lib_path):
            raise ValueError(f"Library '{lib_name_or_path}' is not a valid library")
        manifest = self.load_lib_manifest(lib_path)
        plugin_types =  self._manifest_plugin_types(manifest)
        return self._filter_by_source_language(plugin_types, source_language)

    # Plugin Registration Methods
    def register_plugin_from_source(self, plugin_file:Union[str, Path], lib_name:str):
        """Register a plugin from a file."""
        plugin_file = Path(plugin_file).resolve()
        if not self.is_supported_plugin_file(plugin_file):
            raise ValueError(f"File '{plugin_file}' is not a supported plugin file.")
        path = self.get_library_path(lib_name)
        if path is None:
            raise ValueError(f"Library '{lib_name}' does not exist.")
        # Plugin_file must be in the library context
        if not plugin_file.is_relative_to(path):
            raise ValueError(f"File '{plugin_file}' is not in the library context '{path}'.")
        info = self.get_plugin_info_from_file(plugin_file, persist_compiled_files=True)
        return self.register_plugin(info, lib_name)

    def register_plugin(self, plugin_info: PluginInfo, lib_name: str, append_to_json=True, append_to_manifest=True):
        """Register a plugin in a library."""

        lib_path = self.get_library_path(lib_name)
        if not self.is_valid_plugin_library(lib_path):
            raise ValueError(f"Library '{lib_name}' is not a valid library")

        plugin_info.info = apply_library_context_to_plugin(plugin_info.info, lib_name)

        registration_result = p_reg_api.register_plugin(plugin_info)
        if not registration_result.success:
            raise ValueError(f"Failed to register plugin '{plugin_info['Name']}' in library '{lib_name}'")
        desc = plugin_info.info
        rel_path = os.path.relpath(desc['SourceFile'], lib_path)
        if rel_path.startswith('/'):
            rel_path = rel_path[1:]

        description = desc.get("Description", "No description provided.")
        is_casadi = bool(desc.get("IsCasadi", False))

        validation_data = plugin_info.validation_data

        plugin_info = build_plugin_info_payload(
            name=desc["Name"],
            plugin_name=desc["PluginName"],
            plugin_path=str(rel_path),
            source_language=desc["SourceLanguage"],
            description=description,
            library=lib_name,
            is_casadi=is_casadi,
        )

        if validation_data is not None:
            plugin_info = {**plugin_info, **validation_data.as_dict()}
        if registration_result.register_data is not None:
            plugin_info = {**plugin_info, **registration_result.register_data.as_dict()}

        if append_to_json:
            plugins_file = self._plugins_path(lib_path)
            plugins_data = load_json5(Path(plugins_file))
            if LIBRARY_PLUGINS_KEY not in plugins_data:
                plugins_data[LIBRARY_PLUGINS_KEY] = []

            for comp in plugins_data[LIBRARY_PLUGINS_KEY]:
                if comp['Name'] == plugin_info['Name']:
                    warnings.warn(f"Plugin '{plugin_info['Name']}' already exists in library '{lib_name}'. Overwriting.")
                    plugins_data[LIBRARY_PLUGINS_KEY].remove(comp)
                    break

            plugins_data[LIBRARY_PLUGINS_KEY].append(
                build_library_plugin_file_plugin_type_entry(name=plugin_info['PluginName'], path=rel_path, entry_type="file")
            )
            write_json(Path(plugins_file), plugins_data, indent=4, sort_keys=False)

        if append_to_manifest:
            self.add_to_manifest(lib_name, plugin_or_list=plugin_info)
        return plugin_info

    def load_lib_manifest(self, lib_path):
        """Load the manifest file for a library."""
        manifest_file = self._manifest_path(lib_path)
        if not os.path.isfile(manifest_file):
            raise ValueError(f"Library at '{lib_path}' does not contain a valid {LIBRARY_MANIFEST_FILENAME} file")
        return load_json5(Path(manifest_file))

    def save_lib_manifest(self, lib_path, manifest_data):
        """Save the manifest file for a library."""
        manifest_file = self._manifest_path(lib_path)
        write_json(Path(manifest_file), manifest_data, indent=4, sort_keys=False)

    def add_to_manifest(self, lib_name,
            plugin_or_list: dict | list | None = None,
            plugin_type_or_list: dict | list | None = None):
        lib_path = self.get_library_path(lib_name)
        manifest_data = self.load_lib_manifest(lib_path)

        if plugin_or_list is not None:
            plugin_list = plugin_or_list \
                    if isinstance(plugin_or_list, list) else [plugin_or_list]
            for plugin in plugin_list:
                plugin_name = plugin['PluginName']
                manifest_data.setdefault(LIBRARY_PLUGINS_KEY, {})
                manifest_data[LIBRARY_PLUGINS_KEY][plugin_name] = plugin
        if plugin_type_or_list is not None:
            plugin_type_list = plugin_type_or_list \
                    if isinstance(plugin_type_or_list, list) else [plugin_type_or_list]
            for plugin_type in plugin_type_list:
                plugin_type_name = plugin_type['PluginTypeName']
                manifest_data.setdefault(LIBRARY_PLUGIN_TYPES_KEY, {})
                manifest_data[LIBRARY_PLUGIN_TYPES_KEY][plugin_type_name] = plugin_type

        self.save_lib_manifest(lib_path, manifest_data)

    def unregister_plugin(self, plugin_name, lib_name):
        """Unregister a plugin from a library."""
        lib_path = self.get_library_path(lib_name)
        if not self.is_valid_plugin_library(lib_path):
            raise ValueError(f"Library '{lib_name}' is not a valid library")

        manifest_data = self.load_lib_manifest(lib_path)
        registry = self._manifest_plugins(manifest_data)
        found = False
        for comp_type, comps in registry.items():
            for comp in comps:
                if comp['Name'] == plugin_name:
                    comps.remove(comp)
                    found = True
                    break
            if found:
                break
        if not found:
            raise ValueError(f"Plugin '{plugin_name}' not found in library '{lib_name}'")
        self.save_lib_manifest(lib_path, manifest_data)

        plugins_file = self._plugins_path(lib_path)
        plugins_data = load_json5(Path(plugins_file))
        found = False
        for comp in plugins_data.get(LIBRARY_PLUGINS_KEY, []):
            if comp['Name'] == plugin_name:
                plugins_data[LIBRARY_PLUGINS_KEY].remove(comp)
                found = True
                break
        if not found:
            raise ValueError(f"Plugin '{plugin_name}' not found in library '{lib_name}'")
        write_json(Path(plugins_file), plugins_data, indent=4, sort_keys=False)

    @staticmethod
    def _normalize_registration_entries(entries):
        if entries is None:
            return []
        if isinstance(entries, dict):
            normalized = []
            for name, value in entries.items():
                if isinstance(value, dict):
                    entry = dict(value)
                else:
                    entry = {"Path": value}
                entry.setdefault("Name", name)
                normalized.append(entry)
            return normalized
        if isinstance(entries, list):
            return entries
        return []

    def _filter_by_source_language(self, entries, source_language):
        if source_language is None:
            return entries
        filtered = {}
        for name, entry in entries.items():
            if entry.get("SourceLanguage") != source_language:
                continue
            filtered[name] = entry
        return filtered

    def _iter_registration_files(self, base_path, entries, search_file_extensions, entry_label):
        glob_pattern = f"*.[{''.join(search_file_extensions)}]"
        for entry in self._normalize_registration_entries(entries):
            entry_type = entry.get('Type', 'file')
            entry_path = entry.get('Path')
            if not entry_path:
                continue

            if entry_type == 'folder_scan':
                scan_folder = Path(base_path) / entry_path
                if not scan_folder.is_dir():
                    warnings.warn(f"{entry_label} folder '{scan_folder}' does not exist. Skipping...")
                    continue

                description_files = sorted(scan_folder.rglob(glob_pattern))

                for description_file in description_files:
                    yield description_file
            else:
                description_file = Path(base_path) / entry_path
                if not description_file.is_file():
                    warnings.warn(f"{entry_label} source '{description_file}' not found. Skipping...")
                    continue
                if description_file.suffix.lower() not in search_file_extensions:
                    warnings.warn(f"{entry_label} source '{description_file}' is not a Python file. Skipping...")
                    continue
                yield description_file


# Template for plugins.json
_PLUGINS_TEMPLATE = """
{
    "Library": "{{library_name}}",
    "Plugins": [
        // list your plugins here as json objects
        // specify the type of each to either 'folder_scan' or 'file'
    ],
    "PluginTypes": [
        // list your plugin type implementations (.py) here as json objects
        // specify the type of each to either 'folder_scan' or 'file'
    ]
}
"""