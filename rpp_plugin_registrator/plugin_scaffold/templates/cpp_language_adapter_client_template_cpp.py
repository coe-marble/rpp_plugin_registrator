from __future__ import annotations

SOURCE_CONTENT = """#pragma once
#include <memory>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include "rpp_cpp/plugin.hpp"
#include "rpp_cpp/adapter_info.hpp"
#include "capnp_gen/${lib_name}/${generated_h}"
#include <capnp/ez-rpc.h>

namespace ${lib_name}::hidden{

class ${class_name}_Adapter_Client
    : public ${plugin_type_name},
      public rpp::ClientAdapter
{

private:
    std::unique_ptr<capnp::EzRpcClient> client_;
    ::schema::${lib_name}::${class_name}::Client backend_;
    std::shared_ptr<rpp::ClientAdapterParams> params_;
    std::string host_;
    uint16_t port_;
    rpp::ClientAdapterInfo info_;

public:
    explicit ${class_name}_Adapter_Client()
        : client_(nullptr),
        backend_(nullptr),
        params_(nullptr)
    {
        port_ = 0;
        info_.plugin_name = "${lib_name}::{class_name}";
        info_.plugin_type = "${plugin_type_name}";
        info_.created_at = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now().time_since_epoch());
    }

    bool configure_adapter_client__(std::shared_ptr<rpp::ClientAdapterParams> params) override {
        if (!params) {
            throw std::invalid_argument("Params cannot be null");
        }
        params_ = params;
        info_.name = params->name;
        host_ = params->host;
        port_ = params->port;
        return true;
    }

    bool connect_adapter_client__() override {
        if (host_.empty() || port_ == 0) {
            throw std::runtime_error("Params is not set. Call configure_adapter_client__ first.");
        }
        client_ = std::make_unique<capnp::EzRpcClient>(host_, port_);
        backend_ = std::move(client_->getMain<schema::${lib_name}::${class_name}>());
        return true;
    }

    const rpp::ClientAdapterInfo& get_info_adapter_client__() const override {
        return info_;
    }

    virtual ~${class_name}_Adapter_Client() noexcept = default;

$methods_string
};

}  // namespace

"""

METHOD_TEMPLATE = """    ${prototype} override {
        auto request = backend_.${method_name}Request();
${param_setters}

${response_handling}

    }
"""