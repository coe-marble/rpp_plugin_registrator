from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Dict, List, Optional

from rpp_plugin_registrator.plugin_descriptors.core import apply_library_context
from rpp_plugin_registrator.plugin_validators import validate_plugin_type

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
    build_library_component_entry,
    build_initialization_payload,
    build_library_manifest,
    build_library_plugin_entry,
    build_library_package,
    build_registry_entry,
    build_registry_payload,
)


def default_registry_payload() -> Dict[str, Any]:
    return build_registry_payload(rp.SCHEMA_VERSION)


def load_registry() -> Dict[str, Any]:
    resolved_path = rp.get_app_registry_path()
    if not resolved_path.exists():
        return default_registry_payload()
    return load_json(resolved_path)


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

    try:
        common_plugins_module = importlib.import_module("rpp_common.common_plugins")
    except ImportError as exc:
        raise RuntimeError(
            "Failed to resolve common plugins directory: could not import 'rpp_common.common_plugins'."
        ) from exc

    module_file = getattr(common_plugins_module, "__file__", None)
    if not module_file:
        raise RuntimeError(
            "Failed to resolve common plugins directory: module 'rpp_common.common_plugins' has no __file__."
        )

    resolved_path = Path(module_file).resolve().parent
    if not resolved_path.exists() or not resolved_path.is_dir():
        raise RuntimeError(
            f"Resolved common plugins directory is invalid: '{resolved_path}'"
        )
    return resolved_path


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


def _initialize_common_plugins(paths: Dict[str, Path], common_plugins_dir: Optional[Path]) -> List[str]:
    resolved_common_plugins_dir = _resolve_common_plugins_dir(common_plugins_dir)

    from rpp_plugin_registrator.plugin_descriptors import parse_python_plugin

    registry_path = paths["registry"]
    default_library_name = "rpp"
    library_path = _ensure_default_library(paths, default_library_name)
    registry = default_registry_payload()
    plugins = registry[LIBRARY_PLUGIN_TYPES_KEY]
    initialized_plugin_ids: List[str] = []
    library_registry: Dict[str, List[Dict[str, Any]]] = {}
    library_plugin_types_entries: List[Dict[str, Any]] = []
    library_plugin_types_manifest: Dict[str, Dict[str, Any]] = {}

    for source_file in sorted(resolved_common_plugins_dir.glob("*.py")):
        if source_file.name == "__init__.py":
            continue

        description = parse_python_plugin(source_file.resolve(), plugin_id=None)
        plugin = description["Plugin"]
        class_name = plugin.get("ClassName")
        plugin["PluginType"] = f"rpp::{class_name}"
        plugin["FullyQualifiedClassName"] = f"<class 'rpp_common.common_plugins.{source_file.stem}.{class_name}'>" if class_name else None
        plugin = apply_library_context(plugin, "rpp")
        plugin_id = plugin.get("Id")

        try:
            validate_unique_class_name(class_name, plugin_id, plugins)
        except ValueError:
            continue


        description_path = paths["descriptions"] / f"{plugin_id}.plugin.json"
        write_json(description_path, description)
        registry_entry = build_registry_entry(description, description_path)
        registry_entry["FullyQualifiedClassName"] = plugin["FullyQualifiedClassName"]
        plugins[plugin_id] = registry_entry
        library_entry = build_library_component_entry(description, source_file, default_library_name)
        library_plugin_types_entries.append(
            build_library_plugin_entry(
                name=plugin.get("Name") or plugin.get("ClassName") or plugin_id,
                path=str(description_path.resolve()),
                entry_type="file",
            )
        )
        library_plugin_types_manifest[plugin_id] = {
            "DescriptionFile": str(description_path.resolve()),
            "Name": plugin.get("Name"),
            "SourceLanguage": plugin.get("SourceLanguage"),
            "ClassName": plugin.get("ClassName"),
            "PluginType": plugin.get("PluginType"),
            "FullyQualifiedClassName": plugin.get("FullyQualifiedClassName"),
            "Factory": plugin.get("RppRegistration", {}).get("Factory", {}),
            "Library": default_library_name,
        }
        library_registry.setdefault(plugin.get("ClassName") or plugin.get("PluginType") or source_file.stem, []).append(
            library_entry
        )
        initialized_plugin_ids.append(plugin_id)

    write_json(
        library_path / LIBRARY_PLUGINS_FILENAME,
        {
            LIBRARY_PLUGIN_TYPES_KEY: library_plugin_types_entries,
        },
    )
    write_json(
        library_path / "autogen" / LIBRARY_MANIFEST_FILENAME,
        build_library_manifest(
            default_library_name,
            plugin_types=library_plugin_types_manifest,
        ),
    )

    write_json(registry_path, registry)
    return initialized_plugin_ids


