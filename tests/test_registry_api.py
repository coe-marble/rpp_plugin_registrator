import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def load_registry_api_module():
    registrator_root = Path(__file__).resolve().parents[1]
    if str(registrator_root) not in sys.path:
        sys.path.insert(0, str(registrator_root))

    import rpp_plugin_registrator.registry_api as registry_api

    return registry_api


class RegistryApiTests(unittest.TestCase):
    def setUp(self):
        self.registry_api = load_registry_api_module()

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

    def test_resolve_registry_path_prefers_explicit_path(self):
        with tempfile.TemporaryDirectory() as td:
            explicit = Path(td) / "my_registry.json"
            resolved = self.registry_api.resolve_registry_path(registry_path=explicit)
            self.assertEqual(resolved, explicit.resolve())

    def test_resolve_registry_path_uses_rpp_home_when_no_explicit_path(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            resolved = self.registry_api.resolve_registry_path(rpp_home=home)
            self.assertEqual(
                resolved,
                (home / "registry" / "rpp_plugins.registry.json").resolve(),
            )

    def test_load_registry_returns_default_payload_when_missing(self):
        with tempfile.TemporaryDirectory() as td:
            missing_path = Path(td) / "registry" / "rpp_plugins.registry.json"
            payload = self.registry_api.load_registry(registry_path=missing_path)
            self.assertEqual(payload, self.registry_api.default_registry_payload())

    def test_ensure_rpp_layout_creates_expected_directories(self):
        with tempfile.TemporaryDirectory() as td:
            original_home = self.registry_api.RPP_HOME
            self.registry_api.RPP_HOME = Path(td) / ".rpp"
            common_plugins_dir = Path(td) / "empty_common_plugins"
            common_plugins_dir.mkdir(parents=True, exist_ok=True)
            try:
                self.registry_api.ensure_rpp_layout(common_plugins_dir=common_plugins_dir)
                paths = self.registry_api.get_rpp_paths()
                self.assertTrue(paths["home"].exists())
                self.assertTrue(paths["descriptions"].exists())
                self.assertTrue(paths["interfaces"].exists())
                self.assertTrue(paths["registry"].parent.exists())
                self.assertTrue((paths["home"] / self.registry_api.INITIALIZED_MARKER_FILENAME).exists())
            finally:
                self.registry_api.RPP_HOME = original_home

    def test_ensure_rpp_layout_raises_when_common_plugins_resolution_fails(self):
        with tempfile.TemporaryDirectory() as td:
            original_home = self.registry_api.RPP_HOME
            self.registry_api.RPP_HOME = Path(td) / ".rpp"
            try:
                with mock.patch.object(self.registry_api.importlib, "import_module", side_effect=ImportError):
                    with self.assertRaises(RuntimeError):
                        self.registry_api.ensure_rpp_layout(common_plugins_dir=None)
            finally:
                self.registry_api.RPP_HOME = original_home

    def test_ensure_rpp_layout_initializes_common_plugins_and_writes_marker(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            common_plugins_dir = temp_root / "common_plugins"
            self._write_python_plugin_source(common_plugins_dir / "Controller.py", "Controller", "ctl", "controller")
            self._write_python_plugin_source(common_plugins_dir / "Estimator.py", "Estimator", "est", "estimator")

            original_home = self.registry_api.RPP_HOME
            self.registry_api.RPP_HOME = temp_root / ".rpp"
            try:
                self.registry_api.ensure_rpp_layout(common_plugins_dir=common_plugins_dir)
                paths = self.registry_api.get_rpp_paths()

                marker_path = paths["home"] / self.registry_api.INITIALIZED_MARKER_FILENAME
                self.assertTrue(marker_path.exists())
                marker_payload = json.loads(marker_path.read_text(encoding="utf-8"))
                self.assertTrue(marker_payload["Initialized"])
                self.assertEqual(set(marker_payload["InitializedPlugins"]), {"ctl", "est"})

                registry_payload = self.registry_api.load_registry(registry_path=paths["registry"])
                self.assertIn("ctl", registry_payload["Plugins"])
                self.assertIn("est", registry_payload["Plugins"])
                self.assertTrue((paths["descriptions"] / "ctl.plugin.json").exists())
                self.assertTrue((paths["descriptions"] / "est.plugin.json").exists())

                self.registry_api.ensure_rpp_layout(common_plugins_dir=common_plugins_dir)
                registry_payload_second = self.registry_api.load_registry(registry_path=paths["registry"])
                self.assertEqual(
                    sorted(registry_payload_second["Plugins"].keys()),
                    sorted(registry_payload["Plugins"].keys()),
                )
            finally:
                self.registry_api.RPP_HOME = original_home

    def test_ensure_rpp_layout_override_reinitializes_when_marker_exists(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            common_plugins_dir = temp_root / "common_plugins"
            self._write_python_plugin_source(common_plugins_dir / "Controller.py", "Controller", "ctl", "controller")

            original_home = self.registry_api.RPP_HOME
            self.registry_api.RPP_HOME = temp_root / ".rpp"
            try:
                self.registry_api.ensure_rpp_layout(common_plugins_dir=common_plugins_dir)
                paths = self.registry_api.get_rpp_paths()

                registry_payload = self.registry_api.load_registry(registry_path=paths["registry"])
                self.assertIn("ctl", registry_payload["Plugins"])

                del registry_payload["Plugins"]["ctl"]
                self.registry_api.write_json(paths["registry"], registry_payload)

                self.registry_api.ensure_rpp_layout(
                    common_plugins_dir=common_plugins_dir,
                    override_initialization=True,
                )
                registry_payload_after_override = self.registry_api.load_registry(registry_path=paths["registry"])
                self.assertIn("ctl", registry_payload_after_override["Plugins"])
            finally:
                self.registry_api.RPP_HOME = original_home

    def test_resolve_output_path_uses_override_or_default(self):
        with tempfile.TemporaryDirectory() as td:
            default_path = Path(td) / "default.json"
            explicit = Path(td) / "explicit.json"
            self.assertEqual(
                self.registry_api.resolve_output_path(str(explicit), default_path),
                explicit.resolve(),
            )
            self.assertEqual(
                self.registry_api.resolve_output_path(None, default_path),
                default_path.resolve(),
            )

    def test_get_plugin_tags_and_types(self):
        with tempfile.TemporaryDirectory() as td:
            registry_path = Path(td) / "registry" / "rpp_plugins.registry.json"
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            registry_path.write_text(
                json.dumps(
                    {
                        "SchemaVersion": 1,
                        "System": "rpp",
                        "Plugins": {
                            "ctl": {"ClassName": "Controller"},
                            "est": {"ClassName": "Estimator"},
                            "other": {"ClassName": "Controller"},
                        },
                    }
                ),
                encoding="utf-8",
            )

            tags = self.registry_api.get_plugin_tags(registry_path=registry_path)
            types = self.registry_api.get_plugin_types(registry_path=registry_path)

            self.assertEqual(tags, ["ctl", "est", "other"])
            self.assertEqual(types, ["Controller", "Estimator"])

    def test_register_description_persists_plugin_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            description_path = temp_root / "descriptions" / "echo.plugin.json"
            registry_path = temp_root / "registry" / "rpp_plugins.registry.json"

            self._write_description(
                path=description_path,
                plugin_id="echo",
                class_name="EchoPlugin",
                name="echo",
            )

            self.registry_api.register_description(description_path, registry_path)
            payload = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertIn("echo", payload["Plugins"])
            self.assertEqual(
                payload["Plugins"]["echo"]["DescriptionFile"],
                str(description_path),
            )
            self.assertEqual(payload["Plugins"]["echo"]["ClassName"], "EchoPlugin")

    def test_register_description_rejects_missing_plugin_id(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            description_path = temp_root / "descriptions" / "broken.plugin.json"
            registry_path = temp_root / "registry" / "rpp_plugins.registry.json"
            description_path.parent.mkdir(parents=True, exist_ok=True)
            description_path.write_text(
                json.dumps({"Plugin": {"Name": "broken"}}),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                self.registry_api.register_description(description_path, registry_path)

    def test_register_description_rejects_duplicate_plugin_id(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            registry_path = temp_root / "registry" / "rpp_plugins.registry.json"
            first = temp_root / "descriptions" / "first.plugin.json"
            second = temp_root / "descriptions" / "second.plugin.json"

            self._write_description(first, plugin_id="dup", class_name="FirstClass")
            self._write_description(second, plugin_id="dup", class_name="SecondClass")

            self.registry_api.register_description(first, registry_path)
            with self.assertRaises(ValueError):
                self.registry_api.register_description(second, registry_path)

    def test_register_description_rejects_duplicate_class_name(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            registry_path = temp_root / "registry" / "rpp_plugins.registry.json"
            first = temp_root / "descriptions" / "first.plugin.json"
            second = temp_root / "descriptions" / "second.plugin.json"

            self._write_description(first, plugin_id="one", class_name="SharedClass")
            self._write_description(second, plugin_id="two", class_name="SharedClass")

            self.registry_api.register_description(first, registry_path)
            with self.assertRaises(ValueError):
                self.registry_api.register_description(second, registry_path)

    def test_register_descriptions_in_folder_uses_plugin_extension_first(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            folder = temp_root / "descriptions"
            registry_path = temp_root / "registry" / "rpp_plugins.registry.json"

            plugin_file = folder / "plugin_only.plugin.json"
            plain_json = folder / "ignored.json"
            self._write_description(plugin_file, plugin_id="plugin_only", class_name="PluginOnly")
            self._write_description(plain_json, plugin_id="ignored", class_name="Ignored")

            registered = self.registry_api.register_descriptions_in_folder(folder, registry_path)
            self.assertEqual(registered, [plugin_file.resolve()])

            payload = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertIn("plugin_only", payload["Plugins"])
            self.assertNotIn("ignored", payload["Plugins"])

    def test_register_descriptions_in_folder_handles_empty_and_invalid_folder(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            empty_folder = temp_root / "empty"
            empty_folder.mkdir(parents=True, exist_ok=True)
            registry_path = temp_root / "registry" / "rpp_plugins.registry.json"

            self.assertEqual(
                self.registry_api.register_descriptions_in_folder(empty_folder, registry_path),
                [],
            )

            missing_folder = temp_root / "missing"
            with self.assertRaises(ValueError):
                self.registry_api.register_descriptions_in_folder(missing_folder, registry_path)

    def test_unregister_plugin_and_list_registered_plugins(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            registry_path = temp_root / "registry" / "rpp_plugins.registry.json"
            description_path = temp_root / "descriptions" / "item.plugin.json"
            self._write_description(description_path, plugin_id="item", class_name="ItemPlugin")
            self.registry_api.register_description(description_path, registry_path)

            self.assertFalse(self.registry_api.unregister_plugin("missing", registry_path))
            self.assertTrue(self.registry_api.unregister_plugin("item", registry_path))
            self.assertFalse(self.registry_api.unregister_plugin("item", registry_path))

            listed = self.registry_api.list_registered_plugins(registry_path)
            self.assertEqual(listed["Plugins"], {})

            missing_registry = temp_root / "registry" / "never_created.json"
            missing_list = self.registry_api.list_registered_plugins(missing_registry)
            self.assertEqual(missing_list, self.registry_api.default_registry_payload())


if __name__ == "__main__":
    unittest.main()