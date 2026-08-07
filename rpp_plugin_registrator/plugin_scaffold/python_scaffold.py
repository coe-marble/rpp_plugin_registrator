from __future__ import annotations

from dbm.ndbm import library
from pathlib import Path
from typing import Any, Dict

from rpp_plugin_registrator.plugin_descriptors.core import (
    FieldInfo, MethodInfo, PluginTypeInfo, TypeInfo
)


_PRIMITIVE_TYPE_MAP = {
    "int8": ("int", 0),
    "int16": ("int", 0),
    "int32": ("int", 0),
    "int64": ("int", 0),
    "uint8": ("int", 0),
    "uint16": ("int", 0),
    "uint32": ("int", 0),
    "uint64": ("int", 0),
    "float32": ("float", 0.0),
    "float64": ("float", 0.0),
    "string": ("str", '""'),
    "text": ("str", '""'),
    "bool": ("bool", False),
}

def update_init_file(directory: Path, class_name: str) -> None:
    """Ensure that an __init__.py file exists in the given directory."""
    init_file = directory / "__init__.py"
    if not init_file.exists():
        init_file.write_text("# Auto-generated __init__.py\n", encoding="utf-8")
    line = f"from .{class_name} import {class_name}\n"
    with init_file.open("r+", encoding="utf-8") as f:
        lines = f.readlines()
        if line not in lines:
            f.write(line)


def parse_field_type(field_type: Dict[str, Any] | TypeInfo,
        library_name: str, imports=None, import_as_private=False) -> str:

    if isinstance(field_type, TypeInfo):
        field_type = field_type.as_dict()
    kind = field_type.get("Kind")
    if kind == "primitive":
        return _PRIMITIVE_TYPE_MAP.get(field_type.get("Name"))[0]
    elif kind == "struct":
        splits = field_type.get("CapnpTypeDisplayName", "").split("/")
        if len(splits) == 2:
            library_name_in_msg, _ = splits
        else:
            library_name_in_msg = library_name
        splits2 = field_type.get("CapnpTypeDisplayName", "").split(":")
        struct_name = splits2[-1]
        if import_as_private:
            import_statement = f"from rpp_schema.{library_name_in_msg}." \
                + f"{struct_name} import {struct_name} as _{struct_name}"
        else:
            import_statement = f"from rpp_schema.{library_name_in_msg}" \
                + f".{struct_name} import {struct_name}"
        if imports is not None and import_statement not in imports:
            imports.append(import_statement)
        return struct_name
    elif kind == "list":
        element_type = parse_field_type(
            field_type.get("ElementType", {}), library_name, imports,
            import_as_private=import_as_private)
        return f"List[{element_type}]"


def generate_structs(description: PluginTypeInfo, output_path: Path) -> None:
    """Generate Python classes for the structs defined in the plugin description."""
    library_name = description.info["Library"]
    if description.parse_data is None or description.parse_data.structs is None:
        return
    for struct_name, struct in description.parse_data.structs.items():
        imports = ["from typing import List, Dict, Any, Tuple"]
        field_lines = []
        for field in struct.fields:
            field_type_parsed = parse_field_type(field.type, library_name, imports)
            if field.type.kind == "struct":
                field_lines.append(f"{field.name}: {field_type_parsed}"
                    + f" = Field(default_factory={field_type_parsed})")
            elif field.type.kind == "list":
                field_lines.append(
                    f"{field.name}: {field_type_parsed} = Field(default_factory=list)")
            else:
                type_name = field.type.name
                if type_name not in _PRIMITIVE_TYPE_MAP:
                    raise ValueError(
                        f"Unsupported primitive type '{type_name}' for field "
                        + f"'{field.name}' in struct '{struct_name}'.")
                default_value = _PRIMITIVE_TYPE_MAP.get(field.type.name)[1]
                field_lines.append(
                    f"{field.name}: {field_type_parsed} = {default_value}")
        field_str = "\n    ".join(field_lines)

        imports_str = "\n".join(imports)

        content = f'''
from typing import List, Dict, Any, Tuple
from pydantic import (
    BaseModel, ConfigDict, RootModel,
    ValidationError, Field
)
from pydantic.dataclasses import dataclass
{imports_str}

@dataclass(config=ConfigDict(extra="forbid", validate_assignment=True))
class {struct_name}:

    def as_dict(self) -> Dict[str, Any]:

        return RootModel(self).model_dump()

    {field_str}
    '''
        struct_file_path = output_path / "python" / "rpp_schema" \
            / library_name / f"{struct_name}.py"
        if not struct_file_path.parent.exists():
            struct_file_path.parent.mkdir(parents=True, exist_ok=True)
        struct_file_path.write_text(content, encoding="utf-8")

