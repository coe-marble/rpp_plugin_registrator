"""Derived registration information for a plugin library.

Only the registrator version is persisted in a library manifest.  This module
recomputes whether a library can be refreshed from the live registry.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING

import rpp_plugin_registrator.registry_config as rp
from rpp_plugin_registrator.registrator_version import (
    current_registrator_version,
    is_newer_version,
)
from rpp_plugin_registrator.registry_config import LIBRARY_REGISTRATOR_VERSION_KEY

if TYPE_CHECKING:
    from rpp_plugin_registrator.library_manager import LibraryManager


_CAPNP_LIBRARY_IMPORT = re.compile(r'\bimport\s+"([A-Za-z_][A-Za-z0-9_-]*)/')
_LIBRARY_DEPENDENCY_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_-]*')
@dataclass(frozen=True)
class LibraryRegistrationStatus:
    registered_version: str | None
    current_version: str
    dependencies: list[str]
    blocking_dependencies: list[str]

    @property
    def update_available(self) -> bool:
        return is_newer_version(self.current_version, self.registered_version)

    @property
    def refresh_ready(self) -> bool:
        return not self.blocking_dependencies


def _dependencies(manager: LibraryManager, library_path) -> list[str]:
    dependencies = set()
    package = manager.load_package_file(library_path)
    for dependency in package.get("Dependencies", []):
        match = _LIBRARY_DEPENDENCY_NAME.match(dependency)
        if match:
            dependencies.add(match.group(0))

    manifest = manager.load_lib_manifest(library_path)
    for plugin in manager._manifest_plugins(manifest).values():
        plugin_type_library = plugin.get("PluginTypeLibrary")
        if plugin_type_library:
            dependencies.add(plugin_type_library)

    registry_root = rp.get_app_registry_path()
    for plugin_type in manager._manifest_plugin_types(manifest).values():
        source_file = plugin_type.get("RegistryPluginTypeFile")
        if not source_file:
            continue
        try:
            source = (registry_root / source_file).read_text(
                encoding=manager.file_text_encoding)
        except OSError:
            continue
        dependencies.update(_CAPNP_LIBRARY_IMPORT.findall(source))

    dependencies.discard(manager.lib_name_from_path(library_path))
    return sorted(dependencies)


def _blocking_dependencies(
        manager: LibraryManager, library_path, current_version: str,
        visited=None) -> list[str]:
    library_name = manager.lib_name_from_path(library_path)
    visited = set() if visited is None else visited
    if library_name in visited:
        return []
    visited.add(library_name)

    blocked = set()
    for dependency in _dependencies(manager, library_path):
        dependency_path = manager.get_library_path(dependency)
        if dependency_path is None:
            blocked.add(dependency)
            continue
        dependency_manifest = manager.load_lib_manifest(dependency_path)
        if dependency_manifest.get(LIBRARY_REGISTRATOR_VERSION_KEY) != current_version:
            blocked.add(dependency)
            continue
        blocked.update(_blocking_dependencies(
            manager, dependency_path, current_version, visited))
    return sorted(blocked)


def compute_library_registration_status(
        manager: LibraryManager, library_name_or_path) -> LibraryRegistrationStatus:
    """Recompute a library's refresh eligibility from the current registry."""
    library_path = manager.get_library_path(library_name_or_path)
    if not manager.is_valid_plugin_library(library_path):
        raise ValueError(f"Library '{library_name_or_path}' is not a valid library")
    manifest = manager.load_lib_manifest(library_path)
    current_version = current_registrator_version()
    return LibraryRegistrationStatus(
        registered_version=manifest.get(LIBRARY_REGISTRATOR_VERSION_KEY),
        current_version=current_version,
        dependencies=_dependencies(manager, library_path),
        blocking_dependencies=_blocking_dependencies(
            manager, library_path, current_version),
    )
