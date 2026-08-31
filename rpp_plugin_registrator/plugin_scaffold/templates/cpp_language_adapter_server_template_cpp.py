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
#include "rpp_cpp/adapter_bases.hpp"
#include "rpp_cpp/capnp_server.hpp"
#include "rpp_cpp/context.hpp"
#include "rpp_cpp/logger.hpp"

namespace ${lib_name}::hidden{

class ${class_name}_Adapter_Server
    : public rpp::ServerAdapter,
      public ::schema::${lib_name}::${class_name}::Server
{

private:
    ${lib_name}::${class_name}* backend_;
    std::shared_ptr<rpp::ServerAdapterParams> params_ = nullptr;
    std::shared_ptr<rpp::RppLogger> logger_;
    rpp::ServerAdapterInfo info_;
    std::unique_ptr<rpp::runtime::CapnpServer> rpc_server_ = nullptr;

public:

    explicit ${class_name}_Adapter_Server(
        std::shared_ptr<rpp::RppLogger> logger = nullptr)
        : backend_(nullptr),
          logger_(std::move(logger))
    {
        info_.plugin_type = "${plugin_type_name}";
        info_.created_at = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now().time_since_epoch());
    }

    capnp::Capability::Client create_capability_adapter_server__() override {
        RPP_LOG_DEBUG(*logger_, "Creating component capability: component=%s.",
                      info_.name.c_str());
        kj::Own<::schema::${lib_name}::${class_name}::Server> owned_server(
            static_cast<::schema::${lib_name}::${class_name}::Server*>(this),
            kj::NullDisposer::instance
        );
        return capnp::Capability::Client(std::move(owned_server));
    }

    void start_adapter_server__(kj::AsyncIoContext& io, std::string host, uint16_t port) override {
        if (!backend_) {
            throw std::runtime_error("RPC server is not initialized. Call configure_adapter_server__ first.");
        }
        auto server_cap = create_capability_adapter_server__();
        rpc_server_ = std::make_unique<rpp::runtime::CapnpServer>(io, host, port, server_cap);
        RPP_LOG_DEBUG(*logger_, "Started adapter RPC server: component=%s host=%s port=%d.",
                      info_.name.c_str(), host.c_str(), port);
    }

    bool configure_adapter_server__(std::shared_ptr<rpp::ServerAdapterParams> params) override {
        if (!params) {
            throw std::invalid_argument("Params cannot be null");
        }
        params_ = params;
        info_.name = params->name;
        info_.plugin_name = params->plugin_name;
        info_.connection_name = params->connection_name;
        backend_ = dynamic_cast<${lib_name}::${class_name}*>(params->backend.get());
        if (!logger_) {
            logger_ = std::make_shared<rpp::RppLogger>(info_.name);
        }
        RPP_LOG_DEBUG(*logger_, "Configured adapter server: component=%s connection=%s.",
                      info_.name.c_str(), info_.connection_name.c_str());
        return true;
    }

    void close_adapter_server__() override {
        RPP_LOG_DEBUG(*logger_, "Stopping adapter RPC server: component=%s.",
                      info_.name.c_str());
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


METHOD_TEMPLATE = """    ::kj::Promise<void> ${method_name}(${context_type} ${context_if_arguments}) override {
${body}
}
    """
