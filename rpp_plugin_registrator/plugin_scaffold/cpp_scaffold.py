from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from string import Template
from typing import Dict

from rpp_plugin_registrator.plugin_descriptors.core import PluginTypeInfo, StructInfo, TypeInfo

from .scaffold_capnp_stubs import scaffold_capnp_stubs

from .templates.utils import to_pascal_case, adapt_capnp_field_name
from .templates import cpp_language_adapter_client_template_cpp as client_template
from .templates import cpp_language_adapter_server_template_cpp as server_template




PRIMITIVE_TYPE_MAP = {
    "bool": "bool",
    "int8": "int8_t",
    "int16": "int16_t",
    "int32": "int32_t",
    "int64": "int64_t",
    "uint8": "uint8_t",
    "uint16": "uint16_t",
    "uint32": "uint32_t",
    "uint64": "uint64_t",
    "float32": "float",
    "float64": "double",
    "text": "std::string",
}


def parse_type_name_from_type_info(type_info: TypeInfo,
        type_aliases: list = None, include_types: list = None, lib_name: str = None) -> str:
    """Extract the type name from a TypeInfo dictionary."""

    if isinstance(type_info, TypeInfo):
        type_info = type_info.as_dict()
    if type_info["Kind"] == "primitive":
        return PRIMITIVE_TYPE_MAP.get(type_info["Name"], type_info["Name"])
    elif type_info["Kind"] == "list":
        element_type_name = parse_type_name_from_type_info(type_info["ElementType"], type_aliases, include_types, lib_name=lib_name)
        return f"std::vector<{element_type_name}>"
    elif type_info["Kind"] == "struct":
        capnp_type_display_name = type_info.get("CapnpTypeDisplayName", "")
        splits = capnp_type_display_name.split('/')
        if len(splits) > 2:
            raise ValueError(f"Invalid Cap'n Proto type display name: {capnp_type_display_name}")
        if len(splits) == 1:
            library_name = lib_name
        else:
            library_name = splits[0]
        alias = f"    using {type_info['Name']} = rpp_schema::{library_name}::{type_info['Name']};"
        alias_native = f"    using {type_info['Name']}_S = rpp_schema::{library_name}::{type_info['Name']}_Native;"
        include_type = f'#include "rpp_schema/{library_name}/{type_info["Name"]}.hpp"'
        if type_aliases is not None and alias not in type_aliases:
            type_aliases.append(alias)
            type_aliases.append(alias_native)
        if include_types is not None and include_type not in include_types:
            include_types.append(include_type)
        return f"{type_info['Name']}"
    else:
        raise ValueError(f"Unsupported type kind: {type_info['Kind']}")


def _render_template(source_content: str, **values: str) -> str:
    return Template(source_content).substitute(**values)


def create_function_prototype(method: dict, type_aliases: list = None, include_types: list = None, lib_name: str = None) -> str:
    """Create a C++ function prototype from a method dictionary."""
    # make params const reference
    param_types_and_names = []
    for param in method["Params"]:
        type_name = parse_type_name_from_type_info(param["Type"], type_aliases, include_types, lib_name=lib_name)
        if param["Type"]["Kind"] == "struct":
            type_name += "::Const"
        param_types_and_names.append(f"{type_name} {param['Name']}")
    params = ", ".join(param_types_and_names)

    result_types = []
    for result in method["Results"]:
        type_name = parse_type_name_from_type_info(result["Type"], type_aliases, include_types, lib_name=lib_name)
        if result["Type"]["Kind"] == "struct":
            type_name += "::Const"
        result_types.append(type_name)


    if len(method["Results"]) == 0:
        results = "void"
    elif len(method["Results"]) == 1:
        results = result_types[0]
    else:
        results = "std::tuple<" + ", ".join(result_types) + ">"
    return f"{results} {method['Name']}({params})", results

