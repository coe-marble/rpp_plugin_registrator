"""A bare library name refers to the registered library, not to a folder of that name."""

import json
import shutil
from pathlib import Path
from unittest.mock import Mock

import pytest

from rpp_plugin_registrator import library_manager as libraries
from rpp_plugin_registrator import registry_config as rp


@pytest.fixture
def registry(tmp_path, monkeypatch):
    home = tmp_path / "rpp-home"
    (home / "libraries").mkdir(parents=True)
    monkeypatch.setattr(rp, "RPP_HOME", home)
    monkeypatch.setattr(rp, "load_and_set_config", Mock())
    manager = libraries.LibraryManager(rpp_home=home, skip_layout_check=True)
    registered = Path(manager.get_or_create_plugin_library("TestLib").path)
    # A second valid library of the same name in the current folder.
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    local = workdir / "TestLib"
    shutil.copytree(registered, local)
    package = json.loads((local / "package.json").read_text(encoding="utf-8"))
    package["Marker"] = "local-folder"
    (local / "package.json").write_text(json.dumps(package), encoding="utf-8")
    monkeypatch.chdir(workdir)
    return manager, registered, local


class TestLibraryNameResolution:
    def test_bare_name_resolves_to_registered_library(self, registry) -> None:
        manager, registered, _ = registry

        assert Path(manager.get_library_path("TestLib")) == registered
        assert "Marker" not in manager.get_library_info("TestLib")

    @pytest.mark.parametrize("explicit", ["./TestLib", "absolute", "../workdir/TestLib"])
    def test_explicit_path_resolves_as_path(self, registry, explicit) -> None:
        manager, _, local = registry
        if explicit == "absolute":
            explicit = str(local)

        assert Path(manager.get_library_path(explicit)) == local.resolve()
        assert manager.get_library_info(explicit)["Marker"] == "local-folder"

    def test_unregistered_bare_name_falls_back_to_folder(self, registry) -> None:
        manager, _, local = registry
        shutil.copytree(local, local.parent / "OtherLib")

        assert Path(manager.get_library_path("OtherLib")) == (local.parent / "OtherLib").resolve()
