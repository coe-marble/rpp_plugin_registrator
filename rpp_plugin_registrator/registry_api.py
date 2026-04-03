from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_VERSION = 1
RPP_HOME = Path.home() / ".rpp"


def default_registry_payload() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "system": "rpp",
        "plugins": {},
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


def ensure_rpp_layout() -> None:
    paths = get_rpp_paths()
    paths["home"].mkdir(parents=True, exist_ok=True)
    paths["descriptions"].mkdir(parents=True, exist_ok=True)
    paths["interfaces"].mkdir(parents=True, exist_ok=True)
    paths["registry"].parent.mkdir(parents=True, exist_ok=True)


def resolve_output_path(path_text: Optional[str], default_path: Path) -> Path:
    if path_text:
        return Path(path_text).expanduser().resolve()
    return default_path.resolve()


def get_plugin_tags(
    registry_path: Optional[Path] = None,
    rpp_home: Optional[Path] = None,
) -> List[str]:
    registry = load_registry(registry_path=registry_path, rpp_home=rpp_home)
    return sorted(registry.get("plugins", {}).keys())


def get_plugin_types(
    registry_path: Optional[Path] = None,
    rpp_home: Optional[Path] = None,
) -> List[str]:
    registry = load_registry(registry_path=registry_path, rpp_home=rpp_home)
    plugins = registry.get("plugins", {})
    class_names = {
        value.get("class_name")
        for value in plugins.values()
        if isinstance(value, dict) and value.get("class_name")
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
        if existing_data.get("class_name") == class_name:
            raise ValueError(
                f"Class name '{class_name}' is already registered under plugin id '{existing_id}'."
            )


def register_description(description_path: Path, registry_path: Path) -> None:
    description = load_json(description_path)
    plugin = description.get("plugin", {})
    requested_plugin_id = plugin.get("id")
    if not requested_plugin_id:
        raise ValueError(f"Description '{description_path}' does not include plugin.id")

    registry = load_registry(registry_path=registry_path)
    plugins = registry.setdefault("plugins", {})
    validate_unique_plugin_id(requested_plugin_id, plugins)
    validate_unique_class_name(plugin.get("class_name"), requested_plugin_id, plugins)

    plugins[requested_plugin_id] = {
        "description_file": str(description_path),
        "name": plugin.get("name"),
        "source_language": plugin.get("source_language"),
        "class_name": plugin.get("class_name"),
        "factory": plugin.get("rpp_registration", {}).get("factory", {}),
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
    plugins = registry.get("plugins", {})
    if plugin_id not in plugins:
        return False

    del plugins[plugin_id]
    write_json(registry_path, registry)
    return True


def list_registered_plugins(registry_path: Path) -> Dict[str, Any]:
    if not registry_path.exists():
        return default_registry_payload()
    return load_json(registry_path)