def create_method_prototype_string(method: MethodInfo,
        library_name: str, type_aliases=None,
        imports=None, append_to_params_call=None) -> str:
    param_types_with_names = []
    params_call_backend = []
    for param in method.params:
        field_type = param.type
        parsed_type = parse_field_type(field_type,
                library_name, imports, import_as_private=True)
        param_types_with_names.append(f"{param.name}: {parsed_type}")

        if append_to_params_call is not None:
            params_call_backend.append(f"{param.name}={param.name}{append_to_params_call}")
        else:
            params_call_backend.append(f"{param.name}={param.name}")
        if type_aliases is not None:
            type_alias = f"{parsed_type} = _{parsed_type}"
            if field_type.kind == "struct":
                if type_alias not in type_aliases:
                    type_aliases.append(type_alias)
            elif field_type.kind == "list" and field_type.element_type.kind == "struct":
                element_type_parsed = parse_field_type(field_type.element_type,
                    library_name, imports, import_as_private=True)
                type_alias = f"{element_type_parsed} = _{element_type_parsed}"
                if type_alias not in type_aliases:
                    type_aliases.append(type_alias)

    result_types_with_names = []
    for output in method.results:
        field_type = output.type
        parsed_type = parse_field_type(field_type,
                library_name, imports, import_as_private=True)

        result_types_with_names.append(f"{parsed_type}")
        if type_aliases is not None:
            type_alias = f"{parsed_type} = _{parsed_type}"
            if field_type.kind == "struct":
                if type_alias not in type_aliases:
                    type_aliases.append(type_alias)
            elif field_type.kind == "list" and field_type.element_type.kind == "struct":
                element_type_parsed = parse_field_type(field_type.element_type,
                    library_name, imports, import_as_private=True)
                type_alias = f"{element_type_parsed} = _{element_type_parsed}"
                if type_alias not in type_aliases:
                    type_aliases.append(type_alias)
    param_types_with_names_str = \
        ', '.join(param_types_with_names) + ', ' if param_types_with_names else ''
    if len(result_types_with_names) == 0:
        result_types_with_names_str = "None"
    elif len(result_types_with_names) == 1:
        result_types_with_names_str = result_types_with_names[0]
    else:
        result_types_with_names_str = f"Tuple[{', '.join(result_types_with_names)}]"
    return f"def {method.name}(self, {param_types_with_names_str}**kwargs)" \
        + f"-> {result_types_with_names_str}", ", ".join(params_call_backend)



def create_plugin_methods_string_with_type_alisases_and_imports(
        description: PluginTypeInfo, imports=None) -> str:
    """Generate type aliases for the plugin class based on the description."""
    type_aliases = []

    methods_str = ""
    methods = description.get_interface().methods if description.get_interface() else []
    for method in methods:
        prototype, _ = create_method_prototype_string(method,
                description.info["Library"], type_aliases, imports)
        methods_str += f'''
    {prototype}:
        raise NotImplementedError("This method should be implemented in the plugin class.")
'''
    return methods_str, type_aliases, imports


def create_adapter_server_methods_string_with_type_alisases_and_imports(
        description: PluginTypeInfo, imports=None) -> str:
    """Generate type aliases for the plugin adapter server class based on the description."""
    type_aliases = []
    methods_str = ""
    methods = description.get_interface().methods if description.get_interface() else []
    for method in methods:
        prototype, params_call_backend = create_method_prototype_string(method,
            description.info["Library"], type_aliases, imports)
        methods_str += f'''
    async {prototype}:
        if self._backend is None:
            raise RuntimeError("Backend is not configured. Please call configure_adapter_server__() first.")
        return self._backend.{method.name}({params_call_backend})
'''

    return methods_str, type_aliases, imports

