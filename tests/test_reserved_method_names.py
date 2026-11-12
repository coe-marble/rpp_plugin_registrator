"""Plugin type methods that collide with names the generated adapters define."""

from pathlib import Path
from types import SimpleNamespace

import capnp
import pytest
import rpp_common

from rpp_plugin_registrator import plugin_type_registrator as registrator
from rpp_plugin_registrator.plugin_descriptors import capnp as descriptor
from rpp_plugin_registrator.plugin_descriptors import core


@pytest.fixture
def register(tmp_path, monkeypatch):
    monkeypatch.setattr(registrator, "library_exists", lambda library: True)
    monkeypatch.setattr(registrator, "load_registry", lambda: {})
    # Reaching the payload builder means the method names were accepted.
    monkeypatch.setattr(
        registrator, "build_plugin_type_info_payload",
        lambda *arguments: (_ for _ in ()).throw(RuntimeError("names accepted")))

    def register_schema(schema_text):
        source = tmp_path / "probe.capnp"
        source.write_text(schema_text, encoding="utf-8")
        imports = [str(Path(rpp_common.__file__).parent / "common_plugin_types")]
        parser = capnp.SchemaParser()
        loaded = parser.load(str(source), imports=imports)
        monkeypatch.setattr(descriptor, "load_capnp_schema_from_file",
                            lambda *args, **kwargs: (parser, loaded))
        return registrator.register_plugin_type_from_source(source, "demo")
    return register_schema


def schema_with_method(method_name):
    return f'''@0xe41a9c2b7f6d0a31;
using Anot = import "/rpp_common/anot.capnp";
interface Probe $Anot.plugin("Probe") {{
  check @0 (value :Float64) -> ();
  {method_name} @1 () -> ();
}}
'''


class TestReservedMethodNames:
    def test_reset_is_rejected_with_method_and_plugin_type(self, register) -> None:
        with pytest.raises(ValueError) as error:
            register(schema_with_method("reset"))

        assert "'reset'" in str(error.value)
        assert "demo::Probe" in str(error.value)
        assert "reserved" in str(error.value)

    def test_other_plugin_base_class_name_is_rejected(self, register) -> None:
        with pytest.raises(ValueError, match="'cleanup'"):
            register(schema_with_method("cleanup"))

    def test_ordinary_method_name_is_accepted(self, register) -> None:
        with pytest.raises(RuntimeError, match="names accepted"):
            register(schema_with_method("calibrate"))

    def test_every_reserved_name_is_rejected(self, register, monkeypatch) -> None:
        for name in sorted(core.RESERVED_METHOD_NAMES):
            interface = SimpleNamespace(methods=[SimpleNamespace(name=name)])
            data = SimpleNamespace(
                source_language="capnp", interfaces={"Probe": interface},
                plugins=[SimpleNamespace(interface_name="Probe", plugin_name="Probe")])
            monkeypatch.setattr(
                "rpp_plugin_registrator.plugin_descriptors.parse_plugin_type_file",
                lambda source, plugin_id_override=None: SimpleNamespace(
                    is_valid=True, data=data))

            with pytest.raises(ValueError, match=f"'{name}'"):
                registrator.register_plugin_type_from_source(Path("probe.capnp"), "demo")
