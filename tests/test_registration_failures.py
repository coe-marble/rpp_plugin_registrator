"""Registry consistency when backends or metadata writes fail.

Compiler and generator boundaries are mocked; registry files use a temporary home.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rpp_plugin_registrator import library_manager as libraries
from rpp_plugin_registrator import registry_config as rp
from rpp_plugin_registrator.plugin_registrator import dispatch
from rpp_plugin_registrator.plugin_descriptors.core import (
    PluginInfo,
    PluginRegisterData,
    PluginRegistrationResult,
    PluginValidationData,
    PluginValidationResult,
)


def files_under(root):
    """Capture both file contents and the absence of new registry records."""
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


@pytest.fixture
def registry(tmp_path, monkeypatch):
    home = tmp_path / "rpp-home"
    (home / "libraries").mkdir(parents=True)
    monkeypatch.setattr(rp, "RPP_HOME", home)
    # These tests do not initialize common schemas or depend on user settings.
    monkeypatch.setattr(rp, "load_and_set_config", Mock())
    manager = libraries.LibraryManager(rpp_home=home, skip_layout_check=True)
    library = Path(manager.get_or_create_plugin_library("TestLib").path)
    source = library / "plugins" / "controller.py"
    source.parent.mkdir()
    source.write_text("class Controller:\n    pass\n", encoding="utf-8")
    plugin = PluginInfo(
        info={"Name": "Controller", "ClassName": "Controller",
              "SourceLanguage": "python", "SourceFile": str(source)},
        validation_data=PluginValidationData(
            plugin_type="Types::Controller", plugin_type_class_name="Controller",
            plugin_type_source_file="plugin_types/controller.capnp",
            plugin_type_library="Types", fully_qualified_plugin_class_name="Controller",
            fully_qualified_class_name="Controller", class_name="Controller",
        ),
    )
    backend = Mock(return_value=PluginRegistrationResult(
        success=True, register_data=PluginRegisterData(
            plugin_shared_library_path=None, plugin_type_shared_library_path=None,
            plugin_metadata={"Parameters": {}, "Components": {}},
        ),
    ))
    monkeypatch.setattr(libraries.p_reg_api, "register_plugin", backend)
    return SimpleNamespace(home=home, manager=manager, library=library,
                           plugin=plugin, backend=backend, source=source)


def test_backend_exception_leaves_registry_and_library_unchanged(registry):
    failure = RuntimeError("compiler failed")
    registry.backend.side_effect = failure
    before = files_under(registry.home)

    with pytest.raises(RuntimeError) as caught:
        registry.manager.register_plugin(registry.plugin, "TestLib")

    assert caught.value is failure
    assert files_under(registry.home) == before


def test_unsuccessful_backend_result_reports_registration_error(registry):
    registry.backend.return_value = PluginRegistrationResult(
        success=False, message="compiler failed")
    before = files_under(registry.home)

    with pytest.raises(ValueError, match="Failed to register plugin.*compiler failed"):
        registry.manager.register_plugin(registry.plugin, "TestLib")

    assert files_under(registry.home) == before


@pytest.mark.parametrize("language", ["python", "cpp"])
def test_dispatch_preserves_backend_failure_without_resolving_shared_library(
        registry, monkeypatch, language):
    failure = PluginRegistrationResult(success=False, message="class missing")
    registry.plugin.info["SourceLanguage"] = language
    monkeypatch.setattr(dispatch, f"register_{language}_plugin", Mock(return_value=failure))
    resolve_library = Mock()
    monkeypatch.setattr(dispatch, "get_plugin_type_shared_library_path", resolve_library)

    result = dispatch.register_plugin(registry.plugin)

    assert result is failure
    resolve_library.assert_not_called()


@pytest.mark.parametrize("replacement", [False, True], ids=["new", "replacement"])
@pytest.mark.parametrize("target", ["plugins", "descriptor", "manifest"])
@pytest.mark.filterwarnings("ignore:Plugin .* already exists")
def test_failed_metadata_write_restores_previous_registration(
        registry, monkeypatch, replacement, target):
    if replacement:
        registry.manager.register_plugin(registry.plugin, "TestLib")
    before = files_under(registry.home)
    registry.plugin.info["Description"] = "replacement description"
    fail_path = {
        "plugins": registry.library / "plugins.json",
        "descriptor": rp.get_app_registry_plugin_json_path("TestLib::Controller"),
        "manifest": rp.get_app_library_manifest_path_json("TestLib"),
    }[target]
    failure = PermissionError(f"Cannot write {target}")
    write_json = libraries.write_json

    def fail_one_write(path, *args, **kwargs):
        if Path(path) == fail_path:
            # Simulate a writer that truncates the file before reporting an error.
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text('{"partial":', encoding="utf-8")
            raise failure
        return write_json(path, *args, **kwargs)

    monkeypatch.setattr(libraries, "write_json", fail_one_write)

    with pytest.raises(PermissionError) as caught:
        registry.manager.register_plugin(registry.plugin, "TestLib")

    assert caught.value is failure
    assert files_under(registry.home) == before


@pytest.mark.parametrize("link", [False, True], ids=["copied", "linked"])
def test_failed_library_refresh_removes_partial_registration(registry, tmp_path, monkeypatch, link):
    external = tmp_path / "external" / "NewLibrary"
    external.mkdir(parents=True)
    (external / "package.json").write_text(
        '{"Library": "NewLibrary", "Version": "1.0.0"}\n', encoding="utf-8")
    (external / "plugins.json").write_text(
        '{"Plugins": [], "PluginTypes": []}\n', encoding="utf-8")
    source = external / "plugins" / "source.py"
    source.parent.mkdir()
    source.write_text("# Original plugin source\n", encoding="utf-8")
    before = files_under(registry.home)
    original_source = source.read_bytes()
    failure = RuntimeError("plugin type generation failed")
    def partial_refresh(_library_name, *, build_type=None):
        libraries.write_json(rp.get_app_registry_json_path(), {
            "PluginTypes": {"NewLibrary::PartialType": {"Library": "NewLibrary"}},
        })
        libraries.write_json(rp.get_app_registry_plugin_type_json_path(
            "NewLibrary::PartialType"), {"ClassName": "PartialType"})
        raise failure

    monkeypatch.setattr(registry.manager, "refresh_plugin_library", partial_refresh)

    with pytest.raises(RuntimeError) as caught:
        registry.manager.register_plugin_library(external, link_register=link)

    assert caught.value is failure
    assert source.read_bytes() == original_source
    assert files_under(registry.home) == before


@pytest.mark.parametrize("link", [False, True], ids=["copied", "linked"])
def test_library_setup_failure_preserves_existing_metadata(
        registry, tmp_path, monkeypatch, link):
    external = tmp_path / "external" / "NewLibrary"
    external.mkdir(parents=True)
    (external / "package.json").write_text(
        '{"Library": "NewLibrary", "Version": "1.0.0"}\n', encoding="utf-8")
    (external / "plugins.json").write_text(
        '{"Plugins": [], "PluginTypes": []}\n', encoding="utf-8")
    libraries.write_json(rp.get_app_registry_json_path(), {
        "PluginTypes": {"Existing::Type": {"Library": "Existing"}},
    })
    # Include an existing manifest to ensure rollback restores rather than deletes it.
    manifest = rp.get_app_library_manifest_path_json("NewLibrary")
    libraries.write_json(manifest, {"Library": "NewLibrary", "Description": "original"})
    before = files_under(registry.home)
    failure = PermissionError("library setup failed")
    ensure_structure = registry.manager.ensure_library_structure

    def fail_setup(path, name):
        ensure_structure(path, name)
        libraries.write_json(manifest, {"Library": name, "Description": "partial"})
        raise failure

    monkeypatch.setattr(registry.manager, "ensure_library_structure", fail_setup)

    with pytest.raises(PermissionError) as caught:
        registry.manager.register_plugin_library(external, link_register=link)

    assert caught.value is failure
    assert files_under(registry.home) == before


@pytest.mark.parametrize("link", [False, True], ids=["copied", "linked"])
def test_successful_library_registration_keeps_manifest_and_source(registry, tmp_path, link):
    external = tmp_path / "external" / "NewLibrary"
    external.mkdir(parents=True)
    (external / "package.json").write_text(
        '{"Library": "NewLibrary", "Version": "1.0.0"}\n', encoding="utf-8")
    (external / "plugins.json").write_text(
        '{"Plugins": [], "PluginTypes": []}\n', encoding="utf-8")

    registered_path = Path(registry.manager.register_plugin_library(external, link_register=link))

    assert registered_path == (external if link else rp.get_app_libraries_path() / "NewLibrary")
    assert Path(registry.manager.get_library_path("NewLibrary")) == registered_path
    assert rp.get_app_library_manifest_path_json("NewLibrary").is_file()
    assert (external / "plugins.json").is_file()


@pytest.mark.parametrize("returns_false", [False, True], ids=["exception", "failure-result"])
def test_failed_unregistration_keeps_existing_registration(registry, monkeypatch, returns_false):
    registry.manager.register_plugin(registry.plugin, "TestLib")
    before = files_under(registry.home)
    backend = Mock(return_value=False) if returns_false else Mock(
        side_effect=RuntimeError("unregistration failed"))
    monkeypatch.setattr(libraries.p_reg_api, "unregister_plugin", backend)

    with pytest.raises(ValueError if returns_false else RuntimeError):
        registry.manager.unregister_plugin("TestLib::Controller")

    assert files_under(registry.home) == before


def test_validation_rejection_does_not_reach_backend_or_change_files(registry, monkeypatch):
    monkeypatch.setattr(libraries, "parse_plugin_file", Mock(return_value=SimpleNamespace(
        is_valid=True, data=SimpleNamespace(plugins=[registry.plugin.info]),
    )))
    monkeypatch.setattr(libraries.ptyp_reg_api, "get_plugin_types", Mock(return_value={}))
    monkeypatch.setattr(libraries, "validate_plugin", Mock(return_value=PluginValidationResult(
        is_valid=False, message="Unknown plugin type",
    )))
    before = files_under(registry.home)

    with pytest.raises(ValueError, match="Unknown plugin type"):
        registry.manager.register_plugin_from_source(registry.source, "TestLib")

    registry.backend.assert_not_called()
    assert files_under(registry.home) == before
