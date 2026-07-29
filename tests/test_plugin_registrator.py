import json
import json5
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest import mock
import os

import rpp_plugin_registrator
from rpp_plugin_registrator.library_manager import LibraryManager
from rpp_plugin_registrator import registry_config as rp
from rpp_plugin_registrator.plugin_validators.dispatch import PluginValidationResult, PluginValidationData
import rpp_plugin_registrator.registry_config


#TODO: Fix this
RPP_TESTING_PATH = Path(__file__).parent.parent.parent.resolve() \
    / "rpp_testing" / "rpp_testing"
EXAMPLES_DATA_PATH = RPP_TESTING_PATH / "data"

class LibraryManagerTests(unittest.TestCase):
    def setUp(self):
        self._home_dir = tempfile.TemporaryDirectory()
        self.home = Path(self._home_dir.name)
        self.home.mkdir(parents=True, exist_ok=True)
        self._original_rpp_home = rp.RPP_HOME
        rp.RPP_HOME = self.home

        # dissable unnecessary scaffolding
        import rpp_plugin_registrator.plugin_type_registrator
        rpp_plugin_registrator.plugin_type_registrator.SCAFFOLD_LANGUAGES = ['python']

    def tearDown(self):
        self._home_dir.cleanup()
        rp.RPP_HOME = self._original_rpp_home
        import rpp_plugin_registrator.plugin_type_registrator
        rpp_plugin_registrator.plugin_type_registrator.reset_module()
        # clean up the environment variable after the test
        os.environ.pop("RPP_WHITELIST_PLUGIN_TYPES", None)

    def test_library_manager_starts_with_empty_registry(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            manager = LibraryManager(rpp_home=temp_root / ".rpp")
            plugins = manager.get_available_plugins()
            libraries = manager.list_plugin_libraries()
            self.assertIn("rpp_common", plugins)
            self.assertIn("rpp_testing", plugins)
            self.assertTrue(any(lib["Name"] == "rpp_common" for lib in libraries))
            self.assertTrue(any(lib["Name"] == "rpp_testing" for lib in libraries))



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

            self.assertIn("PluginTypes", manifest_payload)
            self.assertIn("TestLib::ControlType", manifest_payload["PluginTypes"])
            registry_plugin_type_file = \
                manifest_payload["PluginTypes"]["TestLib::ControlType"]["RegistryPluginTypeFile"]
            abs_path = rp.get_app_registry_path() / registry_plugin_type_file

            self.assertTrue(abs_path.exists(), f"Expected registry plugin type file '{abs_path}' does not exist.")
            self.assertEqual(manifest_payload["PluginTypes"]["TestLib::ControlType"]["Library"], "TestLib")


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
                """from rpp_plugin_types.rpp_common import MotionController2D
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

            manifest_path = rp.get_app_library_manifest_path_json("TestLib")
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertIn("Plugins", manifest_payload)
            self.assertIn("TestLib::MyPlugin", manifest_payload["Plugins"])
            abs_path = manager.get_plugin_path_absolute(
                manifest_payload["Plugins"]["TestLib::MyPlugin"]["PluginPath"],
                "TestLib",
            )

            self.assertEqual(
                str(abs_path),
                str(plugin_path.resolve()),
            )
            self.assertEqual(manifest_payload["Plugins"]["TestLib::MyPlugin"]["Library"], "TestLib")


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
            self.assertEqual(library_info["Library"], "TestLib")
            self.assertEqual(library_info["Version"], "0.1.0")
            self.assertEqual(library_info["RosDependencies"], ["rclcpp>=2.0.0", "zlib>=1.2.11"])
            self.assertEqual(library_info["Dependencies"], ["rpp_common>=0.0.1"])

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

            self.assertEqual(library_info["Library"], "test_lib")
            self.assertEqual(library_info["Version"], "0.0.2")
            self.assertEqual(library_info["License"], "TestLicence")
            self.assertEqual(library_info["RosDependencies"], [
                "test_depend_ros_1",
                "test_depend_ros_2==0.0.2",
                "test_depend_ros_3<=0.0.3",
                "test_depend_ros_4>=0.0.4",
            ])
            self.assertEqual(library_info["Dependencies"], [
                "test_depend1",
                "test_depend2<0.0.5",
                "test_depend3>0.0.6",
            ])

class PythonPluginRegistratorTests(unittest.TestCase):
    def setUp(self):
        self._home_dir = tempfile.TemporaryDirectory()
        self.home = Path(self._home_dir.name)
        self.home.mkdir(parents=True, exist_ok=True)
        self._original_rpp_home = rp.RPP_HOME
        os.environ["RPP_WHITELIST_PLUGIN_TYPES"] = "rpp_testing::MotionController2D"
        rp.RPP_HOME = self.home
        self.manager = LibraryManager(rpp_home=self.home / ".rpp")

    def tearDown(self):
        self._home_dir.cleanup()
        rp.RPP_HOME = self._original_rpp_home
        os.environ.pop("RPP_WHITELIST_PLUGIN_TYPES", None)  # Clean up the environment variable after the test


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
        self.assertTrue(result)

        plugins = self.manager.get_available_plugins()
        self.assertIn("TestLib", plugins)
        self.assertIn("rpp_testing::MotionController2D", plugins["TestLib"])
        hello_item = self.manager.get_plugin_info_from_lib("TestLib::HelloPlugin")
        self.assertIsNotNone(hello_item)
        self.assertEqual(hello_item["Name"], "hello")
        self.assertEqual(hello_item["ClassName"], "HelloPlugin")
        self.assertEqual(hello_item["PluginType"], "rpp_testing::MotionController2D")
        self.assertEqual(hello_item["Library"], "TestLib")
        self.assertEqual(hello_item["FullyQualifiedClassName"], "<class 'hello_plugin.HelloPlugin'>")
        self.assertEqual(hello_item["PluginName"], "TestLib::HelloPlugin")
        self.assertEqual(hello_item["PluginTypeLibrary"], "rpp_testing")
        self.assertTrue("PluginTypeSharedLibraryPath" in hello_item)
        self.assertIsNone(hello_item.get("PluginSharedLibraryPath"))

        shared_lib_path = hello_item["PluginTypeSharedLibraryPath"]
        registry_path = rp.get_app_registry_path()
        self.assertTrue((registry_path / shared_lib_path).exists(),
                        f"Expected shared library '{shared_lib_path}' does not exist.")
        metadata = hello_item.get("PluginMetadata", {})
        self.assertIn("Parameters", metadata)
        self.assertIn("Components", metadata)
        self.assertEqual(metadata["Components"], {})
        self.assertEqual(metadata["Parameters"], {})

        libraries = self.manager.list_plugin_libraries()
        self.assertTrue(any(lib["Name"] == "TestLib" for lib in libraries))

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

        self.assertTrue(result)

        plugins = self.manager.get_available_plugins()
        plugin_items = [item for group in plugins["TestLib"].values() for item in group]
        fallback_item = next((item for item in plugin_items if item.get("PluginName") == "TestLib::FallbackPlugin"), None)
        self.assertIsNotNone(fallback_item)
        self.assertEqual(fallback_item["PluginType"], "rpp_testing::MotionController2D")
        self.assertEqual(fallback_item["PluginTypeLibrary"], "rpp_testing")
        self.assertEqual(fallback_item["PluginName"], "TestLib::FallbackPlugin")

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
            self.assertIn("Failed to import plugin class from", str(e))

        self.assertTrue(did_throw, "Expected ValueError was not raised for invalid plugin type.")

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

        self.assertIn("Plugins", manifest_payload)
        self.assertIn("TestLib::ComponentPlugin", manifest_payload["Plugins"])
        abs_path = self.manager.get_plugin_path_absolute(
            manifest_payload["Plugins"]["TestLib::ComponentPlugin"]["PluginPath"],
            "TestLib",
        )
        self.assertEqual(
            str(abs_path),
            str(plugin_path.resolve()),
        )

        comps = self.manager.get_plugin_components_from_lib("ComponentPlugin", "TestLib")
        self.assertEqual(comps, {"ctl1": "TestLib::ComponentPlugin"})

        params = self.manager.get_plugin_parameters_from_lib("ComponentPlugin", "TestLib")
        self.assertEqual(params["param1"], {"name": "param1", "default_value": 1.1, "type": "float64"})
        self.assertEqual(params["param2"], {"name": "param2", "default_value": 2, "type": "int64"})
        self.assertEqual(params["param3"], {"name": "param3", "default_value": "default_string", "type": "string"})
        self.assertEqual(params["param4"], {"name": "param4", "default_value": True, "type": "bool"})
        self.assertEqual(params["param5"]["type"], "list")
        self.assertEqual(params["param5"]["default_value"], [
            {"name": "param5[0]", "default_value": 1, "type": "int64"},
            {"name": "param5[1]", "default_value": 2, "type": "int64"},
            {"name": "param5[2]", "default_value": 3, "type": "int64"},
        ])
        self.assertEqual(params["param5"]["element_type"], "int64")
        self.assertEqual(params["param6"]["type"], "dict")
        self.assertEqual(params["param6"]["fields"], {
            "key1": {"name": "key1", "default_value": "value1", "type": "string"},
            "key2": {"name": "key2", "default_value": 2, "type": "int64"},
        })
        self.assertEqual(params["param7"]["type"], "dict")
        self.assertEqual(params["param7"]["fields"], {
            "a": {"name": "a", "default_value": 10, "type": "int64"},
            "b": {"name": "b", "default_value": 2, "type": "int64"},
        })

class CppPluginRegistratorTests(unittest.TestCase):


    def tearDown(self):
        os.environ.pop("RPP_WHITELIST_PLUGIN_TYPES", None)  # Clean up the environment variable after the test
        rpp_plugin_registrator.registry_config.reset_module()

    def test_register_cpp_plugin_with_components(self):
        with tempfile.TemporaryDirectory() as td:

            temp_root = Path(td)
            os.environ["RPP_WHITELIST_PLUGIN_TYPES"] = "rpp_testing::MotionController2D"
            manager = LibraryManager(rpp_home=temp_root / ".rpp")
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

            self.assertIn("Plugins", manifest_payload)
            self.assertIn("TestLib::ComponentPluginSimpleCpp", manifest_payload["Plugins"])
            abs_path = manager.get_plugin_path_absolute(
                manifest_payload["Plugins"]["TestLib::ComponentPluginSimpleCpp"]["PluginPath"],
                "TestLib",
            )
            self.assertEqual(
                str(abs_path),
                str(plugin_path.resolve()),
            )

            so_path = rp.get_app_registry_path() / "cpp" / "shared" / "TestLib" / "plugins" / "ComponentPluginSimpleCpp.so"
            self.assertTrue(so_path.exists(), f"Expected shared library '{so_path}' does not exist.")


    def test_register_cpp_plugin_with_using_namespace_and_type_aliasing(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            os.environ["RPP_WHITELIST_PLUGIN_TYPES"] = "rpp_testing::MotionController2D"
            manager = LibraryManager(rpp_home=temp_root / ".rpp")
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

                self.assertIn("Plugins", manifest_payload)
                self.assertIn(f"TestLib::{class_name}", manifest_payload["Plugins"])
                abs_path = manager.get_plugin_path_absolute(
                    manifest_payload["Plugins"][f"TestLib::{class_name}"]["PluginPath"],
                    "TestLib",
                )
                self.assertEqual(
                    str(abs_path),
                    str(plugin_path.resolve()),
                )


            load_and_test("example_plugin_with_using_namespace.cpp", "ComponentPluginWithUsingNamespace")
            load_and_test("example_plugin_with_type_alias_outside_class.cpp", "ComponentPluginWithTypeAliasOutsideClass")
            load_and_test("example_plugin_with_type_alias_in_class.cpp", "ComponentPluginWithTypeAliasInClass")

    def test_register_cpp_plugin_with_library_dependencies(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            os.environ["RPP_WHITELIST_PLUGIN_TYPES"] = "rpp_testing::MotionController2D"
            manager = LibraryManager(rpp_home=temp_root / ".rpp")
            rpp_plugin_registrator.registry_config.set_to_config("USE_ROS2_COMPILATION", "True")
            manager.get_or_create_plugin_library("rpp_testing")
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

            self.assertIn("Plugins", manifest_payload)
            self.assertIn("TestLib::ComponentPluginWithDependencies", manifest_payload["Plugins"])
            abs_path = manager.get_plugin_path_absolute(
                manifest_payload["Plugins"]["TestLib::ComponentPluginWithDependencies"]["PluginPath"],
                "TestLib",
            )
            self.assertEqual(
                str(abs_path),
                str(plugin_path.resolve()),
            )

            so_path = rp.get_app_registry_path() / "cpp" / "shared" / "TestLib" / "plugins" / "ComponentPluginWithDependencies.so"
            self.assertTrue(so_path.exists(), f"Expected shared library '{so_path}' does not exist.")


if __name__ == "__main__":
    unittest.main()