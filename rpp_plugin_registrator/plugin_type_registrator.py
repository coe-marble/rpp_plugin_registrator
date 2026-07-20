from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import os

from rpp_plugin_registrator.plugin_descriptors.core import (
    PluginTypeInfo,
    PluginTypeValidationResult, \
    apply_library_context_to_plugin_type,
    plugin_id_from_name
)
from rpp_plugin_registrator.plugin_registrator.dispatch import generate_plugin_type_interface
from rpp_plugin_registrator.plugin_validators import validate_plugin_type as validate_plugin_type_dispatch
from rpp_plugin_registrator.plugin_registrator import register_plugin_type as register_plugin_type_dispatch
from rpp_plugin_registrator.plugin_registrator import unregister_plugin_type as unregister_plugin_type_dispatch
from rpp_plugin_registrator.plugin_scaffold import scaffold_plugin

from . import registry_paths as rp
from .utils import load_json, write_json
from .library_constants import (
    LIBRARY_MANIFEST_FILENAME,
    LIBRARY_PACKAGE_FILENAME,
    LIBRARY_PLUGINS_FILENAME,
    LIBRARY_PLUGIN_TYPES_KEY,
    LIBRARY_PLUGINS_KEY,
)
from .payload_builders import (
    build_initialization_payload,
    build_library_manifest,
    build_library_package,
    build_plugin_type_info_payload,
    build_registry_plugin_type_entry,
    build_registry_payload,
)

SCAFFOLD_LANGUAGES = ["all"]


def plugin_id_from_plugin_name(plugin_name: str) -> str:
    return plugin_id_from_name(plugin_name)

def default_registry_payload() -> Dict[str, Any]:
    return build_registry_payload(rp.SCHEMA_VERSION)


def load_registry() -> Dict[str, Any]:
    resolved_path = rp.get_app_registry_plugin_types_json_path()
    if not resolved_path.exists():
        return default_registry_payload()
    return load_json(resolved_path)

def library_exists(library_name: str) -> bool:
    libraries_path = rp.get_app_libraries_path()
    library_path = libraries_path / library_name
    if library_path.exists() and library_path.is_dir():
        return True
    library_path_json = f"{library_path}.json"
    if Path(library_path_json).exists():
        return True
    return False


def get_rpp_paths() -> Dict[str, Path]:
    return rp.get_rpp_paths()


def _resolve_common_plugins_dir(common_plugins_dir: Optional[Path]) -> Path:
    if common_plugins_dir is not None:
        resolved_path = Path(common_plugins_dir).expanduser().resolve()
        if not resolved_path.exists() or not resolved_path.is_dir():
            raise ValueError(
                f"Common plugins directory does not exist or is not a directory: '{resolved_path}'"
            )
        return resolved_path

    # TODO: Consider using a more robust method to locate the default common plugins directory,
    # possibly using environment variables or configuration files.
    # Default to the 'rpp_common' directory relative to this file
    default_common_plugins_dir = Path(__file__).parent.parent.parent \
        / "rpp_common" / "rpp_common" / "common_plugin_types"

    return default_common_plugins_dir


def _ensure_default_library(paths: Dict[str, Path], library_name: str) -> Path:
    library_path = paths["libraries"] / library_name
    library_path.mkdir(parents=True, exist_ok=True)
    autogen_path = library_path / "autogen"
    autogen_path.mkdir(parents=True, exist_ok=True)

    package_path = library_path / LIBRARY_PACKAGE_FILENAME
    if not package_path.exists():
        write_json(package_path, build_library_package(library_name))

    plugins_path = library_path / LIBRARY_PLUGINS_FILENAME
    if not plugins_path.exists():
        write_json(
            plugins_path,
            {
                LIBRARY_PLUGINS_KEY: [],
                LIBRARY_PLUGIN_TYPES_KEY: [],
            },
        )

    manifest_path = autogen_path / LIBRARY_MANIFEST_FILENAME
    if not manifest_path.exists():
        write_json(manifest_path, build_library_manifest(library_name), indent=2, sort_keys=False)

    return library_path

def _initialize_common_plugins(paths: Dict[str, Path],
        common_plugins_dir: Optional[Path], init_anot_only: bool) -> List[str]:
    resolved_common_plugins_dir = _resolve_common_plugins_dir(common_plugins_dir)

    default_library_name = "rpp_common"
    _ensure_default_library(paths, default_library_name)

    priority_files = ["anot.capnp", "msgs.capnp"]

    def sort_key(file_path: Path) -> int:
        if file_path.name in priority_files:
            return priority_files.index(file_path.name)
        return len(priority_files) + 1


    common_plugin_names = os.getenv("RPP_WHITELIST_PLUGIN_TYPES", None)
    whitelist_plugin_types = common_plugin_names.split(";") if common_plugin_names else None
    whitelist_plugin_types = [name.strip() for name in whitelist_plugin_types] if whitelist_plugin_types else None

    initialized_plugin_types = []
    for source_file in sorted(
            resolved_common_plugins_dir.glob("**/*.capnp"), key=sort_key):
        types = register_plugin_type_from_source(source_file,
                default_library_name, whitelist_plugins=whitelist_plugin_types)
        initialized_plugin_types.extend(types)
        if init_anot_only and source_file.name == "anot.capnp":
            break
    return initialized_plugin_types


