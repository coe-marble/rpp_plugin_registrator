from rpp_plugin_registrator.payload_builders import (
    build_library_manifest_plugin_entry,
    build_plugin_info_payload,
    build_registry_plugin_entry,
)
from rpp_plugin_registrator.plugin_descriptors.core import build_base_plugin_description
from rpp_plugin_registrator.plugin_descriptors.python import parse_python_plugin


def test_plugin_metadata_has_no_casadi_flag(tmp_path):
    source = tmp_path / "plugin.py"
    source.write_text('''
class Plugin(Base):
    def step(self, value: float) -> float:
        return value
''', encoding="utf-8")

    parsed = parse_python_plugin(source, None)
    assert parsed.is_valid
    assert "IsCasadi" not in parsed.data.plugins[0]

    base = build_base_plugin_description(
        name="Plugin", language="python", source_file=source,
        class_name="Plugin", base_class_name="Base", base_classes=["Base"],
        description="No description provided.")
    assert "IsCasadi" not in base

    info = build_plugin_info_payload(
        name="Plugin", plugin_name="plugin", library="lib",
        source_language="python", source_file="plugin.py")
    assert "IsCasadi" not in info
    assert "IsCasadi" not in build_registry_plugin_entry(info)
    entry = build_library_manifest_plugin_entry({
        **info, "PluginType": "lib::Type", "PluginTypeLibrary": "lib"})
    assert "IsCasadi" not in entry
