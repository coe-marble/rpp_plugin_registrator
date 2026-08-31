REGISTER_CPP_PLUGIN_TYPE_SOURCE_TEMPLATE = """

#include <{plugin_type_source_file}>

extern "C" rpp::ServerAdapter* create_plugin_server(
        std::shared_ptr<rpp::RppLogger> logger) {{
        return static_cast<rpp::ServerAdapter*>(
            new {lib_name}::{class_name}::AdapterServer(std::move(logger)));
    }}

extern "C" void destroy_plugin_server(rpp::ServerAdapter* server) {{
        delete server;
    }}

extern "C" rpp::ClientAdapter* create_plugin_client(
        std::shared_ptr<rpp::RppLogger> logger) {{
        return static_cast<rpp::ClientAdapter*>(
            new {lib_name}::{class_name}::AdapterClient(std::move(logger)));
    }}

extern "C" void destroy_plugin_client(rpp::ClientAdapter* client) {{
        delete client;
    }}
"""