def generate_type_aliases_and_methods_for_plugin_hpp(methods: list, lib_name:str) -> str:
    """Generate a string representation of methods for C++ code generation."""
    method_strings = []
    type_aliases = []
    include_types = []
    for method in methods:
        prototype, _ = create_function_prototype(method, type_aliases, include_types, lib_name=lib_name)
        method_strings.append(f"    virtual {prototype} = 0;\n")
    return "\n".join(method_strings), "\n".join(type_aliases), "\n".join(include_types)


def generate_methods_for_foreign_language_adapter_client(methods: list) -> str:
    method_strings = []
    for method in methods:
        prototype, return_type = create_function_prototype(method)
        method_name = method["Name"]
        result_getters = []
        for result in method["Results"]:
            type_name = parse_type_name_from_type_info(result["Type"])
            # if result["Type"]["Kind"] == "struct":
            #     type_name += "::Const"
            if result["Type"]["Kind"] == "struct":
                result_getters.append(f"{type_name}::Const(response.get{adapt_capnp_field_name(result['Name'])}())")
            else:
                result_getters.append(f"response.get{adapt_capnp_field_name(result['Name'])}()")


        param_setters = "\n".join(
            f"        request.set{adapt_capnp_field_name(param['Name'])}({param['Name']});"
            for param in method["Params"]
        )
        response_handling = ""
        if return_type == "void":
            response_handling = "        request.send().wait(client_->getWaitScope());"
        elif len(method["Results"]) == 1:
            response_handling = "        auto response = request.send().wait(client_->getWaitScope());\n"
            response_handling += f"        return {result_getters[0]};"
        else:
            response_handling = "        auto response = request.send().wait(client_->getWaitScope());\n"
            response_handling += f"        return std::make_tuple({', '.join(result_getters)});"

        method_strings.append(
            _render_template(
                client_template.METHOD_TEMPLATE,
                prototype=prototype,
                method_name=method_name,
                param_setters=param_setters,
                response_handling=response_handling,
            )
        )
    return "\n".join(method_strings)


def generate_methods_for_foreign_language_adapter_server(lib_name: str, class_name: str, methods: list) -> str:
    method_strings = []
    for method in methods:
        _, return_type = create_function_prototype(method)
        method_name = method["Name"]
        method_prefix = to_pascal_case(method_name)
        context_type = f"{method_prefix}Context"
        params_expr = ", ".join(
            f"context.getParams().get{adapt_capnp_field_name(param['Name'])}()"
            for param in method["Params"]
        )
        body_lines = []
        if return_type == "void":
            if params_expr:
                body_lines.append(f"        backend_->{method_name}({params_expr});\n")
            else:
                body_lines.append(f"        backend_->{method_name}();\n")
        elif len(method["Results"]) == 1:
            result_name = adapt_capnp_field_name(method["Results"][0]["Name"])
            if params_expr:
                body_lines.append(f"        auto result = backend_->{method_name}({params_expr});\n")
            else:
                body_lines.append(f"        auto result = backend_->{method_name}();\n")
            body_lines.append(f"        context.getResults().set{result_name}(result);\n")
        else:
            if params_expr:
                body_lines.append(f"        auto results = backend_->{method_name}({params_expr});\n")
            else:
                body_lines.append(f"        auto results = backend_->{method_name}();\n")
            for index, result in enumerate(method["Results"]):
                result_name = adapt_capnp_field_name(result["Name"])
                body_lines.append(f"        context.getResults().set{result_name}(std::get<{index}>(results));\n")
        body_lines.append("        return ::kj::READY_NOW;\n")
        method_strings.append(
            _render_template(
                server_template.METHOD_TEMPLATE,
                method_name=method_name,
                context_type=context_type,
                body="".join(body_lines),
            )
        )
    return "\n".join(method_strings)


