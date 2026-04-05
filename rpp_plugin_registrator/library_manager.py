from __future__ import annotations

import json
import json5
import os
import re
import shutil
import warnings
from pathlib import Path

from matplotlib.pylab import f
from numpy import full
from sympy import li

from rpp_plugin_registrator import plugin_type_registrator as ptyp_reg_api
from rpp_plugin_registrator import plugin_registrator as p_reg_api
from rpp_plugin_registrator.plugin_descriptors.core import apply_library_context
from rpp_plugin_registrator.utils import to_pascal_case
import rpp_plugin_registrator.registry_paths as rp
from rpp_plugin_registrator.plugin_descriptors import parse_plugin_file
from rpp_plugin_registrator.plugin_validators import validate_plugin
from rpp_plugin_registrator.utils import import_module_from_path, load_json5, write_json
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
    build_library_plugin_entry,
    build_manifest_plugin_type_entry,
    build_plugin_info_payload,
)


class LibraryManager:
    """Manages component libraries and plugins in the RPP environment."""

    rpp_home = None
    registry_path = None

    def __init__(self, rpp_home: Path | None = None):
        self.rpp_home = Path(rpp_home).expanduser().resolve() if rpp_home is not None else rp.RPP_HOME
        rp.RPP_HOME = self.rpp_home
        self.registry_path = rp.get_app_registry_path()
        self._ensure_layout()

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
    def _manifest_path(library_path):
        return os.path.join(library_path, 'autogen', LIBRARY_MANIFEST_FILENAME)

    @staticmethod
    def _package_path(library_path):
        return os.path.join(library_path, LIBRARY_PACKAGE_FILENAME)

    @staticmethod
    def _plugins_path(library_path):
        return os.path.join(library_path, LIBRARY_PLUGINS_FILENAME)

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

    def _ensure_layout(self):
        """Ensure required directory structure exists."""
        ptyp_reg_api.ensure_rpp_layout()

    def start(self):
        """Start the library manager and ensure layout."""
        self._ensure_layout()

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
                    for k, v in registry.items():
                        if not isinstance(v, list):
                            v = [v]
                            registry[k] = v
                        for it in v:
                            it["Lib"] = data["Library"]
                            it["LibVersion"] = data["Version"]
                    plugins[data["Library"]] = registry
        return plugins

    def get_library_path(self, lib_name):
        """Get the path to a library by name."""
        if self.is_valid_component_library(lib_name):
            return lib_name

        reg = rp.get_app_libraries_path()
        fs = os.listdir(reg)

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

    def is_valid_component_library(self, path):
        """Check if a path is a valid component library."""
        return os.path.isfile(self._package_path(path)) and \
            os.path.isfile(self._plugins_path(path))

    def list_component_libraries(self):
        """List all registered component libraries."""
        libs = []
        reg = rp.get_app_libraries_path()
        fs = os.listdir(reg)

        for n in fs:
            if n in ['.', '..', 'slprj']:
                continue
            full_path = os.path.join(reg, n)
            if os.path.isdir(full_path):
                if self.is_valid_component_library(full_path):
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
                    if os.path.isdir(lib) and self.is_valid_component_library(lib):
                        info = self.get_library_info(lib, only_registered=True)
                        libs.append({
                            "Name": info['Library'],
                            "Type": "link",
                            "Path": lib,
                            "Version": info['Version']
                        })
        return libs

    # Component File Methods
    def is_supported_component_file(self, component_file):
        """Check if a file is a supported component file."""
        supported_extensions = ['.py']
        ext = os.path.splitext(component_file)[1].lower()
        return ext in supported_extensions

    def get_plugin_info_from_file(self, component_file):
        """Get plugin information from a component file."""
        desc = parse_plugin_file(component_file)
        desc = desc["Plugin"]

        class_name = desc["ClassName"]
        plugin_types = ptyp_reg_api.get_plugin_types()
        validation = validate_plugin(Path(component_file), class_name, plugin_types)
        if not validation.get("IsValid", False):
            error_message = validation.get("Error") or "Unknown plugin validation error"
            raise ValueError(error_message)
        validation_data = validation.get("Data", {})

        has_params = bool(desc.get("ParameterDescription"))
        description = desc.get("Description", "No description provided.")
        is_casadi = bool(desc.get("IsCasadi", False))

        plugin_info = build_plugin_info_payload(
            name=class_name,
            class_name=desc.get("ClassName"),
            plugin_type=validation_data["PluginType"],
            plugin_class_name=validation_data["PluginClassName"],
            fully_qualified_class_name=validation_data["FullyQualifiedClassName"],
            fully_qualified_plugin_class_name=validation_data["FullyQualifiedPluginClassName"],
            component_path=str(component_file),
            source_language=desc.get("SourceLanguage", "unknown"),
            has_parameters=has_params,
            description=description,
            is_casadi=is_casadi,
        )

        return plugin_info


    def get_plugin_class(self, plugin_path: str):
        """Get the plugin class from a plugin file."""
        if not os.path.exists(plugin_path):
            raise ValueError(f"Plugin path '{plugin_path}' does not exist.")

        file_stem = os.path.splitext(os.path.basename(plugin_path))[0]
        target_name = to_pascal_case(file_stem)
        plugin_module = import_module_from_path(plugin_path)
        if hasattr(plugin_module, target_name):
            return getattr(plugin_module, target_name)

        raise ValueError(f"Plugin class '{target_name}' was not found in '{plugin_path}'.")

    def get_plugin_class_from_info(self, info):
        """Get plugin class from plugin info dictionary."""
        plugin_path = info["ComponentPath"]
        return self.get_plugin_class(plugin_path)

    # Library Info Methods
    def get_plugin_info(self, lib_name_or_path, component_name):
        """Get plugin info from a library."""
        if self.is_valid_component_library(lib_name_or_path):
            lib_path = lib_name_or_path
        else:
            lib_path = self.get_library_path(lib_name_or_path)

        manifest_file = self._manifest_path(lib_path)
        if not os.path.isfile(manifest_file):
            raise ValueError(f"Library at '{lib_path}' does not contain a valid {LIBRARY_MANIFEST_FILENAME} file")

        plugins = load_json5(Path(manifest_file))
        registry = self._manifest_plugins(plugins)
        for comp_type, comps in registry.items():
            for comp in comps:
                if comp['Name'] == component_name:
                    return comp

    def get_library_info(self, lib_name_or_path, only_registered=True):
        """Get library metadata information."""
        if only_registered:
            if self.is_valid_component_library(lib_name_or_path):
                path = lib_name_or_path
            else:
                path = self.get_library_path(lib_name_or_path)
            if not os.path.isdir(lib_name_or_path) and not os.path.isdir(path):
                raise ValueError(f"Library '{lib_name_or_path}' is not a valid library")
            info = load_json5(Path(self._package_path(path)))
        else:
            if self.is_valid_component_library(lib_name_or_path):
                info = load_json5(Path(self._package_path(lib_name_or_path)))
            else:
                raise ValueError(f"Path '{lib_name_or_path}' is not a valid library")
        return info

    def get_plugin_info_from_lib(self, component_name, lib_name_or_path):
        """Get plugin information from a specific library."""
        lib_path = self.get_library_path(lib_name_or_path)
        manifest_file = self._manifest_path(lib_path)
        if not os.path.isfile(manifest_file):
            raise ValueError(f"Library at '{lib_path}' does not contain a valid {LIBRARY_MANIFEST_FILENAME} file")

        plugins = load_json5(Path(manifest_file))
        registry = self._manifest_plugins(plugins)
        for comp_type, comps in registry.items():
            for comp in comps:
                if comp['Name'] == component_name:
                    return comp

    # Library Management Methods
    def refresh_component_library(self, lib_name):
        """Refresh a component library's manifest."""
        path = self.get_library_path(lib_name)
        if not self.is_valid_component_library(path):
            raise ValueError(f"Library '{lib_name}' is not a valid library")

        plugins = load_json5(Path(self._plugins_path(path)))


        for plugin_type_path in self._iter_registration_files(path, plugins.get(LIBRARY_PLUGIN_TYPES_KEY, []), "Plugin type"):
            info = ptyp_reg_api.register_plugin_type_from_source(plugin_type_path, lib_name)
            self.add_to_manifest(lib_name, plugin_type=info)

        for comp_path in self._iter_registration_files(path, plugins.get(LIBRARY_PLUGINS_KEY, []), "Plugin"):
            try:
                comp_info = self.get_plugin_info_from_file(comp_path)
            except Exception as e:
                warnings.warn(f"Failed to get plugin info from '{comp_path}': {e}")
                continue
            self.register_component(comp_info, lib_name, append_to_json=False, append_to_manifest=True)

    def register_component_library(self, path, link_register=False, ask_dialog=True):
        """Register a component library."""
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
            self.refresh_component_library(lib_path.name)
        except Exception as e:
            if link_register:
                if json_path.exists():
                    json_path.unlink()
            else:
                if dest_path.exists():
                    shutil.rmtree(dest_path)
            raise e

        return str(lib_path)

    def remove_component_library(self, lib_name):
        """Remove a component library from registry."""
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

    def get_or_create_component_library(self, lib_name, library_path=None, close_after_creation=False):
        """Get or create a component library."""
        path = self.get_library_path(lib_name)
        if path is not None:
            return {
                'path': path,
                'name': lib_name
            }

        root_dir = rp.get_app_libraries_path() if library_path is None else library_path

        path = os.path.join(root_dir, lib_name)
        if not os.path.exists(path):
            os.makedirs(path)


        self.ensure_library_structure(path, lib_name)

        handle = {}
        handle['path'] = path
        handle['name'] = lib_name

        if library_path is not None:
            self.register_component_library(lib_name, library_path, link_register=True, ask_dialog=False)

        return handle

    # Component Registration Methods
    def register_component_from_file(self, component_file, lib_name):
        """Register a component from a file."""
        info = self.get_plugin_info_from_file(component_file)
        self.register_component(info, lib_name)
        return True

    def register_component(self, info, lib_name, append_to_json=True, append_to_manifest=True):

        info = apply_library_context(info, lib_name)
        ok = p_reg_api.register_plugin(info)

        if not ok:
            raise ValueError(f"Failed to register component '{info['Name']}' in library '{lib_name}'")

        """Register a component in a library."""
        lib_path = self.get_library_path(lib_name)
        if not self.is_valid_component_library(lib_path):
            raise ValueError(f"Library '{lib_name}' is not a valid library")

        if append_to_json:
            plugins_file = self._plugins_path(lib_path)
            plugins_data = load_json5(Path(plugins_file))
            if LIBRARY_PLUGINS_KEY not in plugins_data:
                plugins_data[LIBRARY_PLUGINS_KEY] = []

            for comp in plugins_data[LIBRARY_PLUGINS_KEY]:
                if comp['Name'] == info['Name']:
                    warnings.warn(f"Component '{info['Name']}' already exists in library '{lib_name}'. Overwriting.")
                    plugins_data[LIBRARY_PLUGINS_KEY].remove(comp)
                    break

            rel_path = os.path.relpath(info['ComponentPath'], lib_path)
            if rel_path.startswith('/'):
                rel_path = rel_path[1:]
            plugins_data[LIBRARY_PLUGINS_KEY].append(
                build_library_plugin_entry(name=info['Name'], path=rel_path, entry_type="file")
            )
            info["Lib"] = lib_name
            write_json(Path(plugins_file), plugins_data, indent=4, sort_keys=False)

        if append_to_manifest:
            self.add_to_manifest(lib_name, plugin=info)

    def add_to_manifest(self, lib_name, plugin=None, plugin_type=None):
        lib_path = self.get_library_path(lib_name)
        manifest_file = self._manifest_path(lib_path)
        manifest_data = load_json5(Path(manifest_file))

        if plugin is not None:
            plugin_name = plugin.get('PluginName')
            manifest_data.setdefault(LIBRARY_PLUGINS_KEY, {})
            manifest_data[LIBRARY_PLUGINS_KEY][plugin_name] = plugin
        if plugin_type is not None:
            comp_type = plugin_type.get('PluginType')
            manifest_data.setdefault(LIBRARY_PLUGIN_TYPES_KEY, {})
            manifest_data[LIBRARY_PLUGIN_TYPES_KEY][comp_type] = plugin_type

        write_json(Path(manifest_file), manifest_data, indent=4, sort_keys=False)

    def unregister_component(self, component_name, lib_name):
        """Unregister a component from a library."""
        lib_path = self.get_library_path(lib_name)
        if not self.is_valid_component_library(lib_path):
            raise ValueError(f"Library '{lib_name}' is not a valid library")
        manifest_file = self._manifest_path(lib_path)
        manifest_data = load_json5(Path(manifest_file))
        found = False
        registry = self._manifest_plugins(manifest_data)
        for comp_type, comps in registry.items():
            for comp in comps:
                if comp['Name'] == component_name:
                    comps.remove(comp)
                    found = True
                    break
            if found:
                break
        if not found:
            raise ValueError(f"Component '{component_name}' not found in library '{lib_name}'")
        write_json(Path(manifest_file), manifest_data, indent=4, sort_keys=False)

        plugins_file = self._plugins_path(lib_path)
        plugins_data = load_json5(Path(plugins_file))
        found = False
        for comp in plugins_data.get(LIBRARY_PLUGINS_KEY, []):
            if comp['Name'] == component_name:
                plugins_data[LIBRARY_PLUGINS_KEY].remove(comp)
                found = True
                break
        if not found:
            raise ValueError(f"Component '{component_name}' not found in library '{lib_name}'")
        write_json(Path(plugins_file), plugins_data, indent=4, sort_keys=False)

    # Component Detection Methods
    def make_component_registry_from_plugin_description(self, plugin_path, lib_name, save_manifest_library_path=None):
        """Create component registry from plugin description."""
        plugin_desc_path = self._plugins_path(plugin_path)
        if not plugin_desc_path.endswith(".json"):
            raise ValueError(f"Error parsing json. {plugin_desc_path} is not a json file.")
        try:
            with open(plugin_desc_path, 'r') as f:
                pd = json5.load(f)
        except Exception as e:
            print("Error parsing library plugins.json")
            raise e

        plugin_package_path = self._package_path(plugin_path)
        if not plugin_package_path.endswith(".json"):
            raise ValueError(f"Error parsing json. '{plugin_package_path}' is not a json file.")
        try:
            with open(plugin_package_path, 'r') as f:
                pkg = json5.load(f)
        except Exception as e:
            print("Error parsing library package.json")
            raise e

        lib_path = os.path.dirname(plugin_desc_path)
        registry = {z: [] for z in ptyp_reg_api.get_plugin_types_ids()}
        for p in pd.get('Plugins', []):
            if p['Type'] == 'folder_scan':
                scan_folder = os.path.join(lib_path, p['Path'])
                if not os.path.isdir(scan_folder):
                    warnings.warn(f"Plugin folder '{scan_folder} does not exist. Skipping...")
                    continue
                registry = self.detect_components_from_path(scan_folder, registry)
            elif p['Type'] == 'file':
                comp_path = os.path.join(lib_path, p['Path'])
                registry = self.detect_component(comp_path, registry)

        def append_lib_name_to_registry(registry, lib_name, version):
            for comps in registry.values():
                for comp in comps:
                    comp['Lib'] = lib_name
                    comp['LibVersion'] = version
            return registry

        append_lib_name_to_registry(registry, lib_name, pkg['Version'])

        if save_manifest_library_path is not None:
            manifest = build_library_manifest(pkg['Library'], plugins=registry, version=pkg['Version'])
            dir_name = os.path.dirname(save_manifest_library_path)
            if not os.path.exists(dir_name):
                os.makedirs(dir_name, exist_ok=True)
            write_json(Path(self._manifest_path(save_manifest_library_path)), manifest, indent=4, sort_keys=False)
        return registry

    def detect_components_from_path(self, path, registry=None):
        """Detect components from a directory path."""
        if registry is None:
            registry = {z: [] for z in ptyp_reg_api.get_plugin_types_ids()}
        for root, dirs, files in os.walk(path):
            for file in files:
                comp_path = os.path.join(root, file)
                registry = self.detect_component(comp_path, registry)
        return registry

    def detect_component(self, component_file, registry=None):
        """Detect a component from a file."""
        if registry is None:
            registry = {z: [] for z in ptyp_reg_api.get_plugin_types_ids()}
        if not os.path.isfile(component_file):
            raise FileNotFoundError(f"Component file '{component_file}' not found.")
        if not self.is_supported_component_file(component_file):
            warnings.warn(f"Component file '{component_file}' is not a supported component file. Skipping.")
            return registry

        try:
            comp_info = self.get_plugin_info_from_file(component_file)
        except Exception as e:
            warnings.warn(f"Failed to get plugin info from '{component_file}': {e}")
            return registry
        comp_type = comp_info.get('PluginType')
        if comp_type not in registry:
            registry[comp_type] = []
        registry[comp_type].append(comp_info)
        return registry

    def setup_library(self, lib_name_or_path):
        """Setup a library."""
        pass

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

    def _iter_registration_files(self, base_path, entries, entry_label):
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

                description_files = sorted(scan_folder.rglob('*.py'))

                for description_file in description_files:
                    yield description_file
            else:
                description_file = Path(base_path) / entry_path
                if not description_file.is_file():
                    warnings.warn(f"{entry_label} source '{description_file}' not found. Skipping...")
                    continue
                if description_file.suffix.lower() != '.py':
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