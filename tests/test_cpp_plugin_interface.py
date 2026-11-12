from pathlib import Path
from types import SimpleNamespace

import pytest

from rpp_plugin_registrator.plugin_registrator import cpp


@pytest.fixture
def interface_paths(tmp_path, monkeypatch):
    tmp_out_dir = tmp_path / "interfaces" / "tmp_Probe"
    shared_libraries = tmp_path / "shared_libraries"
    shared_libraries.mkdir()
    monkeypatch.setattr(cpp, "get_app_interfaces_path", lambda: tmp_path / "interfaces")
    monkeypatch.setattr(
        cpp, "get_tmp_dir_for_compilation", lambda source_file, class_name: tmp_out_dir)
    monkeypatch.setattr(
        cpp, "get_cpp_shared_libraries_path", lambda library, is_plugin: shared_libraries)
    return tmp_out_dir, shared_libraries


def _plugin_type_info():
    return SimpleNamespace(info={"ClassName": "Probe", "Library": "demo"})


def _successful_compile(source_file, plugin_type_info, out_dir, suppress_warnings):
    (Path(out_dir) / "Probe.so").write_text("compiled", encoding="utf-8")
    return None, "compile command", None


class TestGenerateCppPluginInterface:
    def test_leftover_compile_folder_is_rebuilt(self, interface_paths, monkeypatch) -> None:
        tmp_out_dir, shared_libraries = interface_paths
        tmp_out_dir.mkdir(parents=True)
        (tmp_out_dir / "stale.o").touch()
        monkeypatch.setattr(cpp, "compile_cpp_plugin_type", _successful_compile)

        cpp.generate_cpp_plugin_interface(_plugin_type_info())

        assert (shared_libraries / "Probe.so").read_text(encoding="utf-8") == "compiled"
        assert not tmp_out_dir.exists()

    def test_failed_compile_removes_the_compile_folder(
            self, interface_paths, monkeypatch) -> None:
        tmp_out_dir, shared_libraries = interface_paths
        monkeypatch.setattr(
            cpp, "compile_cpp_plugin_type",
            lambda **arguments: ("compiler error", "compile command", None))

        with pytest.raises(RuntimeError, match="Failed to compile C\\+\\+ plugin 'Probe'"):
            cpp.generate_cpp_plugin_interface(_plugin_type_info())

        assert not tmp_out_dir.exists()
        assert not (shared_libraries / "Probe.so").exists()

    def test_missing_shared_library_does_not_leave_the_folder(
            self, interface_paths, monkeypatch) -> None:
        tmp_out_dir, _ = interface_paths
        monkeypatch.setattr(
            cpp, "compile_cpp_plugin_type",
            lambda **arguments: (None, "compile command", None))

        with pytest.raises(FileNotFoundError):
            cpp.generate_cpp_plugin_interface(_plugin_type_info())

        assert not tmp_out_dir.exists()
