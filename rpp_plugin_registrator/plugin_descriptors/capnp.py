from __future__ import annotations

import re, secrets
from dataclasses import replace
from pathlib import Path
import subprocess
from typing import Any, Dict, Optional, Tuple
from xml.dom.minidom import TypeInfo

import capnp

from ..registry_config import get_app_capnp_interfaces_path

from .core import (
    FieldInfo,
    InterfaceInfo,
    MethodInfo,
    ParsePluginTypeResult,
    ParsePluginTypeData,
    PluginTypeMetadata,
    StructInfo,
    TypeInfo,
    read_text,
)

PLUGIN_ANNOTATION_ID = "0xabcd000000000000"
LIFECYCLE_STATE_ANNOTATION_ID = "0xabcde00000000000"


def bind_lifecycle_state(interface, node, loaded):
    """Resolve an optional local struct binding without guessing type names."""
    bindings = [annotation.value.text for annotation in node.annotations
                if hex(annotation.id) == LIFECYCLE_STATE_ANNOTATION_ID]
    if not bindings:
        return interface
    name = bindings[0]
    state = getattr(loaded, name, None) if name.isidentifier() else None
    schema = getattr(state, "schema", None)
    if len(bindings) != 1 or schema is None or schema.node.which() != "struct" \
            or schema.node.isGeneric \
            or schema.node.displayName.split(":")[0] != node.displayName.split(":")[0]:
        raise ValueError(
            f"Interface {interface.name}: lifecycleState must name one non-generic "
            f"struct in the same schema file; got {name!r}")
    return replace(interface, lifecycle_state=TypeInfo(
        name=name, kind="struct", capnp_type_display_name=schema.node.displayName),
        lifecycle_state_schema_id=schema.node.id)

def overwrite_capnp_schema_id(source_text: str) -> str:
    schema_id = secrets.randbits(64) | (1 << 63)
    source_text_new_id = re.sub(r'@0x[0-9a-fA-F]+', f'@0x{schema_id:016x}', source_text, count=1)

    return source_text_new_id, schema_id

def check_if_capnp_type_is_plugin(plugin_type) -> bool:
    annotations = plugin_type.schema.node.annotations
    if len(annotations) == 0:
        return False, ""
    for annotation in annotations:
        id_hex = hex(annotation.id)
        if id_hex == PLUGIN_ANNOTATION_ID:
            plugin_name = annotation.value.text
            return True, plugin_name
    return False, ''

def parse_dependency(lib_and_file_name: str) -> Tuple[str, str] | None:
    if '/' in lib_and_file_name:
        lib_name, file_name = lib_and_file_name.split('/')
        return lib_name, Path(file_name).name
    return None

def _type_needs_resolved_schema(plugin_type: Dict[str, Any]) -> bool:
    """Whether raw Cap'n Proto metadata lacks the concrete field type."""
    if "struct" in plugin_type and plugin_type["struct"] is not None:
        return True
    if "anyPointer" in plugin_type and plugin_type["anyPointer"] is not None:
        return True
    if "list" in plugin_type and plugin_type["list"] is not None:
        element_type = plugin_type["list"].get("elementType")
        return isinstance(element_type, dict) and _type_needs_resolved_schema(
            element_type)
    return False


def parse_capnp_type_from_param(plugin_param: Dict[str, Any], parser, dependencies) -> TypeInfo:
    raw_type = plugin_param.proto.slot.type.to_dict()
    schema = None
    # pycapnp can raise "Schema type is unknown" for lists of primitives. Their
    # raw type is complete, so access the resolved schema only for imports and
    # generic bindings whose concrete struct identity cannot be read from proto.
    if _type_needs_resolved_schema(raw_type):
        try:
            schema = plugin_param.schema
        except capnp.KjException:
            schema = None
    result = parse_capnp_plugin_type_from_type_dict(
        raw_type, parser, dependencies, schema=schema)
    return replace(result, name=plugin_param.proto.name) if result.kind == "list" else result

