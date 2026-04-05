import importlib
import json
import json5
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from rpp_plugin_registrator.library_manager import LibraryManager
from rpp_plugin_registrator import registry_paths as rp


class RegistryBackendTests(unittest.TestCase):
    def setUp(self):
        self._home_dir = tempfile.TemporaryDirectory()
        self.home = Path(self._home_dir.name)
        self.home.mkdir(parents=True, exist_ok=True)
        self._original_rpp_home = rp.RPP_HOME
        rp.RPP_HOME = self.home

    def tearDown(self):
        self._home_dir.cleanup()
        rp.RPP_HOME = self._original_rpp_home

    def test_backend_starts_with_empty_registry(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            manager = LibraryManager(rpp_home=temp_root / ".rpp")
            plugins = manager.get_available_plugins()
            libraries = manager.list_component_libraries()
            self.assertIn("rpp", plugins)
            self.assertTrue(any(lib["Name"] == "rpp" for lib in libraries))

    def test_gui_main_passes_ui_path_to_window(self):
        registrator_root = Path(__file__).resolve().parents[1]
        if str(registrator_root) not in sys.path:
            sys.path.insert(0, str(registrator_root))

        import rpp_plugin_registrator.gui as gui_module

        fake_app = mock.Mock()
        fake_app.exec.return_value = 0
        fake_window = mock.Mock()

        with mock.patch.object(gui_module, "QApplication", return_value=fake_app) as app_cls, \
            mock.patch.object(gui_module, "CSBPluginManager", return_value=fake_window) as window_cls:
            result = gui_module.main()

        app_cls.assert_called_once()
        window_cls.assert_called_once()
        _, kwargs = window_cls.call_args
        self.assertIn("ui_path", kwargs)
        self.assertNotIn("parent", kwargs)
        self.assertTrue(str(kwargs["ui_path"]).endswith("ui"))
        fake_window.show.assert_called_once_with()
        fake_app.exec.assert_called_once_with()
        self.assertEqual(result, 0)

    def test_register_component_from_python_file_groups_by_library(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            manager = LibraryManager(rpp_home=temp_root / ".rpp")
            manager.get_or_create_component_library("TestLib")

            plugin_source = temp_root / "hello_plugin.py"
            plugin_source.write_text(
                """
from rpp_common import RPP_Plugin


class HelloPlugin(RPP_Plugin):
    tag = "hello"

    def name(self) -> str:
        return "hello"

    def execute(self, input: str) -> str:
        return input
""".strip()
                + "\n",
                encoding="utf-8",
            )

            result = manager.register_component_from_file(plugin_source, "TestLib")
            self.assertTrue(result)

            plugins = manager.get_available_plugins()
            self.assertIn("TestLib", plugins)
            plugin_items = [item for group in plugins["TestLib"].values() for item in group]
            hello_item = next((item for item in plugin_items if item.get("T") == "HelloPlugin"), None)
            self.assertIsNotNone(hello_item)
            self.assertEqual(hello_item["Name"], "HelloPlugin")
            self.assertEqual(hello_item["T"], "HelloPlugin")

            libraries = manager.list_component_libraries()
            self.assertTrue(any(lib["Name"] == "TestLib" for lib in libraries))

    def test_refresh_component_library_includes_custom_plugin_types_in_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            manager = LibraryManager(rpp_home=temp_root / ".rpp")
            manager.get_or_create_component_library("TestLib")

            library_root = temp_root / ".rpp" / "libraries" / "TestLib"
            plugin_type_dir = library_root / "plugin_types"
            plugin_type_dir.mkdir(parents=True, exist_ok=True)

            descriptor_path = plugin_type_dir / "Control.plugin.json"
            descriptor_path.write_text(
                json.dumps(
                    {
                        "Plugin": {
                            "Id": "ctl_custom",
                            "Tag": "ctl_custom",
                            "Name": "Control",
                            "SourceLanguage": "python",
                            "ClassName": "ControlType",
                            "Library": "TestLib",
                        }
                    }
                ),
                encoding="utf-8",
            )

            plugins_path = library_root / "plugins.json"
            plugins_payload = json5.loads(plugins_path.read_text(encoding="utf-8"))
            plugins_payload["PluginTypes"] = [
                {
                    "Name": "Control",
                    "Path": "plugin_types/Control.plugin.json",
                    "Type": "file",
                }
            ]
            plugins_path.write_text(json.dumps(plugins_payload, indent=2) + "\n", encoding="utf-8")

            manager.refresh_component_library("TestLib")

            manifest_path = library_root / "autogen" / "manifest.json"
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertIn("PluginTypes", manifest_payload)
            self.assertIn("ctl_custom", manifest_payload["PluginTypes"])
            self.assertEqual(
                manifest_payload["PluginTypes"]["ctl_custom"]["DescriptionFile"],
                str(descriptor_path.resolve()),
            )
            self.assertEqual(manifest_payload["PluginTypes"]["ctl_custom"]["Library"], "TestLib")




if __name__ == "__main__":
    unittest.main()