def create_adapter_client_methods_string_with_type_alisases_and_imports(
        description: PluginTypeInfo, imports=None) -> str:
    """Generate type aliases for the plugin adapter client class based on the description."""
    type_aliases = []
    methods_str = ""
    methods = description.get_interface().methods if description.get_interface() else []
    for method in methods:
        prototype, params_call_backend = create_method_prototype_string(method,
            description.info["Library"], type_aliases, imports, append_to_params_call='.as_dict()')
        methods_str += f'''
    async {prototype}:
        if self._client is None:
            raise RuntimeError("Client is not configured. Please call configure_adapter_client__() first.")
        # req = self._client.{method.name}()
        # req.state.position.x = 1.0
        # req.state.position.y = 2.0
        # req.state.yaw = 0.5
        # result = await req
        # return result
        return await self._client.{method.name}({params_call_backend})
'''

    return methods_str, type_aliases, imports

def generate_plugin_adapter_client(
        description: PluginTypeInfo, scaffolded_file_path: Path) -> None:
    """Generate a Python class for the plugin adapter client based on the description."""
    class_name = description.info["ClassName"]
    plugin_type_name = description.info["PluginTypeName"]
    lib_name = description.info["Library"]
    imports = []
    methods_str, type_aliases, imports = \
        create_adapter_client_methods_string_with_type_alisases_and_imports(
            description, imports)
    type_aliases_str = "\n    ".join(type_aliases) if type_aliases else ""
    file_name = Path(f"{description.info['SourceFile']}").name
    imports_str = "\n".join(imports)

    content = f'''
from typing import List, Dict, Any, Tuple
import capnp
import rpp_py.capnp_schema as capnp_schema
from rpp_py.client_context import ClientContext
from rpp_py.adapter_info import AdapterClientParams, AdapterClientInfo
from rpp_plugin_types.{lib_name}.{class_name} import {class_name}
from rpp_py.plugin_runtime import RuntimeConstants
import asyncio
{imports_str}

class {class_name}_AdapterClient({class_name}):
    {type_aliases_str}

    def __init__(self):
        self._adapter_client_params: AdapterClientParams = None
        self._client = None
        self._runtime = None

    def configure_adapter_client__(self, adapter_client_params: AdapterClientParams):
        self._adapter_client_params = adapter_client_params
        self._adapter_client_info = AdapterClientInfo()
        self._adapter_client_info.plugin_name = adapter_client_params.plugin_name
        self._adapter_client_info.name = adapter_client_params.name \\
            if adapter_client_params.name else \\
                f"{{adapter_client_params.plugin_name}}_adapter_client"
        self._adapter_client_info.connection_name = adapter_client_params.connection_name \\
            if adapter_client_params.connection_name else \\
                f"{{adapter_client_params.plugin_name}}_connection"

    async def connect_adapter_client__(self, context: ClientContext):
        if self._adapter_client_params is None:
            raise RuntimeError("Adapter client params is not configured. Please call configure_adapter_client__() first.")
        self._runtime = context.get_runtime()

        runtime_class = RuntimeConstants.get_capnp_schema().PluginRuntime
        try:
            self._runtime_client = context.get_client().cast_as(runtime_class)
            capability = await self._runtime_client.getComponentCapability(
                self._adapter_client_info.connection_name)
            interface_class = capnp_schema.get_client_class("{plugin_type_name}", "{file_name}")
            self._client = capability.pluginRef.as_interface(interface_class)
            return True
        except Exception as e:
            client_class = capnp_schema.get_client_class("{plugin_type_name}", "{file_name}")
            self._client = context.get_client().cast_as(client_class)

    async def disconnect_adapter_client__(self):
        self._adapter_client_params = None
        self._client = None
        self._runtime = None

    {methods_str}
'''

    name = Path(scaffolded_file_path).stem
    adapter_client_file_path = scaffolded_file_path.parent / f"{name}_AdapterClient.py"

    adapter_client_file_path.write_text(content, encoding="utf-8")
    return adapter_client_file_path

