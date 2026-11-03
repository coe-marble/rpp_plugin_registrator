import json
import json5
import tempfile
import shutil
from pathlib import Path
from unittest import mock
import pytest

import rpp_plugin_registrator
from rpp_plugin_registrator.library_manager import LibraryManager
from rpp_plugin_registrator import registry_config as rp
from rpp_plugin_registrator.plugin_validators.dispatch import PluginValidationResult, PluginValidationData
from rpp_plugin_registrator.plugin_descriptors import parse_plugin_file
from rpp_plugin_registrator.plugin_descriptors.core import PluginInfo, PluginTypeInfo
from rpp_plugin_registrator.plugin_validators.cpp import validate_cpp_plugin
import rpp_plugin_registrator.registry_config


#TODO: Fix this
RPP_TESTING_PATH = Path(__file__).parent.parent.parent.resolve() \
    / "rpp_testing" / "rpp_testing"
EXAMPLES_DATA_PATH = RPP_TESTING_PATH / "data"

def write_config(home: Path, orig_cfg: dict):
    new_config_path = home / "config.json"
    home.mkdir(parents=True, exist_ok=True)
    with open(new_config_path, "w", encoding="utf-8") as f:
        json.dump(orig_cfg, f, indent=4)

class TestLibraryManager:
    @pytest.fixture(autouse=True)
    def _rpp_home(self, monkeypatch, tmp_path):
        self.home = tmp_path / "rpp-home"
        self.home.mkdir(parents=True, exist_ok=True)
        cfg = rp.get_config()
        monkeypatch.setattr(rp, "RPP_HOME", self.home)
        write_config(self.home / ".rpp", cfg)

        import rpp_plugin_registrator.plugin_type_registrator
        monkeypatch.setattr(
            rpp_plugin_registrator.plugin_type_registrator,
            "SCAFFOLD_LANGUAGES",
            ["python"],
        )
        yield
        rp.reset_module()
        rpp_plugin_registrator.plugin_type_registrator.reset_module()

    def test_library_manager_starts_with_empty_registry(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            manager = LibraryManager(rpp_home=temp_root / ".rpp")
            plugins = manager.get_available_plugins()
            libraries = manager.list_plugin_libraries()
            assert "rpp_common" in plugins
            assert "rpp_testing" in plugins
            assert any(lib["Name"] == "rpp_common" for lib in libraries)
            assert any(lib["Name"] == "rpp_testing" for lib in libraries)



    def test_refresh_component_library_includes_custom_plugin_types_in_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            manager = LibraryManager(rpp_home=temp_root / ".rpp")
            handle = manager.get_or_create_plugin_library("TestLib")

            library_root = Path(handle.path)
            plugin_type_dir = library_root / "plugin_types"
            plugin_type_dir.mkdir(parents=True, exist_ok=True)

            plugin_type_path = plugin_type_dir / "ControlType.capnp"
            plugin_type_path.write_text(
                """@0xabcdefabcdefabcdef;
using Anot = import "rpp_common/anot.capnp";
interface ControlType $Anot.plugin("ControlType"){
  item @0 () -> ();
}
""", encoding="utf-8",
            )

            plugins_path = library_root / "plugins.json"
            plugins_payload = json5.loads(plugins_path.read_text(encoding="utf-8"))
            plugins_payload["PluginTypes"] = [
                {
                    "Name": "Control",
                    "Path": "plugin_types/ControlType.capnp",
                    "Type": "file",
                }
            ]
            plugins_path.write_text(json.dumps(plugins_payload, indent=2) + "\n", encoding="utf-8")

            manager.refresh_plugin_library("TestLib")

            manifest_path = rp.get_app_library_manifest_path_json("TestLib")
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

            assert "PluginTypes" in manifest_payload
            assert "TestLib::ControlType" in manifest_payload["PluginTypes"]
            registry_plugin_type_file = \
                manifest_payload["PluginTypes"]["TestLib::ControlType"]["RegistryPluginTypeFile"]
            abs_path = rp.get_app_registry_path() / registry_plugin_type_file

            assert abs_path.exists(), f"Expected registry plugin type file '{abs_path}' does not exist."
            assert manifest_payload["PluginTypes"]["TestLib::ControlType"]["Library"] == "TestLib"


    def test_plugin_type_lifecycle_updates_library_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            manager = LibraryManager(rpp_home=Path(td) / ".rpp")
            handle = manager.get_or_create_plugin_library("TestLib")
            source_path = Path(handle.path) / "plugin_types" / "ControlType.capnp"
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text(
                """@0xabcdefabcdefabcdef;
using Anot = import "rpp_common/anot.capnp";
interface ControlType $Anot.plugin("ControlType") {
  item @0 () -> ();
}
""",
                encoding="utf-8",
            )

            registered_types = manager.register_plugin_type_from_source(
                source_path, "TestLib"
            )

            assert registered_types[0]["PluginTypeName"] == "TestLib::ControlType"
            assert "TestLib::ControlType" in manager.get_library_plugin_types("TestLib")
            assert manager.unregister_plugin_type("TestLib::ControlType")
            assert "TestLib::ControlType" not in manager.get_library_plugin_types("TestLib")


    def test_refresh_component_library_includes_custom_plugins_in_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            manager = LibraryManager(rpp_home=temp_root / ".rpp")
            handle = manager.get_or_create_plugin_library("TestLib")

            library_root = Path(handle.path)
            plugin_dir = library_root / "plugins"
            plugin_dir.mkdir(parents=True, exist_ok=True)

            plugin_path = plugin_dir / "MyPlugin.py"
            plugin_path.write_text(
                """from rpp_plugin_types.rpp_testing import MotionController2D
class MyPlugin(MotionController2D):
    def name(self) -> str:
        return "my_plugin"
    def execute(self, input: str) -> str:
        return input
""", encoding="utf-8",
            )

            plugins_path = library_root / "plugins.json"
            plugins_payload = json5.loads(plugins_path.read_text(encoding="utf-8"))
            plugins_payload["Plugins"] = [
                {
                    "Name": "MyPlugin",
                    "Path": "plugins/MyPlugin.py",
                    "Type": "file",
                }
            ]
            plugins_path.write_text(json.dumps(plugins_payload, indent=2) + "\n", encoding="utf-8")

            manager.refresh_plugin_library("TestLib")
            manager.refresh_plugin_library("TestLib")

            refreshed_plugins = json5.loads(
                plugins_path.read_text(encoding="utf-8"))
            assert [entry["Name"] for entry in refreshed_plugins["Plugins"]] == ["MyPlugin"]

            manifest_path = rp.get_app_library_manifest_path_json("TestLib")
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

            assert "Plugins" in manifest_payload
            assert "TestLib::MyPlugin" in manifest_payload["Plugins"]
            abs_path = manager.get_plugin_path_absolute(
                manifest_payload["Plugins"]["TestLib::MyPlugin"]["SourceFile"],
                "TestLib",
            )

            assert str(abs_path) == str(plugin_path.resolve())
            assert manifest_payload["Plugins"]["TestLib::MyPlugin"]["Library"] == "TestLib"

    def test_library_package_json_parse(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            manager = LibraryManager(rpp_home=temp_root / ".rpp")
            handle = manager.get_or_create_plugin_library("TestLib")

            library_root = Path(handle.path)
            package_path = library_root / "package.json"
            package_source = {
                "Library": "TestLib",
                "Version": "0.1.0",
                "RosDependencies": [
                    "rclcpp>=2.0.0",
                    "zlib>=1.2.11"
                ],
                "Dependencies": [
                    "rpp_common>=0.0.1",
                ]
            }
            package_path.write_text(json.dumps(package_source, indent=2) + "\n", encoding="utf-8")

            library_info = manager.get_library_info("TestLib")
            assert library_info["Library"] == "TestLib"
            assert library_info["Version"] == "0.1.0"
            assert library_info["RosDependencies"] == ["rclcpp>=2.0.0", "zlib>=1.2.11"]
            assert library_info["Dependencies"] == ["rpp_common>=0.0.1"]

    def test_library_package_xml_parse(self):
        with tempfile.TemporaryDirectory() as td:
            xml_source = """<?xml version="1.0"?>
<?xml-model href="http://download.ros.org/schema/package_format3.xsd" schematypens="http://www.w3.org/2001/XMLSchema"?>
<package format="3">
  <name>test_lib</name>
  <version>0.0.2</version>
  <description>TestDesc</description>
  <maintainer email="maintainer_email">maintainer</maintainer>
  <license>TestLicence</license>

  <depend>test_depend_ros_1</depend>
  <depend version_eq="0.0.2">test_depend_ros_2</depend>
  <depend version_lte="0.0.3">test_depend_ros_3</depend>
  <depend version_gte="0.0.4">test_depend_ros_4</depend>
  <buildtool_depend>ament_cmake</buildtool_depend>
  <test_depend>ament_lint_auto</test_depend>
  <test_depend>ament_lint_common</test_depend>
  <test_depend>ament_cmake_gtest</test_depend>

  <export>
    <build_type>ament_cmake</build_type>
    <rpp_dependencies>
        <depend>test_depend1</depend>
        <depend version_lt="0.0.5">test_depend2</depend>
        <depend version_gt="0.0.6">test_depend3</depend>
    </rpp_dependencies>

  </export>
</package>

"""

            temp_root = Path(td)
            manager = LibraryManager(rpp_home=temp_root / ".rpp")
            handle = manager.get_or_create_plugin_library("TestLib")

            current_package_path = Path(handle.path) / "package.json"
            if current_package_path.exists():
                current_package_path.unlink()


            library_root = Path(handle.path)
            package_path = library_root / "package.xml"
            package_path.write_text(xml_source, encoding="utf-8")

            library_info = manager.get_library_info("TestLib")

            assert library_info["Library"] == "test_lib"
            assert library_info["Version"] == "0.0.2"
            assert library_info["License"] == "TestLicence"
            assert library_info["RosDependencies"] == [
                "test_depend_ros_1",
                "test_depend_ros_2==0.0.2",
                "test_depend_ros_3<=0.0.3",
                "test_depend_ros_4>=0.0.4",
            ]
            assert library_info["Dependencies"] == [
                "test_depend1",
                "test_depend2<0.0.5",
                "test_depend3>0.0.6",
            ]

class TestPythonPluginRegistrator:
    @pytest.fixture(autouse=True)
    def _rpp_home(self, monkeypatch, tmp_path):
        self.home = tmp_path / "rpp-home"
        self.home.mkdir(parents=True, exist_ok=True)
        cfg = rp.get_config()
        write_config(self.home / ".rpp", cfg)
        monkeypatch.setenv(
            "RPP_WHITELIST_PLUGIN_TYPES", "rpp_testing::MotionController2D"
        )
        monkeypatch.setattr(rp, "RPP_HOME", self.home)
        self.manager = LibraryManager(rpp_home=self.home / ".rpp")
        yield
        rp.reset_module()


    def test_register_component_from_python_file_pass(self):
        lib_handle = self.manager.get_or_create_plugin_library("TestLib")

        plugin_source = Path(lib_handle.path) / lib_handle.name / "hello_plugin.py"
        plugin_source.write_text(
            """
from rpp_plugin_types.rpp_testing import MotionController2D
class HelloPlugin(MotionController2D):
    def name(self) -> str:
        return "hello"
    def execute(self, input: str) -> str:
        return input
""".strip()
            + "\n",
            encoding="utf-8",
        )

        result = self.manager.register_plugin_from_source(plugin_source, "TestLib")
        assert result

        plugins = self.manager.get_available_plugins()
        assert "TestLib" in plugins
        assert "rpp_testing::MotionController2D" in plugins["TestLib"]
        hello_item = self.manager.get_plugin_info_from_lib("TestLib::HelloPlugin")
        assert hello_item is not None
        assert hello_item["Name"] == "HelloPlugin"
        assert hello_item["ClassName"] == "HelloPlugin"
        assert hello_item["PluginType"] == "rpp_testing::MotionController2D"
        assert hello_item["Library"] == "TestLib"
        assert hello_item["FullyQualifiedClassName"].endswith(
            ".hello_plugin.HelloPlugin'>"
        )
        assert hello_item["PluginName"] == "TestLib::HelloPlugin"
        assert hello_item["PluginTypeLibrary"] == "rpp_testing"
        assert "PluginTypeSharedLibraryPath" in hello_item
        assert hello_item.get("PluginSharedLibraryPath") is None

        plugins_manifest = json5.loads(
            (Path(lib_handle.path) / "plugins.json").read_text(encoding="utf-8")
        )
        assert [entry["Name"] for entry in plugins_manifest["Plugins"]] == ["HelloPlugin"]

        shared_lib_path = hello_item["PluginTypeSharedLibraryPath"]
        registry_path = rp.get_app_registry_path()
        assert (registry_path / shared_lib_path).exists(), f"Expected shared library '{shared_lib_path}' does not exist."
        metadata = hello_item.get("PluginMetadata", {})
        assert "Parameters" in metadata
        assert "Components" in metadata
        assert metadata["Components"] == {}
        assert metadata["Parameters"] == {}

        libraries = self.manager.list_plugin_libraries()
        assert any(lib["Name"] == "TestLib" for lib in libraries)

    def test_register_component_from_python_file_with_mock_validation(self):

        handle = self.manager.get_or_create_plugin_library("TestLib")

        plugin_source = Path(handle.path) / handle.name / "fallback_plugin.py"
        plugin_source.write_text(
            """
from rpp_plugin_types.rpp_testing import MotionController2D


class FallbackPlugin(MotionController2D):
    def name(self) -> str:
        return "fallback"

    def execute(self, input: str) -> str:
        return input
""".strip()
            + "\n",
            encoding="utf-8",
        )

        with mock.patch("rpp_plugin_registrator.library_manager.validate_plugin") as validate_plugin:
            validate_plugin.return_value = PluginValidationResult(
                is_valid=True,
                message=None,
                validation_data=PluginValidationData(
                    class_name="FallbackPlugin",
                    plugin_type="rpp_testing::MotionController2D",
                    plugin_type_library="rpp_testing",
                    plugin_type_class_name="MotionController2D",
                    plugin_type_source_file="rpp_testing/MotionController2D.py",
                    fully_qualified_class_name="<class 'fallback_plugin.FallbackPlugin'>",
                    fully_qualified_plugin_class_name="<class 'rpp_plugin_types.rpp_testing.MotionController2D.MotionController2D'>",
                ),
            )
            result = self.manager.register_plugin_from_source(plugin_source, "TestLib")

        assert result

        plugins = self.manager.get_available_plugins()
        plugin_items = [item for group in plugins["TestLib"].values() for item in group]
        fallback_item = next((item for item in plugin_items if item.get("PluginName") == "TestLib::FallbackPlugin"), None)
        assert fallback_item is not None
        assert fallback_item["PluginType"] == "rpp_testing::MotionController2D"
        assert fallback_item["PluginTypeLibrary"] == "rpp_testing"
        assert fallback_item["PluginName"] == "TestLib::FallbackPlugin"

    def test_register_component_from_python_file_with_invalid_plugin_type(self):

        handle = self.manager.get_or_create_plugin_library("TestLib")

        plugin_source = Path(handle.path) / handle.name / "invalid_plugin.py"
        plugin_source.write_text(
            """
from rpp_plugin_types.rpp_common2 import MotionController2D
class InvalidPlugin(MotionController2D):
    def name(self) -> str:
        return "invalid"
    def execute(self, input: str) -> str:
        return input
""".strip()
            + "\n",
            encoding="utf-8",
        )
        did_throw = True
        try:
            result = self.manager.register_plugin_from_source(plugin_source, "TestLib")
            did_throw = False
        except ValueError as e:
            assert "Failed to import plugin class from" in str(e)

        assert did_throw, "Expected ValueError was not raised for invalid plugin type."

    def test_register_python_plugin_and_refresh_library(self):
        handle = self.manager.get_or_create_plugin_library("TestLib")

        library_root = Path(handle.path)
        plugin_dir = library_root / "plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)

        plugin_path = plugin_dir / "ComponentPlugin.py"
        plugin_path.write_text(
            """
from rpp_plugin_types.rpp_testing import MotionController2D
from rpp_py.plugin import ParameterDescription

class SuperClass:
    def __init__(self, a = 1, b = 2):
        self.a = a
        self.b = b

class ComponentPlugin(MotionController2D):
    COMPONENTS = {
        "ctl1": "TestLib::ComponentPlugin",
    }

    PARAMETERS = [
        ParameterDescription("param1", 1.1),
        ParameterDescription("param2", 2),
        ParameterDescription("param3", "default_string"),
        ParameterDescription("param4", True),
        ParameterDescription("param5", [1, 2, 3]),
        ParameterDescription("param6", {"key1": "value1", "key2": 2}),
        ParameterDescription("param7", SuperClass(a=10))
    ]
    def name(self) -> str:
        return "component_plugin"
    def on_step(self, y, dt):
        return y
""", encoding="utf-8",
        )

        plugins_path = library_root / "plugins.json"
        plugins_payload = json5.loads(plugins_path.read_text(encoding="utf-8"))
        plugins_payload["Plugins"] = [
            {
                "Name": "ComponentPlugin",
                "Path": "plugins/ComponentPlugin.py",
                "Type": "file",
            }
        ]
        plugins_path.write_text(json.dumps(plugins_payload, indent=2) + "\n", encoding="utf-8")

        self.manager.refresh_plugin_library("TestLib")

        manifest_path = rp.get_app_library_manifest_path_json("TestLib")
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

        assert "Plugins" in manifest_payload
        assert "TestLib::ComponentPlugin" in manifest_payload["Plugins"]
        abs_path = self.manager.get_plugin_path_absolute(
            manifest_payload["Plugins"]["TestLib::ComponentPlugin"]["SourceFile"],
            "TestLib",
        )
        assert str(abs_path) == str(plugin_path.resolve())

        comps = self.manager.get_plugin_components_from_lib("ComponentPlugin", "TestLib")
        assert comps == {"ctl1": "TestLib::ComponentPlugin"}

        params = self.manager.get_plugin_parameters_from_lib("ComponentPlugin", "TestLib")
        assert params["param1"] == {"name": "param1", "default_value": 1.1, "type": "float"}
        assert params["param2"] == {"name": "param2", "default_value": 2, "type": "int"}
        assert params["param3"] == {"name": "param3", "default_value": "default_string", "type": "string"}
        assert params["param4"] == {"name": "param4", "default_value": True, "type": "bool"}
        assert params["param5"]["type"] == "array"
        assert params["param5"]["default_value"] == [
            {"name": "param5[0]", "default_value": 1, "type": "int"},
            {"name": "param5[1]", "default_value": 2, "type": "int"},
            {"name": "param5[2]", "default_value": 3, "type": "int"},
        ]
        assert params["param5"]["element_type"] == "int"
        assert params["param6"]["type"] == "object"
        assert params["param6"]["fields"] == {
            "key1": {"name": "key1", "default_value": "value1", "type": "string"},
            "key2": {"name": "key2", "default_value": 2, "type": "int"},
        }
        assert params["param7"]["type"] == "object"
        assert params["param7"]["fields"] == {
            "a": {"name": "a", "default_value": 10, "type": "int"},
            "b": {"name": "b", "default_value": 2, "type": "int"},
        }

class TestCppPluginRegistrator:
    @pytest.fixture(autouse=True)
    def _registry_state(self, monkeypatch, tmp_path):
        self._home_dir = tmp_path
        cfg = rp.get_config()
        rpp_home = self._home_dir / ".rpp"
        write_config(rpp_home, cfg)
        monkeypatch.setattr(rp, "RPP_HOME", rpp_home)
        monkeypatch.delenv("RPP_WHITELIST_PLUGIN_TYPES", raising=False)
        yield
        rpp_plugin_registrator.registry_config.reset_module()
        rp.reset_module()

    def test_parse_cpp_plugin_with_final_base_class(self):
        with tempfile.TemporaryDirectory() as td:
            source_path = Path(td) / "final_plugin.hpp"
            source_path.write_text(
                "class FinalPlugin final : public example::PluginType {};\n",
                encoding="utf-8",
            )

            result = parse_plugin_file(source_path)

            assert result.is_valid
            assert result.data.plugins[0]["BaseClasses"] == ["example::PluginType"]

    def test_cpp_plugin_type_override_does_not_require_direct_base(self):
        source_path = self._home_dir / "explicit_plugin.hpp"
        source_path.write_text(
            "class ExplicitPlugin final : public PrivateBase {};\n",
            encoding="utf-8",
        )
        desc = PluginInfo(
            info={
                "SourceFile": str(source_path),
                "ClassName": "ExplicitPlugin",
                "BaseClasses": ["PrivateBase"],
                "DeclaredPluginType": "TestLib::KnownPluginType",
            }
        )
        plugin_types = {
            "TestLib::KnownPluginType": PluginTypeInfo(
                info={
                    "Library": "TestLib",
                    "ClassName": "KnownPluginType",
                    "SourceFile": "plugin_types/known.capnp",
                    "FullyQualifiedClassName": "TestLib::KnownPluginType",
                }
            )
        }

        with mock.patch(
            "rpp_plugin_registrator.plugin_validators.cpp.compile_cpp_plugin",
            return_value=(None, [], None),
        ) as compile_plugin:
            validation = validate_cpp_plugin(desc, plugin_types)

        assert validation.is_valid
        assert validation.validation_data.plugin_type == "TestLib::KnownPluginType"
        assert compile_plugin.call_args.kwargs["plugin_type_name"] == "TestLib::KnownPluginType"

    def test_cpp_plugin_type_override_rejects_unknown_type(self):
        desc = PluginInfo(
            info={
                "ClassName": "ExplicitPlugin",
                "DeclaredPluginType": "TestLib::UnknownPluginType",
            }
        )

        validation = validate_cpp_plugin(desc, {})

        assert not (validation.is_valid)
        assert "declares unknown PluginType" in validation.message

    def test_register_cpp_plugin_with_components_then_unregister(self, monkeypatch):

        monkeypatch.setenv(
            "RPP_WHITELIST_PLUGIN_TYPES", "rpp_testing::MotionController2D"
        )
        manager = LibraryManager(rpp_home=self._home_dir / ".rpp")
        handle = manager.get_or_create_plugin_library("TestLib")

        library_root = Path(handle.path)
        plugin_dir = library_root / "plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)

        plugin_path = plugin_dir / "ComponentPluginSimpleCpp.cpp"
        shutil.copyfile(
            EXAMPLES_DATA_PATH / "example_plugins" / "example_plugin_simple_cpp.cpp",
            plugin_path,
        )

        manager.register_plugin_from_source(plugin_path, "TestLib")

        manifest_path = rp.get_app_library_manifest_path_json("TestLib")
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

        assert "Plugins" in manifest_payload
        assert "TestLib::ComponentPluginSimpleCpp" in manifest_payload["Plugins"]
        abs_path = manager.get_plugin_path_absolute(
            manifest_payload["Plugins"]["TestLib::ComponentPluginSimpleCpp"]["SourceFile"],
            "TestLib",
        )
        assert str(abs_path) == str(plugin_path.resolve())


        so_path = rp.get_app_registry_path() / "cpp" / "shared" / \
            "TestLib" / "plugins" / "ComponentPluginSimpleCpp.so"
        plugin_json_path = rp.get_app_registry_plugin_json_path(
            "TestLib::ComponentPluginSimpleCpp")
        assert so_path.exists(), f"Expected shared library '{so_path}' does not exist."
        assert plugin_json_path.exists(), f"Expected plugin source file '{plugin_json_path}' does not exist."




        manager.unregister_plugin("TestLib::ComponentPluginSimpleCpp")
        assert "TestLib::ComponentPluginSimpleCpp" not in manager.get_available_plugins().get("TestLib", {})
        assert not (so_path.exists()), f"Shared library '{so_path}' should have been removed after unregistering the plugin."
        assert not (plugin_json_path.exists()), f"Plugin source file '{abs_path}' should still exist after unregistering the plugin."


    def test_register_cpp_plugin_with_using_namespace_and_type_aliasing(
            self, monkeypatch):
        monkeypatch.setenv(
            "RPP_WHITELIST_PLUGIN_TYPES", "rpp_testing::MotionController2D"
        )

        manager = LibraryManager(rpp_home=self._home_dir / ".rpp")
        handle = manager.get_or_create_plugin_library("TestLib")

        library_root = Path(handle.path)
        plugin_dir = library_root / "plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)

        def load_and_test(file_name, class_name):
            plugin_path = plugin_dir / f"{class_name}.cpp"
            shutil.copyfile(
                EXAMPLES_DATA_PATH / "complex_plugins" / file_name,
                plugin_path,
            )

            manager.register_plugin_from_source(plugin_path, "TestLib")

            manifest_path = rp.get_app_library_manifest_path_json("TestLib")
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

            assert "Plugins" in manifest_payload
            assert f"TestLib::{class_name}" in manifest_payload["Plugins"]
            abs_path = manager.get_plugin_path_absolute(
                manifest_payload["Plugins"][f"TestLib::{class_name}"]["SourceFile"],
                "TestLib",
            )
            assert str(abs_path) == str(plugin_path.resolve())


        load_and_test("example_plugin_with_using_namespace.cpp", "ComponentPluginWithUsingNamespace")
        load_and_test("example_plugin_with_type_alias_outside_class.cpp", "ComponentPluginWithTypeAliasOutsideClass")
        load_and_test("example_plugin_with_type_alias_in_class.cpp", "ComponentPluginWithTypeAliasInClass")

    def test_register_cpp_plugin_with_library_dependencies(self, monkeypatch):
        monkeypatch.setenv(
            "RPP_WHITELIST_PLUGIN_TYPES", "rpp_testing::MotionController2D"
        )
        rpp_plugin_registrator.registry_config.set_to_config("USE_ROS2_COMPILATION", "True")
        manager = LibraryManager(rpp_home=self._home_dir / ".rpp")
        handle = manager.get_or_create_plugin_library("rpp_testing")
        handle = manager.get_or_create_plugin_library("TestLib")

        library_root = Path(handle.path)
        plugin_dir = library_root / "plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)


        package_source = {
            "Library": "TestLib",
            "Version": "0.1.0",
            "Dependencies": [
                "rpp_testing>=0.0.1",
            ],
            "RosDependencies": [
                "rclcpp>=2.0.0",
                "zlib>=1.2.11"
            ]
        }

        package_path = library_root / "package.json"
        package_path.write_text(json.dumps(package_source, indent=2) + "\n", encoding="utf-8")


        plugin_path = plugin_dir / "ComponentPluginWithDependencies.cpp"
        shutil.copyfile(
            EXAMPLES_DATA_PATH / "complex_plugins" / "example_plugin_with_dependencies.cpp",
            plugin_path,
        )

        manager.register_plugin_from_source(plugin_path, "TestLib")

        manifest_path = rp.get_app_library_manifest_path_json("TestLib")
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

        assert "Plugins" in manifest_payload
        assert "TestLib::ComponentPluginWithDependencies" in manifest_payload["Plugins"]
        abs_path = manager.get_plugin_path_absolute(
            manifest_payload["Plugins"]["TestLib::ComponentPluginWithDependencies"]["SourceFile"],
            "TestLib",
        )
        assert str(abs_path) == str(plugin_path.resolve())

        so_path = rp.get_app_registry_path() / "cpp" / "shared" / "TestLib" / "plugins" / "ComponentPluginWithDependencies.so"
        assert so_path.exists(), f"Expected shared library '{so_path}' does not exist."

    def test_register_cpp_plugin_with_all_interface_types(self, monkeypatch):
        monkeypatch.setenv("RPP_WHITELIST_PLUGIN_TYPES", "rpp_testing::test")
        rpp_plugin_registrator.registry_config.set_to_config("USE_ROS2_COMPILATION", "True")
        manager = LibraryManager(rpp_home=self._home_dir / ".rpp")
        handle = manager.get_or_create_plugin_library("rpp_testing")
        handle = manager.get_or_create_plugin_library("TestLib")

        library_root = Path(handle.path)
        plugin_dir = library_root / "plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)

        plugin_path = plugin_dir / "TestInterfaceAll.cpp"
        shutil.copyfile(
            EXAMPLES_DATA_PATH / "example_plugins" / "example_all_interface_types_cpp.cpp",
            plugin_path,
        )

        manager.register_plugin_from_source(plugin_path, "TestLib")

        manifest_path = rp.get_app_library_manifest_path_json("TestLib")
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

        assert "Plugins" in manifest_payload
        assert "TestLib::AllInterfaceTypesCpp" in manifest_payload["Plugins"]
        abs_path = manager.get_plugin_path_absolute(
            manifest_payload["Plugins"]["TestLib::AllInterfaceTypesCpp"]["SourceFile"],
            "TestLib",
        )
        assert str(abs_path) == str(plugin_path.resolve())

    def test_register_cpp_plugin_with_data_fields(self, monkeypatch):
        monkeypatch.setenv(
            "RPP_WHITELIST_PLUGIN_TYPES", "rpp_testing::DisturbanceGenerator2D"
        )
        rpp_plugin_registrator.registry_config.set_to_config("USE_ROS2_COMPILATION", "True")
        manager = LibraryManager(rpp_home=self._home_dir / ".rpp")
        handle = manager.get_or_create_plugin_library("rpp_testing")
        handle = manager.get_or_create_plugin_library("TestLib")

        library_root = Path(handle.path)
        plugin_dir = library_root / "plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)

        plugin_path = plugin_dir / "ComponentPluginWithDataFields.cpp"
        shutil.copyfile(
            EXAMPLES_DATA_PATH / "example_plugins" / "example_data_interface_cpp.cpp",
            plugin_path,
        )

        manager.register_plugin_from_source(plugin_path, "TestLib")

        manifest_path = rp.get_app_library_manifest_path_json("TestLib")
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

        assert "Plugins" in manifest_payload
        assert "TestLib::DataInterfaceCpp" in manifest_payload["Plugins"]
        abs_path = manager.get_plugin_path_absolute(
            manifest_payload["Plugins"]["TestLib::DataInterfaceCpp"]["SourceFile"],
            "TestLib",
        )
        assert str(abs_path) == str(plugin_path.resolve())
