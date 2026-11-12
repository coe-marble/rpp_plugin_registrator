import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from rpp_plugin_registrator.plugin_registrator import cpp


@pytest.mark.parametrize("profile,flags", [
    ("Debug", {"-O0", "-g"}),
    ("Release", {"-O2", "-DNDEBUG"}),
    ("RelWithDebInfo", {"-O2", "-g", "-DNDEBUG"}),
])
def test_compiler_flags_and_profile_marker(monkeypatch, tmp_path, profile, flags):
    # Inspect the command without invoking a compiler.
    monkeypatch.setattr(cpp.sys, "platform", "linux")
    run = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(cpp.subprocess, "run", run)
    error, command, output = cpp._compile_rpp_file(
        ["example.cpp"], tmp_path, [], [], "Example", build_type=profile)
    assert error is None
    assert flags <= set(command)
    assert output == tmp_path / "Example.so"
    assert json.loads((tmp_path / "Example.build.json").read_text()) == {"build_type": profile}


@pytest.mark.parametrize("profile,expected_compiles", [
    ("RelWithDebInfo", []),
    ("Debug", []),
    ("Release", ["Release"]),
])
@pytest.mark.parametrize("per_plugin", [False, True])
def test_registration_reuses_symbol_rich_builds_and_recompiles_release(
        monkeypatch, tmp_path, profile, expected_compiles, per_plugin):
    default_profile = ("Debug" if profile != "Debug" else "Release") if per_plugin else profile
    monkeypatch.setattr(cpp, "get_setting", lambda name: default_profile)
    validation_profile = "RelWithDebInfo" if profile == "RelWithDebInfo" else "Debug"
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "Example.so").write_text("validation")
    (staged / "Example.build.json").write_text(json.dumps({"build_type": validation_profile}))
    registry = tmp_path / "registry"
    installed = registry / "plugins"
    installed.mkdir(parents=True)
    monkeypatch.setattr(cpp, "get_tmp_dir_for_compilation", lambda *args: staged)
    monkeypatch.setattr(cpp, "get_app_registry_path", lambda: registry)
    monkeypatch.setattr(cpp, "get_cpp_shared_libraries_path", lambda *args, **kwargs: installed)
    monkeypatch.setattr(cpp, "get_plugin_type_shared_library_path", lambda *args: "ExampleType.so")
    compiles = []

    def compile_plugin(**kwargs):
        compiles.append(kwargs["build_type"])
        (staged / "Example.so").write_text("optimized")
        return None, ["compiler"], staged / "Example.so"

    def metadata(path, class_name):
        assert Path(path).read_text() == "validation"
        assert compiles == []
        return {"Components": {}, "Parameters": {}}

    monkeypatch.setattr(cpp, "compile_cpp_plugin", compile_plugin)
    monkeypatch.setattr(cpp, "extract_plugin_metadata", metadata)
    info = SimpleNamespace(
        info={"SourceFile": "example.hpp", "ClassName": "Example", "Library": "examples"},
        build_type=profile if per_plugin else None,
        validation_data=SimpleNamespace(plugin_type_library="examples", plugin_type="examples::Type",
                                        plugin_type_class_name="Type"),
    )
    result = cpp.register_cpp_plugin(info)
    assert result.success
    assert result.register_data.as_dict()["BuildType"] == profile
    assert compiles == expected_compiles
    assert (installed / "Example.so").read_text() == (
        "optimized" if expected_compiles else "validation")


def test_directory_without_profile_is_not_reused(tmp_path):
    (tmp_path / "Example.so").write_text("old binary")
    assert not cpp._has_compiled_profile(tmp_path, "Example", "RelWithDebInfo")


@pytest.mark.parametrize("language", ["cpp", "python"])
def test_individual_registration_selects_mode_before_validation_and_remembers_it(tmp_path, language):
    from rpp_plugin_registrator.library_manager import LibraryManager
    from rpp_plugin_registrator.plugin_descriptors.core import PluginInfo

    manager = LibraryManager.__new__(LibraryManager)
    manager._parse_plugin_info_from_file = Mock(side_effect=lambda *args, **kwargs: PluginInfo(
        info={"ClassName": "Example", "SourceLanguage": language}))
    manager.load_lib_manifest = Mock(return_value={
        "Plugins": {"examples::Example": {"BuildType": "Debug"}}})
    manager._validate_plugin_info = Mock(side_effect=lambda info, *args, **kwargs: info)
    explicit = manager._prepare_plugin_registration(tmp_path / "example.hpp", "examples",
                                                    build_type="Release")
    assert explicit.build_type == "Release"
    manager.load_lib_manifest.assert_not_called()
    manager._validate_plugin_info.assert_called_with(explicit, "examples", persist_compiled_files=True)
    remembered = manager._prepare_plugin_registration(tmp_path / "example.hpp", "examples")
    assert remembered.build_type == "Debug"


