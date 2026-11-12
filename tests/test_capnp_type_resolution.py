"""Resolve imported and bound generic types through pycapnp field schemas."""

from types import SimpleNamespace

import capnp
import pytest

from rpp_plugin_registrator.plugin_descriptors import capnp as descriptor
from rpp_plugin_registrator.plugin_scaffold.python_scaffold import (
    create_method_prototype_string, parse_field_type,
)


@pytest.fixture
def schema(tmp_path, monkeypatch):
    imported = tmp_path / "external" / "common.capnp"
    imported.parent.mkdir()
    imported.write_text('''@0xe2f9bd2dbb2c7431;
struct Point { value @0 :Float64; }
''', encoding="utf-8")
    source = tmp_path / "consumer.capnp"
    source.write_text('''@0xc835a539c12d681f;
using Imported = import "external/common.capnp";
struct Local { text @0 :Text; }
struct Container {
  point @0 :Imported.Point;
  points @1 :List(Imported.Point);
  nested @2 :List(List(Imported.Point));
  numbers @3 :List(Float64);
  local @4 :Local;
}
interface Service {
  call @0 (point :Imported.Point, points :List(List(Imported.Point)),
           numbers :List(Float64)) -> (point :Imported.Point);
}
interface Generic(State) {
  step @0 (state :State) -> (state :State);
}
interface Concrete extends(Generic(Imported.Point)) {}
''', encoding="utf-8")
    parser = capnp.SchemaParser()
    loaded = parser.load(str(source))
    monkeypatch.setattr(descriptor, "load_capnp_schema_from_file",
                        lambda *args, **kwargs: (parser, loaded))
    return source, parser, loaded


def test_imported_struct_fields_and_lists_resolve_without_python_modules(schema):
    source, parser, loaded = schema
    type_id = loaded.Container.schema.fields["point"].proto.slot.type.struct.typeId
    assert type_id not in parser.modules_by_id

    result = descriptor.parse_capnp_plugin(source, None, relative_to_source=False)

    assert result.is_valid, result.message
    fields = {field.name: field.type for field in result.data.structs["Container"].fields}
    point = fields["point"]
    assert point.kind == "struct"
    assert point.name == "Point"
    assert point.capnp_type_display_name == "external/common.capnp:Point"
    assert fields["points"].element_type == point
    assert fields["nested"].element_type.element_type == point
    assert fields["numbers"].element_type.kind == "primitive"
    assert fields["numbers"].element_type.name == "float64"
    assert fields["local"].name == "Local"
    assert result.data.dependencies.count(("external", "common.capnp")) == 1

    method = result.data.interfaces["Service"].methods[0]
    params = {param.name: param.type for param in method.params}
    assert params["point"] == point
    assert params["points"].element_type.element_type == point
    assert params["numbers"].element_type.name == "float64"
    assert method.results[0].type == point


def test_bound_generic_interface_uses_concrete_field_schemas(schema):
    source, _, loaded = schema
    inherited = loaded.Concrete.schema.methods_inherited["step"]
    assert inherited.param_type.fields["state"].proto.slot.type.which() == "anyPointer"

    result = descriptor.parse_capnp_plugin(source, None, relative_to_source=False)

    assert result.is_valid, result.message
    method = result.data.interfaces["Concrete"].methods[0]
    params = {param.name: param.type for param in method.params}
    assert params["state"].kind == "struct"
    assert params["state"].name == "Point"
    assert method.results[0].type == params["state"]
    prototype, _ = create_method_prototype_string(method, "consumer")
    assert "state: Point" in prototype
    assert "-> Point" in prototype


def test_unresolved_struct_id_reports_the_type_id():
    with pytest.raises(ValueError, match="Cannot resolve Cap'n Proto struct type ID 0xdead"):
        descriptor.parse_capnp_plugin_type_from_type_dict(
            {"struct": {"typeId": 0xdead}}, SimpleNamespace(modules_by_id={}), [])


@pytest.mark.parametrize("raw_type", [
    {"float64": None},
    {"list": {"elementType": {"float64": None}}},
    {"list": {"elementType": {"list": {"elementType": {"bool": None}}}}},
])
def test_primitive_types_do_not_require_pycapnp_resolved_schemas(raw_type):
    assert not descriptor._type_needs_resolved_schema(raw_type)


def test_imported_and_generic_types_require_pycapnp_resolved_schemas():
    assert descriptor._type_needs_resolved_schema({"struct": {"typeId": 1}})
    assert descriptor._type_needs_resolved_schema({"anyPointer": {}})
    assert descriptor._type_needs_resolved_schema({
        "list": {"elementType": {"struct": {"typeId": 1}}},
    })


def test_unsupported_primitive_names_are_reported():
    with pytest.raises(ValueError, match="Unsupported primitive type 'anyPointer'"):
        parse_field_type({"Kind": "primitive", "Name": "anyPointer"}, "consumer")
