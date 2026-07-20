from __future__ import annotations

SOURCE_TEMPLATE = """
#pragma once

#include <memory>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <chrono>
#include "rpp_cpp/plugin.hpp"
#include "capnp_gen/${lib_name}/${generated_h}"
#include "rpp_cpp/adapter_info.hpp"
#include "rpp_cpp/capnp_server.hpp"

namespace ${lib_name}::hidden{

class ${class_name}_Adapter_Server
    : public ::schema::${lib_name}::${class_name}::Server,
      public rpp::ServerAdapter
{

private:
    std::string host_;
    uint16_t port_;
    std::shared_ptr<${lib_name}::${class_name}> backend_;
    std::unique_ptr<rpp::runtime::CapnpServer> rpc_server_ = nullptr;
    rpp::ServerAdapterInfo info_;

public:
    explicit ${class_name}_Adapter_Server()
        : host_(""),
        port_(0),
        backend_(nullptr),
        rpc_server_(nullptr)
    {
        info_.plugin_type = "${plugin_type_name}";
        info_.created_at = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now().time_since_epoch());
    }

    void start_adapter_server__(kj::AsyncIoContext& io) override {
        if (!backend_) {
            throw std::runtime_error("RPC server is not initialized. Call configure_adapter_server__ first.");
        }
        kj::Own<::schema::${lib_name}::${class_name}::Server> owned_server(
            static_cast<::schema::${lib_name}::${class_name}::Server*>(this),
            kj::NullDisposer::instance
        );

        auto server_cap = capnp::Capability::Client(std::move(owned_server));

        rpc_server_ = std::make_unique<rpp::runtime::CapnpServer>(io, server_cap, host_, port_);
    }

    bool configure_adapter_server__(std::shared_ptr<rpp::ServerAdapterParams> params) override {
        if (!params) {
            throw std::invalid_argument("Params cannot be null");
        }
        info_.name = params->name;
        info_.plugin_name = params->plugin_name;
        backend_ = std::dynamic_pointer_cast<${lib_name}::${class_name}>(params->backend);
        host_ = params->host;
        port_ = params->port;
        return true;
    }

    void close_adapter_server__() override {
        rpc_server_.reset();
    }

    const rpp::ServerAdapterInfo& get_info_adapter_server__() const override {
        return info_;
    }

    virtual ~${class_name}_Adapter_Server() noexcept = default;

${methods_string}
};

}  // namespace

"""


METHOD_TEMPLATE = """    ::kj::Promise<void> ${method_name}(${context_type} context) override {
    ${body}
}
    """