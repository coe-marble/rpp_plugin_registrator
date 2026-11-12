"""Migration planning and rollback without invoking generators or compilers."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from rpp_plugin_registrator import migration, registry_config as rp
from rpp_plugin_registrator.library_manager import LibraryManager


@pytest.fixture
def registry(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "libraries").mkdir(parents=True)
    (home / rp.INITIALIZED_MARKER_FILENAME).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(rp, "RPP_HOME", home)
    monkeypatch.setattr(rp, "load_and_set_config", Mock())
    native = tmp_path / "native" / "rpp_common"
    native.mkdir(parents=True)
    (native / "anot.capnp").write_text("# Native schema\n", encoding="utf-8")
    monkeypatch.setattr(migration.types, "_resolve_common_plugins_dir", lambda _: native.parent)
    manager = LibraryManager(rpp_home=home, skip_layout_check=True)
    yield manager
    rp.reset_module()


def add_library(manager, name, dependencies=()):
    library = manager.get_or_create_plugin_library(name)
    package = Path(library.path) / "package.json"
    data = json.loads(package.read_text(encoding="utf-8"))
    data["Dependencies"] = list(dependencies)
    package.write_text(json.dumps(data), encoding="utf-8")
    return library


def snapshot(root):
    result = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            result[str(path.relative_to(root))] = ("link", str(path.readlink()))
        elif path.is_file():
            result[str(path.relative_to(root))] = ("file", path.read_bytes())
    return result


def test_plan_orders_dependencies_and_includes_current_libraries(registry):
    add_library(registry, "AConsumer", ["ZDependency"])
    dependency = add_library(registry, "ZDependency", ["rpp_common"])
    registry._record_completed_library_registration_version(dependency.path)
    before = snapshot(rp.RPP_HOME)

    plan = migration.plan_registry_migration(registry)

    assert plan.libraries == ("rpp_common", "ZDependency", "AConsumer")
    assert snapshot(rp.RPP_HOME) == before


@pytest.mark.parametrize("dependencies, message", [
    (["Missing"], "Missing dependency"),
    (["Consumer"], "dependency cycle"),
])
def test_invalid_graph_is_rejected_before_backup(registry, dependencies, message):
    add_library(registry, "Consumer", ["Dependency"])
    add_library(registry, "Dependency", dependencies)
    before = snapshot(rp.RPP_HOME)

    with pytest.raises(ValueError, match=message):
        migration.migrate_registry(registry)

    assert snapshot(rp.RPP_HOME) == before
    assert not list(rp.RPP_HOME.parent.glob("home-before-migration-*"))


@pytest.mark.parametrize("failure", [RuntimeError("generator failed"), KeyboardInterrupt()])
@pytest.mark.parametrize("restore_on_error", [True, False])
def test_failure_honors_restore_option_and_retains_backup(
        registry, monkeypatch, failure, restore_on_error):
    add_library(registry, "Consumer", ["rpp_common"])
    interfaces = rp.RPP_HOME / "interfaces"
    interfaces.mkdir()
    (interfaces / "original.py").write_text("original", encoding="utf-8")
    (interfaces / "self").symlink_to(interfaces, target_is_directory=True)
    before = snapshot(rp.RPP_HOME)

    def generate(*args, **kwargs):
        (interfaces / "original.py").write_text("changed", encoding="utf-8")
        (interfaces / "partial.py").write_text("partial", encoding="utf-8")

    monkeypatch.setattr(registry, "register_plugin_type_from_source", generate)
    monkeypatch.setattr(registry, "refresh_plugin_library", Mock(side_effect=failure))

    restore = Mock(wraps=migration._restore_registry)
    monkeypatch.setattr(migration, "_restore_registry", restore)
    with pytest.raises(type(failure)) as caught:
        migration.migrate_registry(
            registry, progress=lambda _: None, restore_on_error=restore_on_error)

    assert caught.value is failure
    if restore_on_error:
        restore.assert_called_once()
        assert snapshot(rp.RPP_HOME) == before
    else:
        restore.assert_not_called()
        assert (interfaces / "original.py").read_text(encoding="utf-8") == "changed"
        assert (interfaces / "partial.py").is_file()
    backups = list(rp.RPP_HOME.parent.glob("home-before-migration-*/home"))
    assert len(backups) == 1
    assert snapshot(backups[0]) == before


@pytest.mark.parametrize("restore_on_error", [True, False])
def test_success_regenerates_native_then_refreshes_users_and_keeps_backup(
        registry, monkeypatch, restore_on_error):
    add_library(registry, "Consumer", ["rpp_common"])
    before = snapshot(rp.RPP_HOME)
    operations = []
    monkeypatch.setattr(registry, "register_plugin_type_from_source",
                        lambda source, name, **kwargs: operations.append(name))
    refresh = registry.refresh_plugin_library

    def record_refresh(name):
        operations.append(name)
        refresh(name)

    monkeypatch.setattr(registry, "refresh_plugin_library", record_refresh)
    backup = migration.migrate_registry(
        registry, progress=lambda _: None, restore_on_error=restore_on_error)

    assert operations == ["rpp_common", "Consumer"]
    assert snapshot(backup) == before
    for name in operations:
        assert registry.load_lib_manifest(name)[rp.LIBRARY_REGISTRATOR_VERSION_KEY] == (
            migration.current_registrator_version())


def test_missing_source_is_rejected_before_regeneration(registry):
    library = add_library(registry, "Consumer")
    (Path(library.path) / "plugins.json").write_text(json.dumps({
        "Plugins": [{"Path": "missing.py"}],
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="Missing or unsupported registration source"):
        migration.plan_registry_migration(registry)