def parse_capnp_plugin_type_from_type_dict(
        plugin_type: Dict[str, Any], parser, dependencies, *, schema=None) -> TypeInfo:
    is_list = "list" in plugin_type and plugin_type["list"] is not None
    if is_list:
        # Carry the resolved element schema through every list level so imported
        # structs and bound generic elements resolve just like direct fields.
        element_type = plugin_type["list"]["elementType"]
        if isinstance(element_type, dict):
            return TypeInfo(
                kind="list",
                name=None,
                element_type=parse_capnp_plugin_type_from_type_dict(
                    element_type, parser, dependencies,
                    schema=schema.elementType if schema is not None else None),
            )
        else:
            return TypeInfo(
                kind="list",
                name=element_type.name if hasattr(element_type, 'name') else None,
                element_type=parse_capnp_plugin_type_from_type_dict(
                    element_type.to_dict(), parser, dependencies,
                    schema=schema.elementType if schema is not None else None) \
                        if hasattr(element_type, 'to_dict') else None,
            )
    # Generic parameters keep an AnyPointer in the raw proto even after binding
    # to a concrete struct. The field schema carries that resolved binding.
    # For Controller(State) specialized with Msgs.Odometry2D, classify State
    # using this schema; AnyPointer is not a primitive Python/C++ field type.
    is_struct = (schema is not None and hasattr(schema, "fields_list")) or (
        "struct" in plugin_type and plugin_type["struct"] is not None)
    if is_struct:
        # modules_by_id indexes Python objects created by SchemaParser.load(),
        # not every schema loaded by the underlying Cap'n Proto parser. Imported
        # structs can be resolved in field.schema without a Python module entry.
        # Use the module table only as a fallback when no field schema is supplied.
        if schema is None:
            type_id = plugin_type["struct"]["typeId"]
            type_info = parser.modules_by_id.get(type_id)
            schema = getattr(type_info, "schema", None)
            if schema is None:
                raise ValueError(f"Cannot resolve Cap'n Proto struct type ID {type_id:#x}")
        type_display_name = schema.node.displayName
        name = type_display_name.split(':')[-1]

        lib_and_file_name = type_display_name.split(':')[0]
        dep = parse_dependency(lib_and_file_name)
        if dep and dep not in dependencies:
            dependencies.append(dep)

        return TypeInfo(
            kind="struct",
            name=name,
            capnp_type_display_name=type_display_name,
        )
    type_name = next(iter(plugin_type.keys()))
    return TypeInfo(
        name=type_name,
        kind="primitive",
    )

def build_struct_description(msg, struct_node, parser, dependencies) -> StructInfo:
    class_name = struct_node.displayName.split(':')[-1]
    fields = []
    for key, value in msg.schema.fields.items():
        field_name = key
        fields.append(FieldInfo(
            name=field_name,
            type=parse_capnp_type_from_param(value, parser, dependencies),
        ))
    return StructInfo(
        name=class_name,
        fields=fields,
    )


def build_interface_description(server_instance,
        interface_node, parser, dependencies) -> InterfaceInfo:
    class_name = interface_node.displayName.split(':')[-1]

    methods = {
        **server_instance.schema.methods_inherited,
        **server_instance.schema.methods
    }
    methods_info = []

    for method_name, method in methods.items():
        params = []
        results = []
        for param in method.param_type.fields_list:
            # try parse complex types. hasattr will raise an exception...
            param_type_info = parse_capnp_type_from_param(param, parser, dependencies)
            params.append(FieldInfo(
                name=param.proto.name,
                type=param_type_info,
            ))
        for result in method.result_type.fields_list:
            result_type_info = parse_capnp_type_from_param(result, parser, dependencies)
            results.append(FieldInfo(
                name=result.proto.name,
                type=result_type_info,
            ))
        methods_info.append(MethodInfo(
            name=method_name,
            params=params,
            results=results,
        ))

    return InterfaceInfo(
        name=class_name,
        methods=methods_info
    )

