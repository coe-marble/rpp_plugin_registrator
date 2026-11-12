import tempfile
from pathlib import Path

import pytest

from rpp_plugin_registrator.plugin_registrator import cpp_helpers
from rpp_plugin_registrator.plugin_registrator.cpp_helpers import (
    _get_exported_library_flags,
    _is_linkable_library,
    parse_version,
)


class TestLinkableLibrary:
    def test_header_only_package_is_not_linked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            assert not (_is_linkable_library(Path(temporary_directory), "header_only"))

    def test_shared_library_is_linked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            library_directory = Path(temporary_directory)
            (library_directory / "librpp_test.so").touch()

            assert _is_linkable_library(library_directory, "rpp_test")

    def test_exported_ament_library_is_linked_by_exact_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            package_prefix = Path(temporary_directory)
            cmake_directory = package_prefix / "share" / "test_package" / "cmake"
            cmake_directory.mkdir(parents=True)
            library_directory = package_prefix / "lib"
            library_directory.mkdir()
            (library_directory / "libtest_core.so").touch()
            (cmake_directory / "export_test_packageExport-noconfig.cmake").write_text(
                'IMPORTED_LOCATION_NOCONFIG "${_IMPORT_PREFIX}/lib/libtest_core.so"\n',
                encoding="utf-8",
            )

            library_dirs, libraries = _get_exported_library_flags(
                package_prefix, "test_package")

            assert library_dirs == [str(library_directory)]
            assert libraries == [":libtest_core.so"]


class TestVersionCheck:
    def test_two_part_version_is_x_y_0(self) -> None:
        assert parse_version("1.3") == (1, 3, 0)
        assert parse_version("1.3.1") == (1, 3, 1)
        assert parse_version(None) == (0, 0, 0)

    @pytest.mark.parametrize("version", ["1", "1.3.1.1", "1.3-rc1", "a.b", "1..2"])
    def test_malformed_version_names_the_value(self, version) -> None:
        with pytest.raises(ValueError, match=f"Invalid version '{version}'"):
            parse_version(version)

    @pytest.mark.parametrize("registered, requirement, satisfied", [
        ("1.3", ">=1.3", True),
        ("1.3", ">=1.3.1", False),
        ("1.3.1", ">=1.3", True),
        ("1.3", "==1.3.0", True),
        ("1.2", ">=1.3", False),
    ])
    def test_dependency_version_check_accepts_two_part_versions(
            self, monkeypatch, registered, requirement, satisfied) -> None:
        class Manager:
            def get_library_info(self, name):
                return {"Dependencies": [f"zlib_lib{requirement}"]}

            def get_library_path(self, name):
                return "/unused"

            def list_plugin_libraries(self):
                return [{"Name": "zlib_lib", "Version": registered}]

        monkeypatch.setattr(cpp_helpers, "get_library_manager", Manager)
        monkeypatch.setattr(cpp_helpers, "get_setting", lambda name: False)
        monkeypatch.setattr(cpp_helpers, "get_rpp_cpp_shared_libraries",
                            lambda: ("/core", ["rpp_cpp"]))

        if satisfied:
            cpp_helpers.get_cpp_imports_and_libraries_for_library("user")
        else:
            with pytest.raises(ValueError, match="does not satisfy"):
                cpp_helpers.get_cpp_imports_and_libraries_for_library("user")
