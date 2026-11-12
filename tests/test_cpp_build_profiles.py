import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

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
def test_registration_reuses_symbol_rich_builds_and_recompiles_release(
        monkeypatch, tmp_path, profile, expected_compiles):
    monkeypatch.setattr(cpp, "get_setting", lambda name: profile)
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
        validation_data=SimpleNamespace(plugin_type_library="examples", plugin_type="examples::Type",
                                        plugin_type_class_name="Type"),
    )
    result = cpp.register_cpp_plugin(info)
    assert result.success
    assert compiles == expected_compiles
    assert (installed / "Example.so").read_text() == (
        "optimized" if expected_compiles else "validation")


def test_directory_without_profile_is_not_reused(tmp_path):
    (tmp_path / "Example.so").write_text("old binary")
    assert not cpp._has_compiled_profile(tmp_path, "Example", "RelWithDebInfo")


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
