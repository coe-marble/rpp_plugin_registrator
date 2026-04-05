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
                rp.resolve_output_path(str(explicit), default_path),
                explicit.resolve(),
            )
            self.assertEqual(
                rp.resolve_output_path(None, default_path),
                default_path.resolve(),
            )

    def test_get_plugin_types(self):
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

                types = registry_api.get_plugin_types()
                class_names = [entry["ClassName"] for entry in types.values()]

            self.assertEqual(class_names, ["Controller", "Estimator", "Controller"])

    def test_register_plugin_type_persists_plugin_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            with self._temp_rpp_home(Path(td) / ".rpp"):
                temp_root = Path(td)
                source_path = temp_root / "plugins" / "EchoPlugin.py"
                registry_path = rp.get_app_registry_path()

                self._write_python_plugin_source(
                    path=source_path,
                    class_name="EchoPlugin",
                    tag="echo",
                    plugin_name="echo",
                )

                entry = registry_api.register_plugin_type_from_source(
                    source_path,
                    library=self.TEST_LIBRARY,
                )
                payload = json.loads(registry_path.read_text(encoding="utf-8"))
                # Entry should be in the registry
                self.assertEqual(entry["DescriptionFile"], str(source_path.resolve()))
                self.assertEqual(entry["ClassName"], "EchoPlugin")
                # Verify it's persisted in registry under the correct ID
                plugin_types = payload["PluginTypes"]
                self.assertTrue(any(pt["ClassName"] == "EchoPlugin" for pt in plugin_types.values()))

    def test_register_plugin_type_from_source_registers_python_plugin(self):
        with tempfile.TemporaryDirectory() as td:
            with self._temp_rpp_home(Path(td) / ".rpp"):
                temp_root = Path(td)
                source_path = temp_root / "plugins" / "EchoPlugin.py"
                registry_path = rp.get_app_registry_path()

                self._write_python_plugin_source(
                    path=source_path,
                    class_name="EchoPlugin",
                    tag="echo",
                    plugin_name="echo",
                )

                entry = registry_api.register_plugin_type_from_source(
                    source_path,
                    library=self.TEST_LIBRARY,
                )

                self.assertEqual(entry["DescriptionFile"], str(source_path.resolve()))
                self.assertEqual(entry["Library"], self.TEST_LIBRARY)
                self.assertEqual(entry["ClassName"], "EchoPlugin")
                payload = json.loads(registry_path.read_text(encoding="utf-8"))
                # Verify entry is in registry
                plugin_types = payload["PluginTypes"]
                self.assertTrue(any(pt["ClassName"] == "EchoPlugin" for pt in plugin_types.values()))

    def test_register_plugin_type_rejects_duplicate_class_name(self):
        with tempfile.TemporaryDirectory() as td:
            with self._temp_rpp_home(Path(td) / ".rpp"):
                temp_root = Path(td)
                registry_path = rp.get_app_registry_path()
                first_source = temp_root / "plugins" / "FirstPlugin.py"
                second_source = temp_root / "plugins" / "SecondPlugin.py"

                self._write_python_plugin_source(
                    first_source,
                    class_name="SharedClass",
                    tag="first_tag",
                    plugin_name="first",
                )
                self._write_python_plugin_source(
                    second_source,
                    class_name="SharedClass",
                    tag="second_tag",
                    plugin_name="second",
                )

                # First plugin should register successfully
                registry_api.register_plugin_type_from_source(first_source, library=self.TEST_LIBRARY)

                # Second plugin with same class name should fail
                with self.assertRaises(ValueError):
                    registry_api.register_plugin_type_from_source(second_source, library=self.TEST_LIBRARY)


    def test_unregister_plugin_type_and_list_registered_plugin_types(self):
        with tempfile.TemporaryDirectory() as td:
            with self._temp_rpp_home(Path(td) / ".rpp"):
                temp_root = Path(td)
                registry_path = rp.get_app_registry_path()
                source_path = temp_root / "plugins" / "ItemPlugin.py"
                self._write_python_plugin_source(
                    source_path,
                    class_name="ItemPlugin",
                    tag="item",
                    plugin_name="item",
                )
                registry_api.register_plugin_type_from_source(source_path, library=self.TEST_LIBRARY)

                self.assertFalse(registry_api.unregister_plugin_type("missing", registry_path, library=self.TEST_LIBRARY))
                # ID is derived from library_classname in snake_case: testlib_item_plugin
                self.assertTrue(registry_api.unregister_plugin_type("testlib_item_plugin", registry_path, library=self.TEST_LIBRARY))
                self.assertFalse(registry_api.unregister_plugin_type("testlib_item_plugin", registry_path, library=self.TEST_LIBRARY))

                listed = registry_api.list_registered_plugin_types(registry_path)
                self.assertEqual(listed["PluginTypes"], {})

                missing_registry = temp_root / "registry" / "never_created.json"
                missing_list = registry_api.list_registered_plugin_types(missing_registry)
                self.assertEqual(missing_list, registry_api.default_registry_payload())


if __name__ == "__main__":
    unittest.main()