def generate_plugin_adapter_server(description: PluginTypeInfo, scaffolded_file_path: Path) -> None:
    """Generate a Python class for the plugin adapter server based on the description."""
    class_name = description.info["ClassName"]
    plugin_type_name = description.info["PluginTypeName"]
    lib_name = description.info["Library"]
    imports = []
    methods_str, type_aliases, imports = \
        create_adapter_server_methods_string_with_type_alisases_and_imports(description, imports)
    type_aliases_str = "\n    ".join(type_aliases) if type_aliases else ""
    file_name = Path(f"{description.info['SourceFile']}").name
    imports_str = "\n".join(imports)

    content = f'''

from typing import List, Dict, Any, Tuple
{imports_str}
import capnp
import rpp_py.capnp_schema as capnp_schema
import asyncio
from rpp_py.capnp_runtime import CapnpRuntime
from rpp_py.context import ComponentContext
from rpp_py.adapter_info import AdapterServerParams, AdapterServerInfo
from rpp_plugin_types.{lib_name}.{class_name} import {class_name}

class {class_name}_AdapterServer(capnp_schema.get_server_class("{plugin_type_name}", "{file_name}")):
    {type_aliases_str}

    def __init__(self):
        super().__init__()
        self._adapter_server_params: AdapterServerParams = None
        self._backend : {class_name} = None
        self._asyncio_server = None
        self._rpc_server = None
        self.is_running = False
        self._runtime = None
        self._adapter_server_info = AdapterServerInfo()
        self._adapter_server_info.plugin_type = "{plugin_type_name}"
        self._adapter_server_info.created_at = ""

    def configure_adapter_server__(self, adapter_server_params: AdapterServerParams):
        self._adapter_server_params = adapter_server_params
        self._adapter_server_info.plugin_name = adapter_server_params.plugin_name
        self._adapter_server_info.name = adapter_server_params.name \\
            if adapter_server_params.name else \\
                f"{{adapter_server_params.plugin_name}}_adapter_server"
        self._adapter_server_info.connection_name = adapter_server_params.connection_name \\
            if adapter_server_params.connection_name else \\
                f"{{adapter_server_params.plugin_name}}_connection"
        self._backend = adapter_server_params.backend

    def create_capability_adapter_server__(self):
        return capnp_schema.get_server_class("{plugin_type_name}", "{file_name}")

    async def handle_connection_adapter_server__(self, stream):
        self._rpc_server = capnp.TwoPartyServer(stream, bootstrap=self)
        await self._rpc_server.on_disconnect()

    async def start_adapter_server__(self, runtime: CapnpRuntime, host: str, port: int):
        self._runtime = runtime
        if self._adapter_server_params is None:
            raise RuntimeError("Adapter server params are not configured. " \\
                + "Please call configure_adapter_server__() first.")

        self._asyncio_server = await capnp.AsyncIoStream.create_server( \\
                self.handle_connection_adapter_server__, host, port)
        self.is_running = True


    async def stop_adapter_server__(self):
        if self._asyncio_server:
            self._asyncio_server.close()
            await self._asyncio_server.wait_closed()
        self._asyncio_server = None
        self._rpc_server = None
        self._runtime = None
        self.is_running = False

    def get_info_adapter_server__(self) -> AdapterServerInfo:
        return self._adapter_server_info

    def initialize(self, context: ComponentContext):
        pass

    {methods_str}
'''

    name = Path(scaffolded_file_path).stem
    adapter_server_file_path = scaffolded_file_path.parent / f"{name}_AdapterServer.py"

    adapter_server_file_path.write_text(content, encoding="utf-8")
    return adapter_server_file_path


def generate_plugin_class(description: PluginTypeInfo, output_path: Path) -> None:
    class_name = description.info["ClassName"]
    imports = []
    methods_str, type_aliases, imports = \
        create_plugin_methods_string_with_type_alisases_and_imports(description, imports)
    type_aliases_str = "\n    ".join(type_aliases) if type_aliases else ""
    imports_str = "\n".join(imports)
    content = f'''
from typing import List, Dict, Any, Tuple
from rpp_py.plugin import Plugin
from rpp_py.context import ComponentContext
{imports_str}

class {class_name}(Plugin):

    {type_aliases_str}

    {methods_str}

    def initialize(self, context: ComponentContext):
        raise NotImplementedError("This method should be implemented in the plugin class.")
'''

    lib_name = description.info["Library"]
    if output_path.is_dir():
        file_path = output_path / "python" / "rpp_plugin_types" / lib_name / f"{class_name}.py"
    else:
        file_path = output_path

    if not file_path.parent.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return file_path, class_name


def scaffold_python_from_capnp(description: PluginTypeInfo,
        output_path: Path, only_stubs: bool = False) -> None:

    generate_structs(description, output_path)

    if only_stubs:
        # If only stubs are requested, we can skip generating the full plugin class.
        return

    file_path, class_name = generate_plugin_class(description, output_path)
    generate_plugin_adapter_server(description, file_path)
    generate_plugin_adapter_client(description, file_path)
    update_init_file(file_path.parent, class_name)