def generate_plugin_type_hpp(description: PluginTypeInfo, output_path: Path) -> None:
    """Generate a C++ header file for a plugin type based on the provided description."""
    class_name = description.info["ClassName"]
    lib_name = description.info["Library"]
    methods_string, type_aliases, include_types = \
        generate_type_aliases_and_methods_for_plugin_hpp(description.info["Methods"], lib_name)

    content = f'''#pragma once
#include <string>
#include "rpp_cpp/plugin.hpp"
#include "rpp_cpp/context.hpp"
#include "map"
#include <type_traits>
#include <memory>
{include_types}



namespace {lib_name}{{

namespace hidden {{
    class {class_name}_Adapter_Client;
    class {class_name}_Adapter_Server;
}}

class {class_name} : public rpp::Plugin {{


public:
    {class_name}() = default;
    virtual ~{class_name}() = default;

    using AdapterClient = hidden::{class_name}_Adapter_Client;
    using AdapterServer = hidden::{class_name}_Adapter_Server;

{type_aliases}

{methods_string}

    virtual void initialize(const rpp::ComponentContext& /*context */) {{}}

}};

}}  // namespace

#include "{class_name}_Adapter_Client.hpp"
#include "{class_name}_Adapter_Server.hpp"
'''

    if output_path.is_dir():
        file_path = output_path / "cpp" / "rpp_plugin_types" / lib_name / f"{class_name}.hpp"
    else:
        file_path = output_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")


def generate_plugin_type_foreign_language_adapter_client_hpp(description: PluginTypeInfo, output_path: Path) -> None:
    """Generate a C++ header file for a foreign language adapter client for a plugin type."""
    class_name = description.info["ClassName"]
    plugin_type_name = description.info["PluginTypeName"]
    lib_name = description.info["Library"]

    methods_string = generate_methods_for_foreign_language_adapter_client(description.info["Methods"])

    content = _render_template(
        client_template.SOURCE_CONTENT,
        lib_name=lib_name,
        class_name=class_name,
        plugin_type_name=plugin_type_name,
        generated_h=Path(description.register_data.registry_plugin_type_file).name + ".h",
        methods_string=methods_string,
    )

    if output_path.is_dir():
        file_path = output_path / "cpp" / "rpp_plugin_types" / lib_name / f"{class_name}_Adapter_Client.hpp"
    else:
        file_path = output_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")


def generate_plugin_type_foreign_language_adapter_server_hpp(description: PluginTypeInfo, output_path: Path) -> None:
    """Generate a C++ header file for a foreign language adapter server for a plugin type."""
    class_name = description.info["ClassName"]
    plugin_type_name = description.info["PluginTypeName"]
    lib_name = description.info["Library"]

    methods_string = generate_methods_for_foreign_language_adapter_server(
        lib_name,
        class_name,
        description.info["Methods"],
    )

    content = _render_template(
        server_template.SOURCE_TEMPLATE,
        lib_name=lib_name,
        class_name=class_name,
        plugin_type_name=plugin_type_name,
        generated_h=Path(description.register_data.registry_plugin_type_file).name + ".h",
        methods_string=methods_string,
    )

    if output_path.is_dir():
        file_path = output_path / "cpp" / "rpp_plugin_types" / lib_name / f"{class_name}_Adapter_Server.hpp"
    else:
        file_path = output_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")


