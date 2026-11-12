"""Regenerate a registry for the installed registrator without resetting it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile

from . import plugin_type_registrator as types
from . import registry_config as rp
from .library_registration_status import _CAPNP_LIBRARY_IMPORT, _dependencies
from .registrator_version import current_registrator_version, is_newer_version
from .supported_plugins_and_types import (
    get_supported_plugin_extensions,
    get_supported_plugin_type_extensions,
)
from .utils import load_json5


@dataclass(frozen=True)
class MigrationPlan:
    target_version: str
    libraries: tuple[str, ...]
    native_sources: dict[str, tuple[Path, ...]]


def _registration_sources(manager, library_path):
    """Reject missing declarations rather than silently skipping them on refresh."""
    plugins = load_json5(Path(manager._plugins_path(library_path)))
    sources = []
    declared_paths = {}
    for key, extensions in (
            (rp.LIBRARY_PLUGIN_TYPES_KEY, get_supported_plugin_type_extensions()),
            (rp.LIBRARY_PLUGINS_KEY, get_supported_plugin_extensions())):
        for entry in manager._normalize_registration_entries(plugins.get(key, [])):
            path = Path(library_path) / entry.get("Path", "")
            if not entry.get("Path"):
                raise ValueError(f"Missing source path in {library_path}/plugins.json")
            if entry.get("Type", "file") == "folder_scan":
                if not path.is_dir():
                    raise ValueError(f"Registration folder does not exist: {path}")
            elif not path.is_file() or path.suffix.lower() not in extensions:
                raise ValueError(f"Missing or unsupported registration source: {path}")
        entries = list(manager._iter_registration_files(
            library_path, plugins.get(key, []), extensions, key))
        declared_paths[key] = {source.resolve() for source, _ in entries}
        sources.extend(entries)
    # A source removed from plugins.json would otherwise retain its old compiled
    # artifacts and still receive a new version stamp from a normal refresh.
    manifest = manager.load_lib_manifest(library_path)
    for key in (rp.LIBRARY_PLUGIN_TYPES_KEY, rp.LIBRARY_PLUGINS_KEY):
        for name, entry in manifest.get(key, {}).items():
            if key == rp.LIBRARY_PLUGIN_TYPES_KEY:
                entry = load_json5(rp.get_app_registry_plugin_type_json_path(name))
            source = entry.get("SourceFile")
            if not source or (Path(library_path) / source).resolve() not in declared_paths[key]:
                raise ValueError(f"Registered '{name}' has no source declaration in "
                                 f"{library_path}/plugins.json")
    return sources


def plan_registry_migration(manager) -> MigrationPlan:
    """Read dependencies and reject missing libraries or cycles before writing."""
    if not (rp.RPP_HOME / rp.INITIALIZED_MARKER_FILENAME).is_file():
        raise ValueError("Registry is not initialized; run 'rpp init-home' first")
    common_dir = types._resolve_common_plugins_dir(None)
    native_sources = {}
    priority = {"anot.capnp": 0, "msgs.capnp": 1}
    for source in sorted(common_dir.glob("**/*.capnp"), key=lambda path: (
            priority.get(path.name, 2), str(path))):
        native_sources.setdefault(source.parent.name, []).append(source)
    if not native_sources:
        raise ValueError(f"No bundled native schemas found in {common_dir}")

    libraries = {entry["Name"] for entry in manager.list_plugin_libraries()}
    for link in rp.get_app_libraries_path().glob("*.json"):
        if link.stem not in libraries:
            raise ValueError(f"Linked library '{link.stem}' is missing or invalid: {link}")
    libraries.update(native_sources)
    target_version = current_registrator_version()
    dependencies = {}
    for name in sorted(libraries):
        path = manager.get_library_path(name)
        deps = set()
        sources = []
        if path is not None:
            recorded = manager.load_lib_manifest(path).get(rp.LIBRARY_REGISTRATOR_VERSION_KEY)
            if is_newer_version(recorded, target_version):
                raise ValueError(f"Library '{name}' was registered with newer version {recorded}")
            deps.update(_dependencies(manager, path))
            if name not in native_sources:
                sources = _registration_sources(manager, path)
        sources.extend((source, {}) for source in native_sources.get(name, []))
        for source, entry in sources:
            if source.suffix.lower() == ".capnp":
                deps.update(_CAPNP_LIBRARY_IMPORT.findall(source.read_text(
                    encoding=manager.file_text_encoding)))
            plugin_type = entry.get("PluginType", "")
            if "::" in plugin_type:
                deps.add(plugin_type.split("::", 1)[0])
        deps.discard(name)
        dependencies[name] = deps

    ordered = []
    visiting = []
    visited = set()

    def visit(name):
        if name not in libraries:
            raise ValueError(f"Missing dependency '{name}' required by '{visiting[-1]}'")
        if name in visiting:
            raise ValueError("Library dependency cycle: " + " -> ".join([*visiting, name]))
        if name in visited:
            return
        visiting.append(name)
        for dependency in sorted(dependencies[name]):
            visit(dependency)
        visiting.pop()
        visited.add(name)
        ordered.append(name)

    # Native libraries are regenerated first, then every user library, including
    # ones already stamped current: their generated dependencies may have changed.
    for name in [*sorted(native_sources), *sorted(libraries)]:
        visit(name)
    return MigrationPlan(target_version, tuple(ordered), {
        name: tuple(sources) for name, sources in native_sources.items()})


def _restore_registry(home: Path, backup: Path):
    for name in ("registry", "interfaces", "descriptions", "libraries",
                 rp.INITIALIZED_MARKER_FILENAME):
        destination = home / name
        original = backup / name
        if destination.is_symlink() or destination.is_file():
            destination.unlink()
        elif destination.exists():
            shutil.rmtree(destination)
        if original.is_symlink():
            destination.symlink_to(original.readlink(), target_is_directory=original.is_dir())
        elif original.is_dir():
            shutil.copytree(original, destination, symlinks=True)
        elif original.exists():
            shutil.copy2(original, destination)


def migrate_registry(manager, *, progress=print, restore_on_error=True) -> Path:
    """Back up the registry, regenerate, and optionally roll back on error.

    Linked library sources are read in place; generated files stay in RPP_HOME.
    Callers must stop processes using the registry for the duration of migration.
    Backups are retained regardless of success or the rollback setting.
    """
    plan = plan_registry_migration(manager)
    home = rp.RPP_HOME.resolve()
    backup = Path(tempfile.mkdtemp(prefix=f"{home.name}-before-migration-", dir=home.parent))
    snapshot = backup / "home"
    shutil.copytree(home, snapshot, symlinks=True)
    progress(f"Registry backup: {snapshot}")
    try:
        manager._source_registered_libraries()
        for name in plan.libraries:
            progress(f"Migrating {name} to registrator {plan.target_version}")
            if name in plan.native_sources:
                types._ensure_default_library(types.get_rpp_paths(), name)
                for source in plan.native_sources[name]:
                    manager.register_plugin_type_from_source(source, name, override=True)
                manager._record_completed_library_registration_version(name)
            else:
                manager.refresh_plugin_library(name)
    except BaseException as error:
        if not restore_on_error:
            progress(f"Registry left in migration state; backup retained at: {snapshot}")
            raise
        # Include interruption so Ctrl-C does not leave half of the registry upgraded.
        try:
            _restore_registry(home, snapshot)
        except Exception as restore_error:
            raise RuntimeError(
                f"Migration failed ({error}); rollback also failed ({restore_error}). "
                f"Restore manually from {snapshot}"
            ) from error
        progress(f"Registry restored from: {snapshot}")
        raise
    return snapshot
