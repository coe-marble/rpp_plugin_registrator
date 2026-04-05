import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import rpp_plugin_registrator.plugin_type_registrator as registry_api
from rpp_plugin_registrator import registry_paths as rp


class RegistryApiTests(unittest.TestCase):
    TEST_LIBRARY = "testlib"

    @contextmanager
    def _temp_rpp_home(self, home: Path):
        original_home = rp.RPP_HOME
        rp.RPP_HOME = home
        rp.RPP_HOME.mkdir(parents=True, exist_ok=True)
        try:
            yield rp.RPP_HOME
        finally:
            rp.RPP_HOME = original_home

    def _write_description(
        self,
        path: Path,
        plugin_id: str,
        class_name: str = "TestPlugin",
        name: str = "test",
    ) -> None:
        payload = {
            "Plugin": {
                "Id": plugin_id,
                "Name": name,
                "SourceLanguage": "python",
                "ClassName": class_name,
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

    def _write_python_plugin_source(self, path: Path, class_name: str, tag: str, plugin_name: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            (
                "from rpp_common.py.RPP_Plugin import RPP_Plugin\n\n"
                f"class {class_name}(RPP_Plugin):\n"
                f"    tag = \"{tag}\"\n\n"
                "    def name(self) -> str:\n"
                f"        return \"{plugin_name}\"\n\n"
                "    def execute(self, input: str) -> str:\n"
                "        return input\n"
            ),
            encoding="utf-8",
        )

    def test_resolve_registry_path_uses_rpp_home_when_no_explicit_path(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / ".rpp"
            with self._temp_rpp_home(home):
                resolved = rp.get_app_registry_path()
                self.assertEqual(
                    resolved,
                    (home / "registry" / "rpp_plugin_types.registry.json").resolve(),
                )

    def test_load_registry_returns_default_payload_when_missing(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / ".rpp"
            with self._temp_rpp_home(home):
                payload = registry_api.load_registry()
                self.assertEqual(payload, registry_api.default_registry_payload())

    def test_ensure_rpp_layout_creates_expected_directories(self):
        with tempfile.TemporaryDirectory() as td:
            common_plugins_dir = Path(td) / "empty_common_plugins"
            common_plugins_dir.mkdir(parents=True, exist_ok=True)
            with self._temp_rpp_home(Path(td) / ".rpp"):
                registry_api.ensure_rpp_layout(common_plugins_dir=common_plugins_dir)
                paths = registry_api.get_rpp_paths()
                self.assertTrue(paths["home"].exists())
                self.assertTrue(paths["descriptions"].exists())
                self.assertTrue(paths["interfaces"].exists())
                self.assertTrue(paths["registry"].parent.exists())
                self.assertTrue((paths["home"] / registry_api.rp.INITIALIZED_MARKER_FILENAME).exists())

    def test_ensure_rpp_layout_raises_when_common_plugins_resolution_fails(self):
        with tempfile.TemporaryDirectory() as td:
            with self._temp_rpp_home(Path(td) / ".rpp"):
                with mock.patch.object(registry_api.importlib, "import_module", side_effect=ImportError):
                    with self.assertRaises(RuntimeError):
                        registry_api.ensure_rpp_layout(common_plugins_dir=None)

    def test_ensure_rpp_layout_initializes_common_plugins_and_writes_marker(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            common_plugins_dir = temp_root / "common_plugins"
            self._write_python_plugin_source(common_plugins_dir / "Controller.py", "Controller", "ctl", "controller")
            self._write_python_plugin_source(common_plugins_dir / "Estimator.py", "Estimator", "est", "estimator")

            with self._temp_rpp_home(temp_root / ".rpp"):
                registry_api.ensure_rpp_layout(common_plugins_dir=common_plugins_dir)
                paths = registry_api.get_rpp_paths()

                marker_path = paths["home"] / registry_api.rp.INITIALIZED_MARKER_FILENAME
                self.assertTrue(marker_path.exists())
                marker_payload = json.loads(marker_path.read_text(encoding="utf-8"))
                self.assertTrue(marker_payload["Initialized"])
                self.assertEqual(set(marker_payload["InitializedPlugins"]), {"rpp_controller", "rpp_estimator"})

                registry_payload = registry_api.load_registry()
                self.assertIn("rpp_controller", registry_payload["PluginTypes"])
                self.assertIn("rpp_estimator", registry_payload["PluginTypes"])
                self.assertEqual(registry_payload["PluginTypes"]["rpp_controller"]["Library"], "rpp")
                self.assertEqual(registry_payload["PluginTypes"]["rpp_estimator"]["Library"], "rpp")
                self.assertTrue((paths["descriptions"] / "rpp_controller.plugin.json").exists())
                self.assertTrue((paths["descriptions"] / "rpp_estimator.plugin.json").exists())

                rpp_library_path = paths["libraries"] / "rpp"
                self.assertTrue((rpp_library_path / "package.json").exists())
                self.assertTrue((rpp_library_path / "plugins.json").exists())
                self.assertTrue((rpp_library_path / "autogen" / "manifest.json").exists())

                manifest_payload = json.loads((rpp_library_path / "autogen" / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest_payload["Library"], "rpp")

                registry_api.ensure_rpp_layout(common_plugins_dir=common_plugins_dir)
                registry_payload_second = registry_api.load_registry()
                self.assertEqual(
                    sorted(registry_payload_second["PluginTypes"].keys()),
                    sorted(registry_payload["PluginTypes"].keys()),
                )

    def test_ensure_rpp_layout_override_reinitializes_when_marker_exists(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            common_plugins_dir = temp_root / "common_plugins"
            self._write_python_plugin_source(common_plugins_dir / "Controller.py", "Controller", "ctl", "controller")

            with self._temp_rpp_home(temp_root / ".rpp"):
                registry_api.ensure_rpp_layout(common_plugins_dir=common_plugins_dir)
                paths = registry_api.get_rpp_paths()

                registry_payload = registry_api.load_registry()
                self.assertIn("rpp_controller", registry_payload["PluginTypes"])

                del registry_payload["PluginTypes"]["rpp_controller"]
                registry_api.write_json(paths["registry"], registry_payload)

                registry_api.ensure_rpp_layout(
                    common_plugins_dir=common_plugins_dir,
                    override_initialization=True,
                )
                registry_payload_after_override = registry_api.load_registry()
                self.assertIn("rpp_controller", registry_payload_after_override["PluginTypes"])
                rpp_library_path = paths["libraries"] / "rpp"
                self.assertTrue((rpp_library_path / "autogen" / "manifest.json").exists())

    def test_resolve_output_path_uses_override_or_default(self):
        with tempfile.TemporaryDirectory() as td:
            default_path = Path(td) / "default.json"
            explicit = Path(td) / "explicit.json"
            self.assertEqual(
                registry_api.resolve_output_path(str(explicit), default_path),
                explicit.resolve(),
            )
            self.assertEqual(
                registry_api.resolve_output_path(None, default_path),
                default_path.resolve(),
            )

    def test_get_plugin_tags_and_types(self):
        with tempfile.TemporaryDirectory() as td:
            with self._temp_rpp_home(Path(td) / ".rpp"):
                registry_path = rp.get_app_registry_path()
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

                tags = registry_api.get_plugin_tags()
                types = registry_api.get_plugin_types()
                class_names = [entry["ClassName"] for entry in types.values()]

            self.assertEqual(tags, ["ctl", "est", "other"])
            self.assertEqual(class_names, ["Controller", "Estimator", "Controller"])

    def test_register_plugin_type_persists_plugin_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            description_path = temp_root / "descriptions" / "echo.plugin.json"
            registry_path = temp_root / "registry" / "rpp_plugin_types.registry.json"

            self._write_description(
                path=description_path,
                plugin_id="echo",
                class_name="EchoPlugin",
                name="echo",
            )

            registry_api.register_plugin_type(description_path, registry_path, library=self.TEST_LIBRARY)
            payload = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertIn("echo", payload["PluginTypes"])
            self.assertEqual(
                payload["PluginTypes"]["echo"]["DescriptionFile"],
                str(description_path),
            )
            self.assertEqual(payload["PluginTypes"]["echo"]["ClassName"], "EchoPlugin")

    def test_register_plugin_type_rejects_missing_plugin_id(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            description_path = temp_root / "descriptions" / "broken.plugin.json"
            registry_path = temp_root / "registry" / "rpp_plugin_types.registry.json"
            description_path.parent.mkdir(parents=True, exist_ok=True)
            description_path.write_text(
                json.dumps({"Plugin": {"Name": "broken"}}),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                registry_api.register_plugin_type(description_path, registry_path, library=self.TEST_LIBRARY)

    def test_register_plugin_type_rejects_duplicate_plugin_id(self):
        with tempfile.TemporaryDirectory() as td:
            with self._temp_rpp_home(Path(td) / ".rpp"):
                temp_root = Path(td)
                registry_path = rp.get_app_registry_path()
                first = temp_root / "descriptions" / "first.plugin.json"
                second = temp_root / "descriptions" / "second.plugin.json"

                self._write_description(first, plugin_id="dup", class_name="FirstClass")
                self._write_description(second, plugin_id="dup", class_name="SecondClass")

                registry_api.register_plugin_type(first, registry_path, library=self.TEST_LIBRARY)
                with self.assertRaises(ValueError):
                    registry_api.register_plugin_type(second, registry_path, library=self.TEST_LIBRARY)

    def test_register_plugin_type_rejects_duplicate_class_name(self):
        with tempfile.TemporaryDirectory() as td:
            with self._temp_rpp_home(Path(td) / ".rpp"):
                temp_root = Path(td)
                registry_path = rp.get_app_registry_path()
                first = temp_root / "descriptions" / "first.plugin.json"
                second = temp_root / "descriptions" / "second.plugin.json"

                self._write_description(first, plugin_id="one", class_name="SharedClass")
                self._write_description(second, plugin_id="two", class_name="SharedClass")

                registry_api.register_plugin_type(first, registry_path, library=self.TEST_LIBRARY)
                with self.assertRaises(ValueError):
                    registry_api.register_plugin_type(second, registry_path, library=self.TEST_LIBRARY)

    def test_register_plugin_types_in_folder_uses_plugin_extension_first(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            folder = temp_root / "descriptions"
            registry_path = temp_root / "registry" / "rpp_plugin_types.registry.json"

            plugin_file = folder / "plugin_only.plugin.json"
            plain_json = folder / "ignored.json"
            self._write_description(plugin_file, plugin_id="plugin_only", class_name="PluginOnly")
            self._write_description(plain_json, plugin_id="ignored", class_name="Ignored")

            registered = registry_api.register_plugin_types_in_folder(folder, registry_path, library=self.TEST_LIBRARY)
            self.assertEqual(registered, [plugin_file.resolve()])

            payload = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertIn("plugin_only", payload["PluginTypes"])
            self.assertNotIn("ignored", payload["PluginTypes"])

    def test_register_plugin_types_in_folder_handles_empty_and_invalid_folder(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            empty_folder = temp_root / "empty"
            empty_folder.mkdir(parents=True, exist_ok=True)
            registry_path = temp_root / "registry" / "rpp_plugin_types.registry.json"

            self.assertEqual(
                registry_api.register_plugin_types_in_folder(empty_folder, registry_path, library=self.TEST_LIBRARY),
                [],
            )

            missing_folder = temp_root / "missing"
            with self.assertRaises(ValueError):
                registry_api.register_plugin_types_in_folder(missing_folder, registry_path, library=self.TEST_LIBRARY)

    def test_unregister_plugin_type_and_list_registered_plugin_types(self):
        with tempfile.TemporaryDirectory() as td:
            with self._temp_rpp_home(Path(td) / ".rpp"):
                temp_root = Path(td)
                registry_path = rp.get_app_registry_path()
                description_path = temp_root / "descriptions" / "item.plugin.json"
                self._write_description(description_path, plugin_id="item", class_name="ItemPlugin")
                registry_api.register_plugin_type(description_path, registry_path, library=self.TEST_LIBRARY)

                self.assertFalse(registry_api.unregister_plugin_type("missing", registry_path, library=self.TEST_LIBRARY))
                self.assertTrue(registry_api.unregister_plugin_type("item", registry_path, library=self.TEST_LIBRARY))
                self.assertFalse(registry_api.unregister_plugin_type("item", registry_path, library=self.TEST_LIBRARY))

                listed = registry_api.list_registered_plugin_types(registry_path)
                self.assertEqual(listed["PluginTypes"], {})

                missing_registry = temp_root / "registry" / "never_created.json"
                missing_list = registry_api.list_registered_plugin_types(missing_registry)
                self.assertEqual(missing_list, registry_api.default_registry_payload())


if __name__ == "__main__":
    unittest.main()