def make_as_struct_method_string(struct_name : str,
        fields: list, lib_name: str, indent:str, accessor_name: str) -> str:
    list_types = [field for field in fields if field.type.kind == "list"]
    content = f"""
{indent}{struct_name}_Native as_struct() const {{
"""
    any_list_type = len(list_types) > 0
    for list_type in list_types:
        element_type = list_type.type.element_type
        element_reader_type = parse_type_name_from_type_info(element_type, lib_name=lib_name)
        if element_type.kind == "struct":
            content += f'''
    {indent}std::vector<{element_reader_type}_Native> {list_type.name}_vec;
    {indent}auto capnp_{list_type.name} = {accessor_name}.get{to_pascal_case(list_type.name)}();
    {indent}{list_type.name}_vec.reserve(capnp_{list_type.name}.size());
    {indent}for (size_t i = 0; i < capnp_{list_type.name}.size(); ++i) {{
        {indent}{list_type.name}_vec.push_back({element_reader_type}::Const(capnp_{list_type.name}[i]).as_struct());
'''
        else:
            content += f'''
    {indent}std::vector<{element_reader_type}> {list_type.name}_vec;
    {indent}auto capnp_{list_type.name} = {accessor_name}.get{to_pascal_case(list_type.name)}();
    {indent}{list_type.name}_vec.reserve(capnp_{list_type.name}.size());
    {indent}for (size_t i = 0; i < capnp_{list_type.name}.size(); ++i) {{
        {indent}{list_type.name}_vec.push_back(capnp_{list_type.name}[i]);
'''

    if any_list_type:
        content += f'    {indent}}}\n'

    content += f"""
    {indent}return {struct_name}_Native{{
"""

    for field in fields:
        field_name = field.name
        field_type = field.type
        if field_type.kind == "struct":
            field_type_name = parse_type_name_from_type_info(field_type, lib_name=lib_name)
            content += f"        {indent}{field_type_name}::Const({accessor_name}.get{to_pascal_case(field_name)}()).as_struct(),\n"
        elif field_type.kind == "list":
            content += f"        {indent}std::move({field_name}_vec),\n"
        else:
            content += f"        {indent}{accessor_name}.get{to_pascal_case(field_name)}(),\n"

    content = content.rstrip(",\n")  # Remove the trailing comma and newline
    content += f"\n    {indent}}};\n{indent}}}\n" # end of as_struct method

    return content

