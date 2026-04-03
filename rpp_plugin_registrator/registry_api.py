from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_VERSION = 1
RPP_HOME = Path.home() / ".rpp"
INITIALIZED_MARKER_FILENAME = ".initialized"


def default_registry_payload() -> Dict[str, Any]:
    return {
        "SchemaVersion": SCHEMA_VERSION,
        "System": "rpp",
        "Plugins": {},
    }


def resolve_registry_path(
    registry_path: Optional[Path] = None,
    rpp_home: Optional[Path] = None,
) -> Path:
    if registry_path is not None:
        return Path(registry_path).expanduser().resolve()
    home = Path(rpp_home).expanduser().resolve() if rpp_home is not None else RPP_HOME
    return (home / "registry" / "rpp_plugins.registry.json").resolve()


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def load_registry(
    registry_path: Optional[Path] = None,
    rpp_home: Optional[Path] = None,
) -> Dict[str, Any]:
    resolved_path = resolve_registry_path(registry_path=registry_path, rpp_home=rpp_home)
    if not resolved_path.exists():
        return default_registry_payload()
    return load_json(resolved_path)


def get_rpp_paths() -> Dict[str, Path]:
    return {
        "home": RPP_HOME,
        "descriptions": RPP_HOME / "descriptions",
        "interfaces": RPP_HOME / "interfaces",
        "registry": resolve_registry_path(rpp_home=RPP_HOME),
    }


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


def _build_registry_entry(description: Dict[str, Any], description_path: Path) -> Dict[str, Any]:
    plugin = description.get("Plugin", {})
    registration = plugin.get("RppRegistration", {})
    factory = registration.get("Factory", {})
    return {
        "DescriptionFile": str(description_path),
        "Name": plugin.get("Name"),
        "SourceLanguage": plugin.get("SourceLanguage"),
        "ClassName": plugin.get("ClassName"),
        "Factory": factory,
    }


def _initialize_common_plugins(paths: Dict[str, Path], common_plugins_dir: Optional[Path]) -> List[str]:
    resolved_common_plugins_dir = _resolve_common_plugins_dir(common_plugins_dir)

    from rpp_plugin_registrator.plugin_description_api import parse_python_plugin

    registry_path = paths["registry"]
    registry = load_registry(registry_path=registry_path)
    plugins = registry.setdefault("Plugins", {})
    initialized_plugin_ids: List[str] = []

    for source_file in sorted(resolved_common_plugins_dir.glob("*.py")):
        if source_file.name == "__init__.py":
            continue

        description = parse_python_plugin(source_file.resolve(), plugin_id=None)
        plugin = description.get("Plugin", {})
        plugin_id = plugin.get("Id")
        if not plugin_id:
            continue
        if plugin_id in plugins:
            continue

        class_name = plugin.get("ClassName")
        try:
            validate_unique_class_name(class_name, plugin_id, plugins)
        except ValueError:
            continue

        description_path = paths["descriptions"] / f"{plugin_id}.plugin.json"
        write_json(description_path, description)
        plugins[plugin_id] = _build_registry_entry(description, description_path)
        initialized_plugin_ids.append(plugin_id)

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

    init_marker_path = paths["home"] / INITIALIZED_MARKER_FILENAME
    if init_marker_path.exists() and not override_initialization:
        return

    initialized_plugins = _initialize_common_plugins(paths, common_plugins_dir)
    init_payload = {
        "SchemaVersion": SCHEMA_VERSION,
        "Initialized": True,
        "InitializedPlugins": initialized_plugins,
    }
    init_marker_path.write_text(json.dumps(init_payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def resolve_output_path(path_text: Optional[str], default_path: Path) -> Path:
    if path_text:
        return Path(path_text).expanduser().resolve()
    return default_path.resolve()


def get_plugin_tags(
    registry_path: Optional[Path] = None,
    rpp_home: Optional[Path] = None,
) -> List[str]:
    registry = load_registry(registry_path=registry_path, rpp_home=rpp_home)
    return sorted(registry.get("Plugins", {}).keys())


def get_plugin_types(
    registry_path: Optional[Path] = None,
    rpp_home: Optional[Path] = None,
) -> List[str]:
    registry = load_registry(registry_path=registry_path, rpp_home=rpp_home)
    plugins = registry.get("Plugins", {})
    class_names = {
        value.get("ClassName")
        for value in plugins.values()
        if isinstance(value, dict) and value.get("ClassName")
    }
    return sorted(class_names)


def validate_unique_plugin_id(requested_id: str, plugins: Dict[str, Any]) -> None:
    if requested_id in plugins:
        raise ValueError(f"Plugin id/tag '{requested_id}' is already registered.")


def validate_unique_class_name(class_name: Optional[str], plugin_id: str, plugins: Dict[str, Any]) -> None:
    if not class_name:
        return
    for existing_id, existing_data in plugins.items():
        if existing_id == plugin_id:
            continue
        if existing_data.get("ClassName") == class_name:
            raise ValueError(
                f"Class name '{class_name}' is already registered under plugin id '{existing_id}'."
            )


def register_description(description_path: Path, registry_path: Path) -> None:
    description = load_json(description_path)
    plugin = description.get("Plugin", {})
    requested_plugin_id = plugin.get("Id")
    if not requested_plugin_id:
        raise ValueError(f"Description '{description_path}' does not include plugin.id")

    registry = load_registry(registry_path=registry_path)
    plugins = registry.setdefault("Plugins", {})
    validate_unique_plugin_id(requested_plugin_id, plugins)
    validate_unique_class_name(plugin.get("ClassName"), requested_plugin_id, plugins)

    registration = plugin.get("RppRegistration", {})
    factory = registration.get("Factory", {})

    plugins[requested_plugin_id] = {
        "DescriptionFile": str(description_path),
        "Name": plugin.get("Name"),
        "SourceLanguage": plugin.get("SourceLanguage"),
        "ClassName": plugin.get("ClassName"),
        "Factory": factory,
    }
    write_json(registry_path, registry)


def register_descriptions_in_folder(folder_path: Path, registry_path: Path) -> List[Path]:
    if not folder_path.exists() or not folder_path.is_dir():
        raise ValueError(f"Description folder does not exist or is not a directory: '{folder_path}'")

    description_files = sorted(folder_path.glob("*.plugin.json"))
    if not description_files:
        description_files = sorted(folder_path.glob("*.json"))

    if not description_files:
        return []

    registered: List[Path] = []
    for description_path in description_files:
        register_description(description_path.resolve(), registry_path)
        registered.append(description_path.resolve())
    return registered


def unregister_plugin(plugin_id: str, registry_path: Path) -> bool:
    if not registry_path.exists():
        return False

    registry = load_json(registry_path)
    plugins = registry.get("Plugins", {})
    if plugin_id not in plugins:
        return False

    del plugins[plugin_id]
    write_json(registry_path, registry)
    return True


def list_registered_plugins(registry_path: Path) -> Dict[str, Any]:
    if not registry_path.exists():
        return default_registry_payload()
    return load_json(registry_path)
