"""A plugin-type file with interfaces but no $Anot.plugin annotation is rejected."""

import capnp
import pytest

from rpp_plugin_registrator import plugin_type_registrator as registrator
from rpp_plugin_registrator.plugin_descriptors import capnp as descriptor


@pytest.fixture
def register(tmp_path, monkeypatch):
    monkeypatch.setattr(registrator, "library_exists", lambda library: True)
    monkeypatch.setattr(registrator, "load_registry", lambda: {})
    monkeypatch.setattr(registrator, "register_plugin_type_supporting_file",
                        lambda *arguments: None)
    monkeypatch.setattr(registrator, "write_json", lambda *arguments: None)
    monkeypatch.setattr(registrator.rp, "get_app_registry_json_path",
                        lambda: tmp_path / "registry.json")

    def register_schema(schema_text):
        source = tmp_path / "probe.capnp"
        source.write_text(schema_text, encoding="utf-8")
        parser = capnp.SchemaParser()
        loaded = parser.load(str(source))
        monkeypatch.setattr(descriptor, "load_capnp_schema_from_file",
                            lambda *args, **kwargs: (parser, loaded))
        return source, registrator.register_plugin_type_from_source(source, "demo")
    return register_schema


class TestUnannotatedInterface:
    def test_file_with_only_unannotated_interfaces_is_rejected(self, register) -> None:
        with pytest.raises(ValueError) as error:
            register('''@0xe41a9c2b7f6d0a21;
struct R { v @0 :Float64; }
interface Probe { check @0 (value :Float64) -> (out :R); }
interface Other { run @0 () -> (); }
''')

        assert "probe.capnp" in str(error.value)
        assert "'Probe'" in str(error.value)
        assert "'Other'" in str(error.value)
        assert "$Anot.plugin" in str(error.value)

    def test_file_with_only_structs_is_not_rejected(self, register) -> None:
        _, registered = register('''@0xe41a9c2b7f6d0a22;
struct R { v @0 :Float64; }
''')

        assert registered == []