def scaffold_structs(structs: Dict[str, StructInfo],
        registry_plugin_type_file: str, lib_name: str, output_path: Path) -> None:

    generated_h_name = Path(registry_plugin_type_file).name + ".h"

    for struct_name, struct in structs.items():
        struct_file_name = f"{struct_name}.hpp"
        if output_path.is_dir():
            file_path = output_path / "cpp" / "rpp_schema" / lib_name / struct_file_name
        else:
            file_path = output_path
        if file_path.exists():
            return  # Avoid overwriting existing files

        type_aliases = []
        include_types = []
        for field in struct.fields:
            field_type = parse_type_name_from_type_info(field.type,
                    lib_name=lib_name, type_aliases=type_aliases, include_types=include_types)
        include_types_str = "\n".join(include_types)

        content = f'''#pragma once
#include <string>
#include <vector>
#include <map>
#include "capnp_gen/{lib_name}/{generated_h_name}"
#include <capnp/message.h>
#include <capnp/serialize-packed.h>
#include <memory>

{include_types_str}

namespace rpp_schema::{lib_name}{{
'''
        content += f"""\n
struct {struct_name}_Native {{

"""
        list_types = []
        for field in struct.fields:
            field_type = parse_type_name_from_type_info(field.type, lib_name=lib_name)
            field_name = field.name
            if field.type.kind == "list":
                element_type_name = parse_type_name_from_type_info(field.type.element_type, lib_name=lib_name)
                if field.type.element_type.kind == "struct":
                    element_type_name += "_Native"
                content += f"    std::vector<{element_type_name}> {field_name};\n"
                list_types.append(field)
            elif field.type.kind == "struct":
                content += f"    {field_type}_Native {field_name};\n"
            else:
                content += f"    {field_type} {field_name};\n"

        content += "};\n" # end of Native struct definition

        content += f'''

class {struct_name} {{
public:
'''

        content += f'''

    class Const {{

        private:
            schema::{lib_name}::{struct_name}::Reader reader_;
            std::unique_ptr<capnp::MallocMessageBuilder> orphaned_msg_builder_;
        public:
            Const(schema::{lib_name}::{struct_name}::Reader reader)
            : reader_(reader) {{}}
            virtual ~Const() = default;
            Const(const {struct_name}& main_wrapper);
            Const({struct_name}&& main_wrapper)
            : reader_(main_wrapper.builder_.asReader()),
              orphaned_msg_builder_(std::move(main_wrapper.msg_builder_)) {{}}

            operator schema::{lib_name}::{struct_name}::Reader() const {{ return reader_; }}
'''
        for list_type in list_types:
            field_name = list_type.name
            element_type = list_type.type.element_type
            element_reader_type = parse_type_name_from_type_info(element_type, lib_name=lib_name)
            if element_type.kind == "struct":
                element_reader_type += "::Const"
            content += f'''
            struct {field_name}_ListProxy {{
                private:
                    schema::{lib_name}::{struct_name}::Reader r;
                public:
                    {field_name}_ListProxy(schema::{lib_name}::{struct_name}::Reader r) : r(r) {{}}
                    size_t size() const {{ return r.get{to_pascal_case(field_name)}().size(); }}\n
                    {element_reader_type} operator[](size_t index) const {{ return r.get{to_pascal_case(field_name)}()[index]; }}\n
            }};\n
'''

        # FIELD ACCESSORS
        for field in struct.fields:
            field_type = parse_type_name_from_type_info(field.type, lib_name=lib_name)
            field_name = field.name
            if field.type.kind == "struct":
                content += f'''
            inline {field_type}::Const {field_name}() const {{ return {field_type}::Const(reader_.get{to_pascal_case(field_name)}()); }}\n
'''
            elif field.type.kind == "list":
                content += f'''
            inline {field_name}_ListProxy {field_name}() const {{ return {field_name}_ListProxy{{reader_}}; }}\n
'''
            else:
                content += f'''
            inline {field_type} {field_name}() const {{ return reader_.get{to_pascal_case(field_name)}(); }}\n
'''

        content += make_as_struct_method_string(struct_name, struct.fields,
                lib_name, indent="            ", accessor_name="reader_")
        content += '    };\n'  # Close the Const class definition
        content += f'''

    private:
        friend class Const;
        std::unique_ptr<capnp::MallocMessageBuilder> msg_builder_;
        schema::{lib_name}::{struct_name}::Builder builder_;

'''
        for field in struct.fields:
            if field.type.kind == "primitive":
                name = field.name
                type_name = parse_type_name_from_type_info(field.type, lib_name=lib_name)
                content += f'''
        struct {name}_Proxy {{
            private:
                schema::{lib_name}::{struct_name}::Builder& builder_;
            public:
                {name}_Proxy(schema::{lib_name}::{struct_name}::Builder& builder) : builder_(builder) {{}}
                operator {type_name}() const {{ return builder_.get{to_pascal_case(name)}(); }}
                {name}_Proxy& operator=({type_name} value) {{
                    builder_.set{to_pascal_case(name)}(value);
                    return *this;
                }}
        }};
'''
            elif field.type.kind == "list":
                name = field.name
                element_type_name = parse_type_name_from_type_info(field.type.element_type, lib_name=lib_name)
                element_type_kind = field.type.element_type.kind
                if element_type_kind == "struct":
                    element_type_name_const = f"{element_type_name}::Const"
                else:
                    element_type_name_const = element_type_name
                content += f'''
        struct {name}_ListProxy {{
            private:
                schema::{lib_name}::{struct_name}::Builder& builder_;
            public:
                {name}_ListProxy(schema::{lib_name}::{struct_name}::Builder& builder) : builder_(builder) {{}}
                size_t size() const {{ return builder_.asReader().get{to_pascal_case(name)}().size(); }}
                void init(size_t new_size) {{ builder_.init{to_pascal_case(name)}(new_size); }}

                {element_type_name_const} operator[](size_t index) const {{
                    return {element_type_name_const}(builder_.asReader().get{to_pascal_case(name)}()[index]);
                }}
'''
                if element_type_kind == "primitive":
                    content += f'''
                struct {name}_ElementProxy {{
                    private:
                        capnp::List<{element_type_name}>::Builder b;
                        size_t idx;
                    public:
                        {name}_ElementProxy(capnp::List<{element_type_name}>::Builder b, size_t idx) : b(b), idx(idx) {{}}
                        operator {element_type_name}() const {{ return b.asReader()[idx]; }}

                        {name}_ElementProxy& operator=({element_type_name} value) {{
                            b.set(idx, value);
                            return *this;
                        }}
                }};

                {name}_ElementProxy operator[](size_t index) {{
                    return {name}_ElementProxy{{builder_.get{to_pascal_case(name)}(), index}};
                }}
'''
                else:
                    content += f'''                {element_type_name} operator[](size_t index) {{
                    return {element_type_name}(builder_.get{to_pascal_case(name)}()[index]);
                }}
'''
                content += '        };\n'


        content += f'''
    public:

        {struct_name}()
            : msg_builder_(std::make_unique<capnp::MallocMessageBuilder>()),
              builder_(msg_builder_->initRoot<schema::{lib_name}::{struct_name}>()) {{}}
        {struct_name}(schema::{lib_name}::{struct_name}::Builder builder)
            : msg_builder_(nullptr), builder_(builder) {{}}

        //{struct_name}(schema::{lib_name}::{struct_name}::Reader reader)
        //    : msg_builder_(std::make_unique<capnp::MallocMessageBuilder>()),
        //      builder_(msg_builder_->initRoot<schema::{lib_name}::{struct_name}>()) {{
        //        builder_.setRoot(reader);
        //}}

        virtual ~{struct_name}() = default;

        {struct_name}({struct_name}&&) = default;
        {struct_name}& operator=({struct_name}&&) = default;

        //operator Const() const {{
        //    return Const(const_cast<{struct_name}*>(this)->builder_.asReader());
        //}}


'''

        for field in struct.fields:
            name = field.name
            type_name = parse_type_name_from_type_info(field.type, lib_name=lib_name)
            if field.type.kind == "primitive":
                content += f'''
        {name}_Proxy {name}() {{ return {name}_Proxy{{builder_}}; }}
        {type_name} {name}() const {{ return builder_.asReader().get{to_pascal_case(name)}(); }}
'''
            elif field.type.kind == "list":
                content += f'''
        {name}_ListProxy {name}() {{ return {name}_ListProxy{{builder_}}; }}
        const Const::{name}_ListProxy {name}() const {{ return Const::{name}_ListProxy{{builder_}}; }}
'''
            else:
                content += f'''
        {type_name} {name}() {{ return {type_name}(builder_.get{to_pascal_case(name)}()); }}
        {type_name}::Const {name}() const {{ return {type_name}::Const(builder_.asReader().get{to_pascal_case(name)}()); }}
'''


        content += make_as_struct_method_string(struct_name,
                struct.fields, lib_name, indent="        ", accessor_name="builder_.asReader()")

        content += f"""
        {struct_name}::Const as_const() const {{
            return {struct_name}::Const(builder_.asReader());
        }}\n
"""
        content += "};\n"  # Close the Builder struct definition


        content += f'''
inline {struct_name}::Const::Const(const {struct_name}& main_wrapper)
    : reader_(const_cast<schema::{lib_name}::{struct_name}::Builder&>(main_wrapper.builder_).asReader()) {{}}

'''

        content += f"}}  // namespace {lib_name}\n"

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

def scaffold_cpp(description: PluginTypeInfo, output_path: Path, only_stubs: bool = False) -> None:

    lib_name = description.info["Library"]
    registry_plugin_type_file = description.register_data.registry_plugin_type_file

    capnp_dir = scaffold_capnp_stubs(Path(registry_plugin_type_file),
            lib_name, output_path, capnp_language="c++", language_dir_name="cpp")

    # make symlink to capnp generated files in the cpp directory
    symlink_path = capnp_dir / lib_name
    if not symlink_path.exists():
        symlink_path.symlink_to(capnp_dir, target_is_directory=True)

    if any(description.parse_data.structs):
        scaffold_structs(description.parse_data.structs, registry_plugin_type_file, lib_name, output_path)

    if only_stubs:
        return

    generate_plugin_type_hpp(description, output_path)
    generate_plugin_type_foreign_language_adapter_client_hpp(description, output_path)
    generate_plugin_type_foreign_language_adapter_server_hpp(description, output_path)