def scaffold_and_generate_from_description(description: PluginTypeInfo, only_stubs: bool = False) -> None:
    class_name = description.info.get("ClassName")
    lib_name = description.info.get("Library")
    if not class_name or not lib_name:
        raise ValueError(
            "Description must include 'ClassName', and 'Library' fields."
        )
    scaffold_plugin(description, rp.get_app_interfaces_path(),
            SCAFFOLD_LANGUAGES, only_stubs=only_stubs)
    if not only_stubs:
        generate_plugin_type_interface(description, SCAFFOLD_LANGUAGES)

def ensure_rpp_layout(
    common_plugins_dir: Optional[Path] = None,
    override_initialization: bool = False,
    init_anot_only: bool = False,
) -> List[Any]:
    paths = get_rpp_paths()
    paths["home"].mkdir(parents=True, exist_ok=True)
    paths["descriptions"].mkdir(parents=True, exist_ok=True)
    paths["interfaces"].mkdir(parents=True, exist_ok=True)
    paths["registry"].parent.mkdir(parents=True, exist_ok=True)
    paths["libraries"].mkdir(parents=True, exist_ok=True)

    init_marker_path = paths["home"] / rp.INITIALIZED_MARKER_FILENAME
    if init_marker_path.exists() and not override_initialization:
        return

    initialized_plugins = _initialize_common_plugins(paths, common_plugins_dir, init_anot_only=init_anot_only)

    plugins_list_str = [plugin["PluginTypeName"] for plugin in initialized_plugins]
    init_payload = build_initialization_payload(rp.SCHEMA_VERSION, plugins_list_str)
    write_json(init_marker_path, init_payload)
    return initialized_plugins


def get_plugin_types_ids() -> List[str]:
    registry = load_registry()
    return list(registry.get(LIBRARY_PLUGIN_TYPES_KEY, {}).keys())


def get_plugin_types() -> Dict[str, Any]:
    registry = load_registry()
    return registry.get(LIBRARY_PLUGIN_TYPES_KEY, {})


def get_plugins() -> Dict[str, Any]:
    registry = load_registry()
    return registry.get(LIBRARY_PLUGINS_KEY, {})


def validate_unique_plugin_id(requested_id: str, plugins: Dict[str, Any]) -> bool:
    if requested_id in plugins:
        return False
    return True


def validate_unique_class_name(class_name: Optional[str], plugin_id: str, plugins: Dict[str, Any]) -> bool:
    if not class_name:
        return
    for existing_id, existing_data in plugins.items():
        if existing_id == plugin_id:
            continue
        if existing_data.get("ClassName") == class_name:
            return False
    return True

def register_plugin_type(
    desc: PluginTypeInfo,
    registry = None
) -> dict[str, Any]:

    info = desc.info
    library = info.get("Library")
    if not library:
        raise ValueError("Description does not include Plugin.Library")

    source_file = info["SourceFile"]
    if not source_file:
        raise ValueError("Description does not include Plugin.SourceFile")

    registry_id = info.get("PluginTypeName")
    if not registry_id:
        raise ValueError("Description does not include Plugin.PluginTypeName")

    save_registry = False
    if registry is None:
        registry = load_registry()
        save_registry = True

    plugins = registry.setdefault(LIBRARY_PLUGIN_TYPES_KEY, {})

    register_result = register_plugin_type_dispatch(desc)
    if not register_result.success:
        raise ValueError(f"Plugin registration failed: {register_result.message}")
    desc.register_data = register_result.register_data
    scaffold_and_generate_from_description(desc)



    entry = desc.info
    if desc.validation_data:
        entry = {**entry, **desc.validation_data.as_dict()}
    if desc.register_data:
        entry = {**entry, **desc.register_data.as_dict()}

    plugins[registry_id] = entry
    if save_registry:
        write_json(rp.get_app_registry_plugin_types_json_path(), registry)
    return entry


