from __future__ import annotations
from pathlib import Path
from typing import Any, Dict
import re



from rpp_plugin_registrator.registry_config import \
    get_app_capnp_interfaces_path

from rpp_plugin_registrator.plugin_descriptors.capnp import overwrite_capnp_schema_id
from rpp_plugin_registrator.plugin_descriptors.core import PluginTypeRegisterData, PluginTypeRegistrationResult


def set_capnp_to_namespace(source_text: str, schema_id: str, namespace: str) -> str:
    # Insert a line after file id declaration to set the namespace
    # Id ends with a semicolon. Go to new line after it
    lines = source_text.splitlines()
    for i, line in enumerate(lines):
        if re.match(r'@0x[0-9a-fA-F]+;', line):
            lines.insert(i + 1, f'$Cxx.namespace("{namespace}");')
            lines.insert(i + 1, 'using Cxx = import "/capnp/c++.capnp";')
            break

    return '\n'.join(lines)

def read_capnp_schema_id(source_text: str) -> str:
    match = re.search(r'@0x([0-9a-fA-F]+);', source_text)
    if match:
        return match.group(1)
    else:
        raise ValueError("No schema ID found in the provided Cap'n Proto source text.")


def register_capnp_plugin_type(
    desc,
    override: bool = False
) -> PluginTypeRegistrationResult:

    info = desc.info
    interfaces_path = get_app_capnp_interfaces_path()
    lib_interfaces_path = Path(interfaces_path) / info.get("Library")

    file_name = Path(info.get("SourceFile")).name

    if not lib_interfaces_path.exists():
        lib_interfaces_path.mkdir(parents=True, exist_ok=True)

    destination_file_path = lib_interfaces_path / file_name
    if destination_file_path.exists() and not override:
        existing_text = destination_file_path.read_text(encoding="utf-8")
        existing_id = read_capnp_schema_id(existing_text)
        return PluginTypeRegistrationResult(
            success=True,
            message=f"CAP-NP plugin type '{info.get('Library')}' already registered.",
            register_data=PluginTypeRegisterData(
                registry_plugin_type_file=str(destination_file_path),
                registry_plugin_type_file_id=existing_id
            )
        )


    # Copy the source file to the library's interface directory
    source_file_path = Path(info.get("SourceFile"))
    # Overwrite the source file id
    source_text = source_file_path.read_text(encoding="utf-8")

    source_text_override, new_id = overwrite_capnp_schema_id(source_text)

    source_text_override = set_capnp_to_namespace(
            source_text_override, new_id, f"schema::{info.get('Library')}")



    destination_file_path.write_text(source_text_override, encoding="utf-8")

    # for capnp compile command, it is necessary to generate
    # a symlink to the library inside the library so library can be found by capnp compiler
    destination_lib_path = destination_file_path.parent
    symlink_path = destination_lib_path / info.get("Library")
    if not symlink_path.exists():
        symlink_path.symlink_to(destination_lib_path, target_is_directory=True)


    return PluginTypeRegistrationResult(
        success=True,
        message=f"CAP-NP plugin type '{info.get('Library')}' registered successfully.",
        register_data=PluginTypeRegisterData(
            registry_plugin_type_file=str(destination_file_path),
            registry_plugin_type_file_id=new_id
        )
    )
def unregister_capnp_plugin_type(plugin_info: Dict[str, Any]) -> None:
    interfaces_path = get_app_capnp_interfaces_path()
    lib_interfaces_path = Path(interfaces_path) / plugin_info.get("Library")

    file_name = Path(plugin_info.get("SourceFile")).name
    destination_file_path = lib_interfaces_path / file_name

    if destination_file_path.exists():
        destination_file_path.unlink()