def ensure_rpp_layout(
    common_plugins_dir: Optional[Path] = None,
    override_initialization: bool = False,
) -> None:
    paths = get_rpp_paths()
    paths["home"].mkdir(parents=True, exist_ok=True)
    paths["descriptions"].mkdir(parents=True, exist_ok=True)
    paths["interfaces"].mkdir(parents=True, exist_ok=True)
    paths["registry"].parent.mkdir(parents=True, exist_ok=True)
    paths["libraries"].mkdir(parents=True, exist_ok=True)

    init_marker_path = paths["home"] / rp.INITIALIZED_MARKER_FILENAME
    if init_marker_path.exists() and not override_initialization:
        return

    initialized_plugins = _initialize_common_plugins(paths, common_plugins_dir)
    init_payload = build_initialization_payload(rp.SCHEMA_VERSION, initialized_plugins)
    write_json(init_marker_path, init_payload)


def get_plugin_types_ids() -> List[str]:
    registry = load_registry()
    return list(registry.get(LIBRARY_PLUGIN_TYPES_KEY, {}).keys())


def get_plugin_types() -> List[str]:
    registry = load_registry()
    return registry.get(LIBRARY_PLUGIN_TYPES_KEY, {})


def validate_unique_plugin_id(requested_id: str, plugins: Dict[str, Any]) -> None:
    if requested_id in plugins:
        raise ValueError(f"Plugin type id '{requested_id}' is already registered.")


def validate_unique_class_name(class_name: Optional[str], plugin_id: str, plugins: Dict[str, Any]) -> None:
    if not class_name:
        return
    for existing_id, existing_data in plugins.items():
        if existing_id == plugin_id:
            continue
        if existing_data.get("ClassName") == class_name:
            raise ValueError(
                f"Class name '{class_name}' is already registered under plugin type id '{existing_id}'."
            )


def register_plugin_type(
    description: Dict[str, Any],
) -> str:
    plugin = description.get("Plugin", {})
    requested_plugin_id = plugin.get("Id")
    if not requested_plugin_id:
        raise ValueError("Description does not include Plugin.Id")

    library = plugin.get("Library")
    if not library:
        raise ValueError("Description does not include Plugin.Library")

    registry = load_registry()
    plugins = registry.setdefault(LIBRARY_PLUGIN_TYPES_KEY, {})
    validate_unique_plugin_id(requested_plugin_id, plugins)
    validate_unique_class_name(plugin.get("ClassName"), requested_plugin_id, plugins)

    description_file = plugin.get("DescriptionFile")
    if not description_file:
        raise ValueError("Description does not include Plugin.DescriptionFile")

    validation_result = validate_plugin_type(description_file, plugin["ClassName"])
    if not validation_result["IsValid"]:
        raise ValueError(f"Plugin validation failed: {validation_result.get('Error')}")

    description["Plugin"]["FullyQualifiedClassName"] = \
        validation_result["Data"].get("FullyQualifiedClassName")
    description["Plugin"]["PluginType"] = f"{library}::{description['Plugin']['ClassName']}"
    entry = build_registry_entry(description, Path(str(description_file)))

    plugins[requested_plugin_id] = entry
    write_json(rp.get_app_registry_path(), registry)
    return entry


def register_plugin_type_from_source(source_file: Path, library: str) -> str:
    from rpp_plugin_registrator.plugin_descriptors import parse_plugin_file

    source_path = Path(source_file).expanduser().resolve()
    description = parse_plugin_file(source_path)
    plugin = description.setdefault("Plugin", {})
    apply_library_context(plugin, library)
    description.setdefault("Plugin", {})["DescriptionFile"] = str(source_path)

    return register_plugin_type(description)


def unregister_plugin_type(plugin_id: str, registry_path: Path, library: str) -> bool:
    if not registry_path.exists():
        return False

    registry = load_json(registry_path)
    plugin_types = registry.get(LIBRARY_PLUGIN_TYPES_KEY, {})
    if plugin_id not in plugin_types:
        return False

    # Enforce library match.
    entry = plugin_types.get(plugin_id, {})
    if entry.get("Library") != library:
        return False

    del plugin_types[plugin_id]
    write_json(registry_path, registry)
    return True


def list_registered_plugin_types(registry_path: Path) -> Dict[str, Any]:
    if not registry_path.exists():
        return default_registry_payload()
    return load_json(registry_path)


__all__ = [
    "get_plugin_types_ids",
    "get_plugin_types",
    "load_registry",
    "ensure_rpp_layout",
    "resolve_output_path",
    "register_plugin_type",
    "register_plugin_type_from_source",
    "unregister_plugin_type",
    "list_registered_plugin_types",
]