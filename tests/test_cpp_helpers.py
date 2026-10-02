import tempfile
import unittest
from pathlib import Path

from rpp_plugin_registrator.plugin_registrator.cpp_helpers import (
    _get_exported_library_flags,
    _is_linkable_library,
)


class LinkableLibraryTests(unittest.TestCase):
    def test_header_only_package_is_not_linked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            self.assertFalse(
                _is_linkable_library(Path(temporary_directory), "header_only"))

    def test_shared_library_is_linked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            library_directory = Path(temporary_directory)
            (library_directory / "librpp_test.so").touch()

            self.assertTrue(_is_linkable_library(library_directory, "rpp_test"))

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

            self.assertEqual(library_dirs, [str(library_directory)])
            self.assertEqual(libraries, [":libtest_core.so"])