def register_plugin_type_supporting_file(source_file: Path, library: str, parse_data: Dict[str, Any]) -> None:

    data = PluginTypeInfo(
        info={
            "SourceFile": str(source_file),
            "SourceLanguage": "capnp",
            "Library": library,
            "ClassName": source_file.stem,
            "IsSupportingFile": True,
        },
        register_data=None,
        parse_data=parse_data,
        validation_data=None,
    )
    register_data_result = register_plugin_type_dispatch(data)
    if not register_data_result.success:
        raise ValueError(f"Failed to register plugin type from file '{source_file}': {register_data_result.message}")
    data.register_data = register_data_result.register_data
    scaffold_and_generate_from_description(data, only_stubs=True)

def register_plugin_type_from_source(source_file: Path,
        library: str, whitelist_plugins: List[str] = None) -> list[dict[str, Any]]:

    """Register a plugin type from a source file and return the registered plugin type information.
    Args:
        source_file (Path): Path to the plugin type source file.
        library (str): Name of the library to which the plugin type belongs.
        whitelist_plugins (List[str], optional): List of plugin type names to register.
            If provided, only plugin types in this list will be registered. Defaults to None.
            Otherwise, all plugin types in the source file will be registered.
    Returns:
        list[dict[str, Any]]: The registered plugin type information.
    Raises:"""

    from rpp_plugin_registrator.plugin_descriptors import parse_plugin_type_file

    if not library_exists(library):
        raise ValueError(f"Library '{library}' does not exist.")

    source_path = Path(source_file).expanduser().resolve()
    parse_result = parse_plugin_type_file(source_path, plugin_id_override=None)
    if not parse_result.is_valid:
        raise ValueError(f"Failed to parse plugin type file '{source_path}': {parse_result.message}")
    ret_plugins = []

    registry = load_registry()
    plugin_types = registry.setdefault(LIBRARY_PLUGIN_TYPES_KEY, {})
    plugins_validated = []
    for plugin_desc in parse_result.data.plugins:
        interface = parse_result.data.interfaces.get(plugin_desc.interface_name)
        if not interface:
            raise ValueError(f"Interface '{plugin_desc.interface_name}' not found for plugin '{plugin_desc.plugin_type_name}' in file '{source_path}'.")

        info = build_plugin_type_info_payload(plugin_desc, interface, source_path)

        if whitelist_plugins is not None \
                and f"{library}::{info.get('Name')}" not in whitelist_plugins:
            continue  # Skip this plugin type if it's not in the whitelist

        # structs are autogenerated from register_plugin_type_supporting_file bellow
        plugin_type_info = PluginTypeInfo(info=info, parse_data=parse_result.data)

        apply_library_context_to_plugin_type(plugin_type_info.info, library)
        validation_result = validate_plugin_type(plugin_type_info, plugin_types)
        if not validation_result.is_valid:
            raise ValueError(f"Validation failed for plugin type '{plugin_type_info.info.get('PluginTypeName')}': {validation_result.message}")

        plugin_type_info.validation_data = validation_result.validation_data
        plugins_validated.append(plugin_type_info)

    register_plugin_type_supporting_file(source_path, library, parse_result.data)
    for plugin_desc in plugins_validated:
        info = register_plugin_type(plugin_desc, registry=registry)
        ret_plugins.append(info)

    write_json(rp.get_app_registry_plugin_types_json_path(), registry)
    return ret_plugins


def unregister_plugin_type(plugin_id: str, registry_path: Path, library: str) -> bool:
    if not registry_path.exists():
        return False

    registry = load_json(registry_path)
    plugin_types = registry.get(LIBRARY_PLUGIN_TYPES_KEY, {})
    if plugin_id not in plugin_types:
        return False

    entry = plugin_types[plugin_id]

    unregister_plugin_type_dispatch(entry)
    del plugin_types[plugin_id]
    write_json(registry_path, registry)
    return True


def validate_plugin_type(plugin_type_info: PluginTypeInfo, plugin_types: Dict[str, Any]) -> PluginTypeValidationResult:

    registry_id = plugin_type_info.info.get("PluginTypeName")
    class_name = plugin_type_info.info.get("ClassName")
    ok = validate_unique_plugin_id(registry_id, plugin_types) \
         and validate_unique_class_name(class_name, registry_id, plugin_types)

    if not ok:
        return PluginTypeValidationResult(
            is_valid=False,
            message=f"Plugin type '{registry_id}' is not unique in the registry.",
            validation_data=None
        )

    return validate_plugin_type_dispatch(plugin_type_info)

def list_registered_plugin_types(registry_path: Path) -> Dict[str, Any]:
    if not registry_path.exists():
        return default_registry_payload()
    return load_json(registry_path)

__all__ = [
    "get_plugin_types_ids",
    "get_plugin_types",
    "load_registry",
    "ensure_rpp_layout",
    "register_plugin_type_from_source",
    "unregister_plugin_type",
    "list_registered_plugin_types",
]