def load_capnp_schema_from_file(source_file: Path,
        relative_to_source: bool,
        with_random_schema_id: bool = True,
        use_global_parser: bool = False):

    import capnp

    if relative_to_source:
        root_dir = source_file.parent.parent
    else:
        root_dir = get_app_capnp_interfaces_path()

    dir_created = False
    if not root_dir.exists():
        root_dir.mkdir(parents=True, exist_ok=True)
        dir_created = True
    new_tmp_file = root_dir / source_file.name
    try:
        source_text = read_text(source_file)
        # Set a random schema ID to avoid collisions with other schemas.
        # First bit has to be 1, so we use 64 bits and set the first bit to 1.
        if with_random_schema_id:
            source_text_new_id, _ = overwrite_capnp_schema_id(source_text)
        else:
            source_text_new_id = source_text

        new_tmp_file.write_text(source_text_new_id, encoding="utf-8")
        system_paths_for_capnp_imports = ["/usr/local/include", "/usr/include"]
        check = subprocess.check_output(
                ["capnp", "compile", "-o-", str(new_tmp_file)], stderr=subprocess.PIPE)
        if use_global_parser:
            return capnp.load(str(new_tmp_file), imports=system_paths_for_capnp_imports)
        else:
            parser = capnp.SchemaParser()
            return parser, parser.load(str(new_tmp_file), imports=system_paths_for_capnp_imports)
    finally:
        if new_tmp_file.exists():
            new_tmp_file.unlink()
        if dir_created:
            root_dir.rmdir()

def parse_capnp_plugin(source_file: Path,
        plugin_id: Optional[str], relative_to_source: bool) -> ParsePluginTypeResult:
    try:
        parser, loaded = load_capnp_schema_from_file(source_file,
                # Each parse owns its SchemaParser, so stable IDs cannot collide
                # with previous parses and can identify the handover schema.
                relative_to_source, with_random_schema_id=False,
                use_global_parser=False)
    except subprocess.CalledProcessError as e:
        return ParsePluginTypeResult(
            is_valid=False,
            message=f"Failed to load Cap'n Proto schema from '{source_file}': {e}\n{e.stderr.decode('utf-8')}",
            data=None,
        )

    members = [member for member in dir(loaded) if not member.startswith('_')]

    plugins = []
    structs = {}
    interfaces = {}
    dependencies = []
    for member in members:
        member_field = getattr(loaded, member)
        if not hasattr(member_field, "schema") \
            or not hasattr(member_field.schema, "node") \
            or not hasattr(member_field.schema.node, "annotations"):
            continue

        node = member_field.schema.node
        # pycapnp nodes are tagged unions. Query their active member instead of
        # probing union fields with hasattr(), which can suppress valid structs.
        try:
            node_kind = node.which()
        except capnp.KjException:
            continue

        if node_kind == "struct":
            if node.isGeneric:
                continue
            try:
                msg = member_field.new_message()
                struct = build_struct_description(msg, node, parser, dependencies)
            except (capnp.KjException, ValueError) as error:
                return ParsePluginTypeResult(
                    is_valid=False,
                    message=f"Failed to describe struct '{node.displayName}': {error}",
                    data=None,
                )
            structs[struct.name] = struct
        elif node_kind == "interface":
            if node.isGeneric:
                continue
            try:
                server_instance = member_field.Server()
                iface_desc = build_interface_description(server_instance, node, parser, dependencies)
                iface_desc = bind_lifecycle_state(iface_desc, node, loaded)
            except (capnp.KjException, ValueError) as error:
                return ParsePluginTypeResult(
                    is_valid=False,
                    message=f"Failed to describe interface '{node.displayName}': {error}",
                    data=None,
                )
            interfaces[iface_desc.name] = iface_desc
            is_plugin, plugin_name = check_if_capnp_type_is_plugin(member_field)
            if is_plugin:
                plugins.append(PluginTypeMetadata(
                    type='capnp',
                    plugin_name=plugin_name,
                    interface_name=iface_desc.name,
                ))

    return ParsePluginTypeResult(
        is_valid=True,
        message="Successfully parsed Cap'n Proto schema.",
        data=ParsePluginTypeData(
            source_file=str(source_file),
            source_language="capnp",
            structs=structs,
            interfaces=interfaces,
            script_handle=loaded,
            plugins=plugins,
            dependencies=dependencies,
        ),
    )
