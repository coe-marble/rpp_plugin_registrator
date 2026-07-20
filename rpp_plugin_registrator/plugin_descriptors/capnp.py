from __future__ import annotations

import re, secrets
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional
from xml.dom.minidom import TypeInfo

import capnp

from ..registry_paths import get_app_capnp_interfaces_path

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


def parse_capnp_plugin_from_param(plugin_param: Dict[str, Any], parser) -> TypeInfo:
    from capnp import KjException
    # try to parse complex types. hasattr will raise an exception...
    try:
        if hasattr(plugin_param, "schema") \
                and hasattr(plugin_param.schema, "node") \
                and hasattr(plugin_param.schema, "fields_list"):
            display_name = plugin_param.schema.node.displayName
            name = display_name.split(':')[-1]
            return TypeInfo(
                kind="struct",
                name=name,
                capnp_type_display_name=display_name,
            )
    except KjException:
        pass

    return parse_capnp_plugin_type_from_type_dict(plugin_param.proto.slot.type.to_dict(), parser)

def parse_capnp_plugin_type_from_type_dict(plugin_type: Dict[str, Any], parser) -> TypeInfo:
    is_list = "list" in plugin_type and plugin_type["list"] is not None
    if is_list:
        element_type = plugin_type["list"]["elementType"]
        if isinstance(element_type, dict):
            return TypeInfo(
                kind="list",
                name=None,
                element_type=parse_capnp_plugin_type_from_type_dict(element_type, parser),
            )
        else:
            return TypeInfo(
                kind="list",
                name=element_type.name if hasattr(element_type, 'name') else None,
                element_type=parse_capnp_plugin_type_from_type_dict(element_type.to_dict(), parser) if hasattr(element_type, 'to_dict') else None,
            )
    is_struct = "struct" in plugin_type and plugin_type["struct"] is not None
    if is_struct:
        type_id = plugin_type["struct"]["typeId"]
        type_info = parser.modules_by_id.get(type_id)
        type_display_name = type_info.schema.node.displayName
        name = type_display_name.split(':')[-1]

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

def build_struct_description(msg, struct_node, parser) -> StructInfo:
    class_name = struct_node.displayName.split(':')[-1]
    fields = []
    for key, value in msg.schema.fields.items():
        field_name = key
        type_as_dict = value.proto.slot.type.to_dict()
        fields.append(FieldInfo(
            name=field_name,
            type=parse_capnp_plugin_type_from_type_dict(type_as_dict, parser),
        ))
    return StructInfo(
        name=class_name,
        fields=fields,
    )


def build_interface_description(server_instance, interface_node, parser) -> InterfaceInfo:
    class_name = interface_node.displayName.split(':')[-1]

    methods = {**server_instance.schema.methods_inherited, **server_instance.schema.methods}
    methods_info = []

    for method_name, method in methods.items():
        params = []
        results = []
        for param in method.param_type.fields_list:
            # try parse complex types. hasattr will raise an exception...
            param_type_info = parse_capnp_plugin_from_param(param, parser)
            params.append(FieldInfo(
                name=param.proto.name,
                type=param_type_info,
            ))
        for result in method.result_type.fields_list:
            result_type_info = parse_capnp_plugin_from_param(result, parser)
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
                ["capnp", "compile", "-o-", str(new_tmp_file)], stderr=subprocess.STDOUT)
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
                relative_to_source, with_random_schema_id=True,
                use_global_parser=False)
    except subprocess.CalledProcessError as e:
        return ParsePluginTypeResult(
            is_valid=False,
            message=f"Failed to load Cap'n Proto schema from '{source_file}': {e}",
            data=None,
        )

    members = [member for member in dir(loaded) if not member.startswith('_')]

    plugins = []
    structs = {}
    interfaces = {}
    for member in members:
        member_field = getattr(loaded, member)
        if not hasattr(member_field, "schema") \
            or not hasattr(member_field.schema, "node") \
            or not hasattr(member_field.schema.node, "annotations"):
            continue

        node = member_field.schema.node
        try:
            is_struct = hasattr(node, "struct")
            if is_struct:
                if node.isGeneric:
                    continue
                msg = member_field.new_message()
                struct = build_struct_description(msg, node, parser)
                structs[struct.name] = struct
            continue
        except capnp.KjException:
            pass

        try:
            is_interface = hasattr(node, "interface")
            if is_interface:
                if node.isGeneric:
                    continue
                # build interface description
                server_instance = member_field.Server()
                iface_desc = build_interface_description(server_instance, node, parser)
                interfaces[iface_desc.name] = iface_desc
                is_plugin, plugin_name = check_if_capnp_type_is_plugin(member_field)
                if is_plugin:
                    plugins.append(PluginTypeMetadata(
                        type='capnp',
                        plugin_name=plugin_name,
                        interface_name=iface_desc.name,
                    ))
        except capnp.KjException:
            pass

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
        ),
    )