import json
from re import sub
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
import subprocess
import pytest

from rpp_plugin_registrator.library_manager import LibraryManager
from rpp_plugin_registrator.plugin_registrator.cpp import get_tmp_dir_for_compilation
import rpp_plugin_registrator.plugin_type_registrator as registry_api
from rpp_plugin_registrator import registry_config as rp


def write_config(home: Path, orig_cfg: dict):
    new_config_path = home / "config.json"
    with open(new_config_path, "w", encoding="utf-8") as f:
        json.dump(orig_cfg, f, indent=4)

class TestPluginTypeRegistrator:
    TEST_LIBRARY = "testlib"

    @pytest.fixture(autouse=True)
    def _plugin_type_registry(self, monkeypatch):
        import rpp_plugin_registrator.plugin_descriptors.capnp
        monkeypatch.setattr(
            rpp_plugin_registrator.plugin_descriptors.capnp,
            "PLUGIN_ANNOTATION_ID",
            "0xabcd000000000000",
        )
        import rpp_plugin_registrator.plugin_type_registrator
        monkeypatch.setattr(
            rpp_plugin_registrator.plugin_type_registrator,
            "SCAFFOLD_LANGUAGES",
            [],
        )
        yield
        rpp_plugin_registrator.plugin_type_registrator.reset_module()
        self._clear_capnproto_cache()


    @contextmanager
    def _temp_rpp_home(self, home: Path):
        original_home = rp.RPP_HOME
        rp.RPP_HOME = home
        rp.RPP_HOME.mkdir(parents=True, exist_ok=True)
        try:
            yield rp.RPP_HOME
        finally:
            rp.RPP_HOME = original_home


    def _clear_capnproto_cache(self):
        import capnp
        capnp.cleanup_global_schema_parser()

    def _write_description(
        self,
        path: Path,
        plugin_id: str,
        class_name: str = "TestPlugin",
        name: str = "test",
        library: str | None = None,
    ) -> None:
        payload = {
            "Plugin": {
                "Id": plugin_id,
                "Name": name,
                "SourceLanguage": "python",
                "ClassName": class_name,
                "Library": library or self.TEST_LIBRARY,
                "RppRegistration": {
                    "Factory": {
                        "CreateSymbol": "create_plugin",
                        "Signature": "void* create_plugin()",
                    }
                },
            }
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")


    def _write_capnp_anot_source(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            """
@0xaaaa000000000000;
annotation plugin @0xabcd000000000000(interface) :Text;
"""
        )


    def _write_capnp_plugin_source(self, path: Path, class_name: str, tag: str,
                                   plugin_name: str, anot_library_name=None, id=1) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if anot_library_name is None:
            anot_library_name = "rpp_common"
        path.write_text(
            (f"""
@0xaaaaaaaa0000000{id};
using Anot = import "{anot_library_name}/anot.capnp";

interface {class_name} $Anot.plugin("{plugin_name}"){{
  {tag}   @0 () -> ();
}}

""".strip()
            ),
            encoding="utf-8",
        )

    def create_test_library(self, test_home: Path):
        lm = LibraryManager(test_home, init_anot_only=True)
        lm.get_or_create_plugin_library("testlib")

    def test_resolve_registry_path_uses_rpp_home_when_no_explicit_path(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / ".rpp"
            with self._temp_rpp_home(home):
                resolved = rp.get_app_registry_json_path()
                assert resolved == (home / "registry" / "rpp_plugin_types.json").resolve()

    def test_load_registry_returns_default_payload_when_missing(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / ".rpp"
            with self._temp_rpp_home(home):
                payload = registry_api.load_registry()
                assert payload == registry_api.default_registry_payload()

    def test_ensure_rpp_layout_creates_expected_directories(self):
        with tempfile.TemporaryDirectory() as td:
            common_plugins_dir = Path(td) / "empty_common_plugins"
            common_plugins_dir.mkdir(parents=True, exist_ok=True)
            with self._temp_rpp_home(Path(td) / ".rpp"):
                registry_api.ensure_rpp_layout(common_plugins_dir=common_plugins_dir)
                paths = registry_api.get_rpp_paths()
                assert paths["home"].exists()
                assert paths["descriptions"].exists()
                assert paths["interfaces"].exists()
                assert paths["registry"].parent.exists()
                assert (paths["home"] / registry_api.rp.INITIALIZED_MARKER_FILENAME).exists()

    def test_ensure_rpp_layout_initializes_common_plugins_and_writes_marker(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            common_plugins_dir = temp_root / "common_plugins"
            self._write_capnp_anot_source(common_plugins_dir / "anot.capnp")
            self._write_capnp_plugin_source(common_plugins_dir / "Controller.capnp", "Controller", "ctl", "controller", anot_library_name="common_plugins", id="1")
            self._write_capnp_plugin_source(
                common_plugins_dir / "Estimator.capnp", "Estimator", "est", "estimator",
                anot_library_name="common_plugins", id="2") # Avoid duplicate annotation ID conflict for test

            with self._temp_rpp_home(temp_root / ".rpp"):
                paths = registry_api.get_rpp_paths()
                registry_api.ensure_rpp_layout(common_plugins_dir=common_plugins_dir)

                marker_path = paths["home"] / registry_api.rp.INITIALIZED_MARKER_FILENAME
                assert marker_path.exists()
                marker_payload = json.loads(marker_path.read_text(encoding="utf-8"))
                assert marker_payload["Initialized"]
                assert set(marker_payload["InitializedPlugins"]) == {"common_plugins::Controller", "common_plugins::Estimator"}

                registry_payload = registry_api.load_registry()
                assert "common_plugins::Controller" in registry_payload["PluginTypes"]
                assert "common_plugins::Estimator" in registry_payload["PluginTypes"]
                assert registry_payload["PluginTypes"]["common_plugins::Controller"]["Library"] == "common_plugins"
                assert registry_payload["PluginTypes"]["common_plugins::Estimator"]["Library"] == "common_plugins"

                rpp_library_path = paths["libraries"] / "common_plugins"
                assert (rpp_library_path / "package.json").exists()
                assert (rpp_library_path / "plugins.json").exists()

                manifest_path = rp.get_app_library_manifest_path_json("common_plugins")
                assert manifest_path.exists()
                manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                assert manifest_payload["Library"] == "common_plugins"

                registry_api.ensure_rpp_layout(common_plugins_dir=common_plugins_dir)
                registry_payload_second = registry_api.load_registry()
                assert sorted(registry_payload_second["PluginTypes"].keys()) == sorted(registry_payload["PluginTypes"].keys())

    def test_ensure_rpp_layout_override_reinitializes_when_marker_exists(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            common_plugins_dir = temp_root / "common_plugins"
            self._write_capnp_plugin_source(common_plugins_dir / "Controller.capnp",
                    "Controller", "ctl", "controller", anot_library_name="common_plugins", id="3")
            self._write_capnp_anot_source(common_plugins_dir / "anot.capnp")

            with self._temp_rpp_home(temp_root / ".rpp"):
                registry_api.ensure_rpp_layout(common_plugins_dir=common_plugins_dir)
                paths = registry_api.get_rpp_paths()

                registry_payload = registry_api.load_registry()
                assert "common_plugins::Controller" in registry_payload["PluginTypes"]

                del registry_payload["PluginTypes"]["common_plugins::Controller"]
                registry_api.write_json(rp.get_app_registry_json_path(), registry_payload)

                registry_api.ensure_rpp_layout(
                    common_plugins_dir=common_plugins_dir,
                    override_initialization=True,
                )
                registry_payload_after_override = registry_api.load_registry()
                assert "common_plugins::Controller" in registry_payload_after_override["PluginTypes"]
                manifest_path = rp.get_app_library_manifest_path_json("common_plugins")
                assert manifest_path.exists()

    def test_resolve_output_path_uses_override_or_default(self):
        with tempfile.TemporaryDirectory() as td:
            default_path = Path(td) / "default.json"
            explicit = Path(td) / "explicit.json"
            assert rp.resolve_output_path(str(explicit), default_path) == explicit.resolve()
            assert rp.resolve_output_path(None, default_path) == default_path.resolve()

    def test_get_plugin_types(self):
        with tempfile.TemporaryDirectory() as td:
            with self._temp_rpp_home(Path(td) / ".rpp"):
                registry_path = rp.get_app_registry_json_path()
                registry_path.parent.mkdir(parents=True, exist_ok=True)
                registry_path.write_text(
                    json.dumps(
                        {
                            "SchemaVersion": 1,
                            "System": "rpp",
                            "PluginTypes": {
                                "ctl": {"ClassName": "Controller"},
                                "est": {"ClassName": "Estimator"},
                                "other": {"ClassName": "Controller"},
                            },
                        }
                    ),
                    encoding="utf-8",
                )

                types = registry_api.get_plugin_types()
                class_names = [entry["ClassName"] for entry in types.values()]

            assert class_names == ["Controller", "Estimator", "Controller"]

    def test_register_plugin_type_persists_plugin_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            with self._temp_rpp_home(Path(td) / ".rpp"):
                temp_root = Path(td)
                source_path = temp_root / "plugins" / "EchoPlugin.capnp"
                registry_path = rp.get_app_registry_json_path()

                self._write_capnp_plugin_source(
                    path=source_path,
                    class_name="EchoPlugin",
                    tag="echo",
                    plugin_name="echo",
                )

                self.create_test_library(temp_root / ".rpp")


                entries = registry_api.register_plugin_type_from_source(
                    source_path,
                    library=self.TEST_LIBRARY,
                )
                entry = entries[0] if isinstance(entries, list) else entries
                payload = json.loads(registry_path.read_text(encoding="utf-8"))
                # Entry should be in the registry
                assert entry["SourceFile"] == str(source_path.resolve())
                assert entry["ClassName"] == "EchoPlugin"
                assert entry["RegistryPluginTypeFileId"] != None
                assert entry["RegistryPluginTypeFile"] != None

                interfaces_path = rp.get_app_capnp_interfaces_path()
                lib_interfaces_path = Path(interfaces_path) / self.TEST_LIBRARY
                registered_capnp_file_exists = (lib_interfaces_path / source_path.name).exists()

                assert registered_capnp_file_exists
                assert entry["Library"] == self.TEST_LIBRARY


                # Verify it's persisted in registry under the correct ID
                plugin_types = payload["PluginTypes"]
                assert any(pt["ClassName"] == "EchoPlugin" for pt in plugin_types.values())

    def test_register_plugin_type_from_source_registers_plugin(self):
        with tempfile.TemporaryDirectory() as td:
            with self._temp_rpp_home(Path(td) / ".rpp"):
                temp_root = Path(td)
                source_path = temp_root / "plugins" / "EchoPlugin.capnp"
                registry_path = rp.get_app_registry_json_path()

                self._write_capnp_plugin_source(
                    path=source_path,
                    class_name="EchoPlugin",
                    tag="echo",
                    plugin_name="echo",
                )

                self.create_test_library(temp_root / ".rpp")

                entries = registry_api.register_plugin_type_from_source(
                    source_path,
                    library=self.TEST_LIBRARY,
                )
                entry = entries[0] if isinstance(entries, list) else entries

                assert entry["SourceFile"] == str(source_path.resolve())
                assert entry["RegistryPluginTypeFile"] == str((rp.get_app_capnp_interfaces_path() / self.TEST_LIBRARY / source_path.name).resolve())
                assert entry["Library"] == self.TEST_LIBRARY
                assert entry["ClassName"] == "EchoPlugin"
                assert entry["PluginTypeName"] == f"{self.TEST_LIBRARY}::EchoPlugin"
                fully_qualified_class_name = f"<class 'rpp_plugin_types.{self.TEST_LIBRARY}.EchoPlugin.EchoPlugin'>"
                assert entry["FullyQualifiedClassName"] == fully_qualified_class_name
                payload = json.loads(registry_path.read_text(encoding="utf-8"))
                # Verify entry is in registry
                plugin_types = payload["PluginTypes"]
                assert any(pt["ClassName"] == "EchoPlugin" for pt in plugin_types.values())

                path = rp.get_app_registry_plugin_type_json_path(entry["PluginTypeName"])
                assert path.exists()

                interfaces_path = rp.get_app_capnp_interfaces_path()
                lib_interfaces_path = Path(interfaces_path) / self.TEST_LIBRARY
                registered_capnp_file_exists = (lib_interfaces_path / source_path.name).exists()
                assert registered_capnp_file_exists
                assert entry["Library"] == self.TEST_LIBRARY

    def test_register_plugin_type_from_invalid_source(self):

        with tempfile.TemporaryDirectory() as td:
            with self._temp_rpp_home(Path(td) / ".rpp"):
                temp_root = Path(td)
                source_path = temp_root / "plugins" / "InvalidPlugin.capnp"

                source_path.parent.mkdir(parents=True, exist_ok=True)
                source_path.write_text(
                    """
@0xaaaaaaaa00000001;
interface12 InvalidPlugin {
  invalidField @0 () -> ();
}
""".strip(),
                    encoding="utf-8",
                )

                self.create_test_library(temp_root / ".rpp")

                with pytest.raises(ValueError) as context:
                    registry_api.register_plugin_type_from_source(
                        source_path,
                        library=self.TEST_LIBRARY)

                assert "Failed to parse plugin type file" in str(context.value)




    def test_register_plugin_type_library_does_not_exist_raises(self):
        with tempfile.TemporaryDirectory() as td:
            with self._temp_rpp_home(Path(td) / ".rpp"):
                temp_root = Path(td)
                source_path = temp_root / "plugins" / "EchoPlugin.capnp"

                self._write_capnp_plugin_source(
                    path=source_path,
                    class_name="EchoPlugin",
                    tag="echo",
                    plugin_name="echo",
                )

                with pytest.raises(ValueError):
                    registry_api.register_plugin_type_from_source(
                        source_path,
                        library="nonexistent_library",
                    )

    def test_register_plugin_type_rejects_duplicate_class_name(self):
        with tempfile.TemporaryDirectory() as td:
            with self._temp_rpp_home(Path(td) / ".rpp"):
                temp_root = Path(td)
                registry_path = rp.get_app_registry_json_path()
                first_source = temp_root / "plugins" / "FirstPlugin.capnp"
                second_source = temp_root / "plugins" / "SecondPlugin.capnp"

                self._write_capnp_plugin_source(
                    first_source,
                    class_name="SharedClass",
                    tag="firsttag",
                    plugin_name="first",
                    id="1"
                )
                self._write_capnp_plugin_source(
                    second_source,
                    class_name="SharedClass",
                    tag="secondtag",
                    plugin_name="second",
                    id="2"
                )

                self.create_test_library(temp_root / ".rpp")

                # First plugin should register successfully
                registry_api.register_plugin_type_from_source(first_source, library=self.TEST_LIBRARY)

                # Second plugin with same class name should fail
                with pytest.raises(ValueError):
                    registry_api.register_plugin_type_from_source(second_source, library=self.TEST_LIBRARY)


    def test_register_plugin_type_with_depencency_from_different_library(self):

        with tempfile.TemporaryDirectory() as td:
            with self._temp_rpp_home(Path(td) / ".rpp"):
                temp_root = Path(td)
                dependency_source = temp_root / "plugins" / "DependencyPlugin.capnp"
                dependent_source = temp_root / "plugins" / "DependentPlugin.capnp"

                self._write_capnp_plugin_source(
                    dependency_source,
                    class_name="DependencyPlugin",
                    tag="dependency",
                    plugin_name="dependency",
                    id="1"
                )
                self._write_capnp_plugin_source(
                    dependent_source,
                    class_name="DependentPlugin",
                    tag="dependent",
                    plugin_name="dependent",
                    id="2"
                )

                self.create_test_library(temp_root / ".rpp")

                # Register the dependency plugin first
                registry_api.register_plugin_type_from_source(dependency_source, library=self.TEST_LIBRARY)

                # Now register the dependent plugin
                entries = registry_api.register_plugin_type_from_source(dependent_source, library=self.TEST_LIBRARY)
                entry = entries[0] if isinstance(entries, list) else entries

                assert entry["Library"] == self.TEST_LIBRARY
                assert entry["ClassName"] == "DependentPlugin"

                interfaces_path = rp.get_app_capnp_interfaces_path()
                lib_interfaces_path = Path(interfaces_path) / self.TEST_LIBRARY
                registered_capnp_dependency_file_exists = (lib_interfaces_path / dependency_source.name).exists()
                registered_capnp_dependent_file_exists = (lib_interfaces_path / dependent_source.name).exists()

                assert registered_capnp_dependency_file_exists
                assert registered_capnp_dependent_file_exists


    def test_unregister_plugin_type_and_list_registered_plugin_types(self):
        with tempfile.TemporaryDirectory() as td:
            with self._temp_rpp_home(Path(td) / ".rpp"):
                temp_root = Path(td)
                source_path = temp_root / "plugins" / "ItemPlugin.capnp"
                self._write_capnp_plugin_source(
                    source_path,
                    class_name="ItemPlugin",
                    tag="item",
                    plugin_name="item",
                )

                self.create_test_library(temp_root / ".rpp")
                registry_api.register_plugin_type_from_source(source_path, library=self.TEST_LIBRARY)

                assert not (registry_api.unregister_plugin_type("missing"))
                assert registry_api.unregister_plugin_type("testlib::ItemPlugin")
                assert not (registry_api.unregister_plugin_type("testlib::ItemPlugin"))

                listed = registry_api.list_registered_plugin_types()
                item_exists = any(entry == "testlib::ItemPlugin" for entry in listed["PluginTypes"].keys())
                assert not (item_exists)

                interfaces_path = rp.get_app_capnp_interfaces_path()
                lib_interfaces_path = Path(interfaces_path) / self.TEST_LIBRARY
                registered_capnp_file_exists = (lib_interfaces_path / source_path.name).exists()

                assert not (registered_capnp_file_exists)

class TestScaffold:
    @pytest.fixture(autouse=True)
    def _scaffold_workspace(self, monkeypatch, tmp_path):
        orig_cfg = rp.get_config()
        self.temp_root = tmp_path
        monkeypatch.setattr(rp, "RPP_HOME", self.temp_root / ".rpp")
        rp.RPP_HOME.mkdir(parents=True, exist_ok=True)
        write_config(rp.RPP_HOME, orig_cfg)

        self.libs_path = self.temp_root / "libraries"
        self.libs_path.mkdir(parents=True, exist_ok=True)

        self.manager = LibraryManager(rpp_home=self.temp_root / ".rpp", init_anot_only=True)
        self.lib_h = self.manager.get_or_create_plugin_library("testlib", self.libs_path)

        self.python_scaffold_path = rp.RPP_HOME / "interfaces" / "python"
        self.cpp_scaffold_path = rp.RPP_HOME / "interfaces" / "cpp"
        self.registry_path = rp.RPP_HOME / "registry"
        import rpp_plugin_registrator.plugin_type_registrator as plugin_type_registrator
        self.registrator_module = plugin_type_registrator
        yield
        rp.reset_module()
        self.registrator_module.reset_module()

    def supporting_file_src(self):
        return """
@0xaaaaaaaa00000003;
struct SupportingStruct {
  value @0 :Float64;
}
"""

    def plugin_type_src1(self):
        return """
@0xaaaaaaaa00000001;
using Anot = import "rpp_common/anot.capnp";
using Sup = import "secondlib/supporting_struct.capnp";
interface MockControllerPlugin $Anot.plugin("mock_ctl") {
  ctl1   @0 (b1: Sup.SupportingStruct) -> (b2: Bool);
}
"""

    def plugin_type_src2(self):
        return """
@0xaaaaaaaa00000002;
using Anot = import "rpp_common/anot.capnp";
interface MockDisturbanceGeneratorPlugin $Anot.plugin("mock_dist") {
  dist1   @0 (data: DisturbanceData) -> (number: Float64);
  dist2CamelCase   @1 (data: DisturbanceData) -> (number: Float64);
}

struct DisturbanceData {
  value @0 :Float64;
  superValue @1 :Float64;
}
"""

    def plugin_type_src3(self):
        return """
@0xaaaaaaaa00000009;
struct TestStruct1 {
    x @0 :Float64;
    y @1 :Float64;
    theta @2 :Float64;
}

struct TestStruct2 {
    linear @0 :Float64;
    angular @1 :Float64;
}

using Anot = import "rpp_common/anot.capnp";
interface TestType1 $Anot.plugin("test") {
  funcEmpty @0 () -> ();
  funcWithSimpleParams @1 (paramFloat :Float64, paramBool :Bool) -> (resultFloat :Float64);
  funcWithStructParam @2 (paramStruct1 :TestStruct1, paramStruct2 :TestStruct2) -> (resultStruct1 :TestStruct1);
  funcWithListParam @3 (paramListFloat :List(Float64), paramListStruct :List(TestStruct1)) -> (resultList :List(Float64));
  funcWithListOfStructParam @4 (paramListStruct :List(TestStruct1)) -> (resultListStruct2 :List(TestStruct2));
  funcWithMultipleSimpleReturns @5 () -> (resultFloat :Float64, resultBool :Bool);
  funcWithMultipleStructReturns @6 () -> (resultStruct1 :TestStruct1, resultStruct2 :TestStruct2);
  funcWithMultipleListReturns @7 () -> (resultListFloat :List(Float64), resultListStruct :List(TestStruct1));
}
"""


    def test_scaffold_all_languages(self, monkeypatch):
        lib_path = self.lib_h.path
        self.registrator_module.SCAFFOLD_LANGUAGES = ["python", "cpp"]

        second_lib = self.manager.get_or_create_plugin_library("secondlib")

        source_path = second_lib.path / "plugins" / "supporting_struct.capnp"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(self.supporting_file_src(), encoding="utf-8")
        registry_api.register_plugin_type_from_source(
            source_path,
            library="secondlib",
        )

        source_path = lib_path / "plugins" / "MockControllerPlugin.capnp"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(self.plugin_type_src1(), encoding="utf-8")

        def create_so_file():
            class_name = "MockControllerPlugin"
            hpp_source_file = rp.get_app_interfaces_path() / "cpp" / "rpp_plugin_types" / "testlib" / f"{class_name}.hpp"
            capnp_dir = rp.get_app_interfaces_path() / "cpp" / "capnp_gen" / 'testlib'
            tmp_out_dir = get_tmp_dir_for_compilation(str(hpp_source_file), class_name)
            path = tmp_out_dir / f"{class_name}.so"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("dummy shared object content", encoding="utf-8")
            gen_source_path = capnp_dir / f"{class_name}.capnp.h"
            gen_source_path.parent.mkdir(parents=True, exist_ok=True)
            gen_source_path.write_text("dummy generated source content", encoding="utf-8")
            return subprocess.CompletedProcess(args=[], returncode=0)

        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: create_so_file(),
        )


        entries = registry_api.register_plugin_type_from_source(
            source_path,
            library="testlib",
        )
        entry = entries[0] if isinstance(entries, list) else entries

        assert entry["Library"] == "testlib"
        assert entry["ClassName"] == "MockControllerPlugin"
        assert entry["PluginTypeName"] == "testlib::MockControllerPlugin"
        assert Path(entry["RegistryPluginTypeFile"]).exists()

        assert (self.python_scaffold_path / "rpp_plugin_types" / "testlib" / "MockControllerPlugin.py").exists()
        assert (self.cpp_scaffold_path / "rpp_plugin_types" / "testlib" / "MockControllerPlugin.hpp").exists()

    def test_scaffold_python1(self):

        self.registrator_module.SCAFFOLD_LANGUAGES = ["python"]
        lib_path = self.lib_h.path

        second_lib = self.manager.get_or_create_plugin_library("secondlib")

        source_path = second_lib.path / "plugins" / "supporting_struct.capnp"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(self.supporting_file_src(), encoding="utf-8")

        registry_api.register_plugin_type_from_source(
            source_path,
            library="secondlib",
        )

        source_path = lib_path / "plugins" / "MockControllerPlugin.capnp"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(self.plugin_type_src1(), encoding="utf-8")

        entries = registry_api.register_plugin_type_from_source(
            source_path,
            library="testlib",
        )
        entry = entries[0] if isinstance(entries, list) else entries

        assert entry["Library"] == "testlib"
        assert entry["ClassName"] == "MockControllerPlugin"
        assert entry["PluginTypeName"] == "testlib::MockControllerPlugin"
        assert Path(entry["RegistryPluginTypeFile"]).exists()

        assert (self.python_scaffold_path / "rpp_plugin_types" / "testlib" / "MockControllerPlugin.py").exists()
        assert (self.python_scaffold_path / "rpp_plugin_types" / "testlib" / "__init__.py").exists()
        assert not ((self.cpp_scaffold_path / "rpp_plugin_types" / "testlib" / "MockControllerPlugin.cpp").exists())

    def test_scaffold_python2(self):
        self.registrator_module.SCAFFOLD_LANGUAGES = ["python"]
        lib_path = self.lib_h.path
        source_path = lib_path / "plugins" / "MockDisturbanceGeneratorPlugin.capnp"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(self.plugin_type_src2(), encoding="utf-8")

        entries = registry_api.register_plugin_type_from_source(
            source_path,
            library="testlib",
        )
        entry = entries[0] if isinstance(entries, list) else entries

        assert entry["Library"] == "testlib"
        assert entry["ClassName"] == "MockDisturbanceGeneratorPlugin"
        assert entry["PluginTypeName"] == "testlib::MockDisturbanceGeneratorPlugin"

        assert (self.python_scaffold_path / "rpp_plugin_types" / "testlib" / "MockDisturbanceGeneratorPlugin.py").exists()
        assert (self.python_scaffold_path / "rpp_plugin_types" / "testlib" / "__init__.py").exists()
        assert not ((self.cpp_scaffold_path / "rpp_plugin_types" / "testlib" / "MockDisturbanceGeneratorPlugin.cpp").exists())

    def test_scaffold_cpp1(self):
        self.registrator_module.SCAFFOLD_LANGUAGES = ["cpp"]
        lib_path = self.lib_h.path

        second_lib = self.manager.get_or_create_plugin_library("secondlib")

        source_path = second_lib.path / "plugins" / "supporting_struct.capnp"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(self.supporting_file_src(), encoding="utf-8")
        registry_api.register_plugin_type_from_source(
            source_path,
            library="secondlib",
        )


        source_path = lib_path / "plugins" / "MockControllerPlugin.capnp"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(self.plugin_type_src1(), encoding="utf-8")
        entries = registry_api.register_plugin_type_from_source(
            source_path,
            library="testlib",
        )

        gen_source_file = self.cpp_scaffold_path / "rpp_plugin_types" / "testlib" / "MockControllerPlugin.hpp"
        assert gen_source_file.exists()
        assert not ((self.python_scaffold_path / "rpp_plugin_types" / "testlib" / "MockControllerPlugin.py").exists())

        capnp_autogen_path = rp.get_app_interfaces_path() / "cpp" / "capnp_gen" / "testlib"
        assert (capnp_autogen_path / "MockControllerPlugin.capnp.h").exists()
        assert (capnp_autogen_path / "MockControllerPlugin.capnp.c++").exists()

        registry_path = rp.get_app_registry_path()
        shared_libs_path = registry_path / "cpp" / "shared" / "testlib" / "plugin_types"
        assert shared_libs_path.exists()

        assert any(f.suffix == ".so" for f in shared_libs_path.iterdir())

        capnp_h_file = capnp_autogen_path / "MockControllerPlugin.capnp.h"
        content = capnp_h_file.read_text(encoding="utf-8")
        assert '#include "capnp_gen/secondlib/supporting_struct.capnp.h"' in content


        loaded = gen_source_file.read_text(encoding="utf-8")

        assert "class MockControllerPlugin" in loaded

    def test_scaffold_cpp2(self):
        self.registrator_module.SCAFFOLD_LANGUAGES = ["cpp"]
        lib_path = self.lib_h.path
        source_path = lib_path / "plugins" / "MockDisturbanceGeneratorPlugin.capnp"
        source_path.parent.mkdir(parents=True, exist_ok=True)

        source_path.write_text(self.plugin_type_src2(), encoding="utf-8")
        entries = registry_api.register_plugin_type_from_source(
            source_path,
            library="testlib",
        )

        gen_source_file = self.cpp_scaffold_path / "rpp_plugin_types" / "testlib" / "MockDisturbanceGeneratorPlugin.hpp"
        assert gen_source_file.exists()
        assert not ((self.python_scaffold_path / "rpp_plugin_types" / "testlib" / "MockDisturbanceGeneratorPlugin.py").exists())

        assert (self.cpp_scaffold_path / "capnp_gen" / "testlib" / "MockDisturbanceGeneratorPlugin.capnp.h").exists()
        assert (self.cpp_scaffold_path / "capnp_gen" / "testlib" / "MockDisturbanceGeneratorPlugin.capnp.c++").exists()

        loaded = gen_source_file.read_text(encoding="utf-8")

        assert "class MockDisturbanceGeneratorPlugin" in loaded


    def test_scaffold_cpp3(self):
        self.registrator_module.SCAFFOLD_LANGUAGES = ["cpp"]
        lib_path = self.lib_h.path
        source_path = lib_path / "plugins" / "TestType1.capnp"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(self.plugin_type_src3(), encoding="utf-8")

        entries = registry_api.register_plugin_type_from_source(
            source_path,
            library="testlib",
        )
        entry = entries[0] if isinstance(entries, list) else entries

        gen_source_file = self.cpp_scaffold_path / "rpp_plugin_types" / "testlib" / "TestType1.hpp"
        assert gen_source_file.exists()
        assert not ((self.python_scaffold_path / "rpp_plugin_types" / "testlib" / "TestType1.py").exists())
