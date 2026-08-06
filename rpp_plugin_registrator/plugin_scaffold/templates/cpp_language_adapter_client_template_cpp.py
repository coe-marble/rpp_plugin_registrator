from __future__ import annotations

SOURCE_CONTENT = """#pragma once
#include <memory>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include "rpp_cpp/plugin.hpp"
#include "rpp_cpp/adapter_bases.hpp"
#include "rpp_cpp/plugin_runtime.capnp.h"
#include "capnp_gen/${lib_name}/${generated_h}"

namespace ${lib_name}::hidden{

class ${class_name}_Adapter_Client
    : public ${plugin_type_name},
      public rpp::ClientAdapter
{


private:
    std::shared_ptr<rpp::ClientAdapterParams> params_;
    rpp::ClientAdapterInfo info_;

    const kj::AsyncIoContext* io_ = nullptr;
    ::schema::${lib_name}::${class_name}::Client backend_;

public:
    explicit ${class_name}_Adapter_Client()
        : params_(nullptr),
          backend_(nullptr)
    {
        info_.plugin_name = "${lib_name}::{class_name}";
        info_.plugin_type = "${plugin_type_name}";
        info_.created_at = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now().time_since_epoch());
    }

    virtual ~${class_name}_Adapter_Client() noexcept = default;

    bool configure_adapter_client__(std::shared_ptr<rpp::ClientAdapterParams> params) override {
        if (!params) {
            throw std::invalid_argument("Params cannot be null");
        }
        params_ = params;
        info_.name = params->name;
        info_.connection_name = params->connection_name;
        return true;
    }

    bool connect_adapter_client__(const rpp::ClientContext& context) override
    {
        io_ = &context.get_io_context();

        auto client = context.get_client();
        auto bootstrap_runtime = client.castAs<rpp::runtime::PluginRuntime>();

        auto request = bootstrap_runtime.getComponentCapabilityRequest();
        request.setName(info_.connection_name);
        try {
            auto response = request.send().wait(io_->waitScope);
            backend_ = response.getPluginRef().castAs<::schema::${lib_name}::${class_name}>();
            return true;
        } catch (const kj::Exception& e) {
            // Try to reconnect using direct connection to the plugin server
            backend_ = client.castAs<::schema::${lib_name}::${class_name}>();
            return true;
        }
    }

    const rpp::ClientAdapterInfo& get_info_adapter_client__() const override {
        return info_;
    }

    void initialize(const rpp::ComponentContext& /*context */) override {
        // Initialization logic if needed
    }

    void reset() override {
        // Reset logic if needed
    }


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