@pytest.mark.parametrize("profile", ["Debug", "Release"])
def test_library_refresh_applies_one_build_type_to_all_plugins(monkeypatch, tmp_path, profile):
    import rpp_plugin_registrator.library_manager as library_manager

    (tmp_path / "plugins.json").write_text(json.dumps({
        "PluginTypes": [{"Path": "interfaces.capnp"}],
        "Plugins": [{"Path": "first.hpp"}, {"Path": "second.hpp"}]}))
    manager = library_manager.LibraryManager.__new__(library_manager.LibraryManager)
    manager.get_library_path = Mock(return_value=tmp_path)
    manager.is_valid_plugin_library = Mock(return_value=True)
    manager._prepare_plugin_registration = Mock()
    manager.register_plugin = Mock()
    manager.add_to_manifest = Mock()
    manager._record_completed_library_registration_version = Mock()
    manager._iter_registration_files = lambda path, entries, *args: (
        (path / entry["Path"], entry) for entry in entries)
    monkeypatch.setattr(library_manager, "compute_library_registration_status",
        lambda *args: SimpleNamespace(blocking_dependencies=[]))
    register_types = Mock(return_value=[])
    monkeypatch.setattr(library_manager.ptyp_reg_api, "register_plugin_type_from_source", register_types)
    manager.refresh_plugin_library("examples", build_type=profile)
    register_types.assert_called_once_with(
        tmp_path / "interfaces.capnp", "examples", override=True, build_type=profile)
    assert manager._prepare_plugin_registration.call_count == 2
    assert all(call.kwargs["build_type"] == profile
               for call in manager._prepare_plugin_registration.call_args_list)
    manager._record_completed_library_registration_version.reset_mock()
    manager._prepare_plugin_registration.side_effect = ValueError("compiler failed")
    with pytest.warns(UserWarning, match="compiler failed"):
        with pytest.raises(ValueError, match="compiler failed"):
            manager.refresh_plugin_library("examples", throw=True, build_type=profile)
    manager._record_completed_library_registration_version.assert_not_called()


@pytest.mark.parametrize("profile", ["Debug", "Release"])
def test_plugin_type_compilation_honors_explicit_build_type(monkeypatch, tmp_path, profile):
    from rpp_plugin_registrator.plugin_descriptors.core import PluginTypeInfo

    # The GUI selection must win over the CLI's RelWithDebInfo default.
    monkeypatch.setattr(cpp, "get_setting", lambda name: "RelWithDebInfo")
    monkeypatch.setattr(cpp, "get_app_interfaces_path", lambda: tmp_path)
    staged = tmp_path / "staged"
    installed = tmp_path / "installed"
    installed.mkdir()
    monkeypatch.setattr(cpp, "get_tmp_dir_for_compilation", lambda *args: staged)
    monkeypatch.setattr(cpp, "get_cpp_shared_libraries_path", lambda *args, **kwargs: installed)

    def compile_type(**kwargs):
        output = kwargs["out_dir"] / "Example.so"
        output.write_text("compiled interface")
        return None, [], output

    compile_type_mock = Mock(side_effect=compile_type)
    monkeypatch.setattr(cpp, "compile_cpp_plugin_type", compile_type_mock)
    cpp.generate_cpp_plugin_interface(PluginTypeInfo(
        info={"ClassName": "Example", "Library": "examples"}, build_type=profile))
    assert compile_type_mock.call_args.kwargs["build_type"] == profile
    assert (installed / "Example.so").is_file()


def test_metadata_failure_preserves_loader_diagnostics_from_gdb_stderr(monkeypatch, tmp_path):
    monkeypatch.setattr(cpp, "get_tmp_dir_for_compilation", lambda *args: tmp_path)
    monkeypatch.setattr(cpp, "get_setting", lambda name: None)
    monkeypatch.setattr(cpp, "_compile_rpp_file",
        Mock(return_value=(None, [], tmp_path / "dummy_Example.out")))
    diagnostic = "libexample.so: cannot open shared object file: No such file or directory"
    monkeypatch.setattr(cpp.subprocess, "run", Mock(return_value=SimpleNamespace(
        returncode=0,
        stdout=b"[ERROR DURING GDB ANALYSIS]: The dummy executable could not load the plugin shared library",
        stderr=diagnostic.encode(),
    )))
    with pytest.raises(RuntimeError, match="libexample.so: cannot open shared object file"):
        cpp.extract_plugin_metadata(tmp_path / "Example.so", "Example")


@pytest.mark.parametrize("returncode", [0, 1])
@pytest.mark.parametrize("log_level", [logging.INFO, logging.DEBUG])
def test_compiler_diagnostics_are_streamed_and_preserved_on_failure(
        monkeypatch, tmp_path, caplog, returncode, log_level):
    process = Mock(stdout=iter(["example.hpp: warning: diagnostic\n"]))
    process.wait.return_value = returncode
    context = MagicMock()
    context.__enter__.return_value = process
    popen = Mock(return_value=context)
    monkeypatch.setattr(cpp.subprocess, "Popen", popen)
    run = Mock(side_effect=AssertionError("Compilation should stream rather than capture output"))
    monkeypatch.setattr(cpp.subprocess, "run", run)
    # Capture directly so application/runner logging settings cannot disable
    # the package logger or prevent its records from reaching pytest's root handler.
    caplog.set_level(log_level)
    logger = logging.Logger("rpp_plugin_registrator.compiler_test", level=log_level)
    logger.propagate = False
    logger.addHandler(caplog.handler)
    monkeypatch.setattr(cpp, "logger", logger)
    error, _, _ = cpp._compile_rpp_file(["example.cpp"], tmp_path, [], [], "Example",
                                       build_type="Debug")
    assert ("Compiling Example (Debug)" in caplog.text) is (log_level == logging.DEBUG)
    assert ("Compiled Example (Debug)" in caplog.text) is (
        log_level == logging.DEBUG and returncode == 0)
    assert ("example.hpp: warning: diagnostic" in caplog.text) is (log_level == logging.DEBUG)
    assert ("Command:" in caplog.text) is (log_level == logging.DEBUG)
    assert (tmp_path / "Example.build.json").exists() is (returncode == 0)
    if returncode:
        assert "example.hpp: warning: diagnostic" in error
    else:
        assert error is None
    run.assert_not_called()
