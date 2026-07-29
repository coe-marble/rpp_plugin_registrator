
REGISTER_CPP_PLUGIN_SOURCE_TEMPLATE = """
#include <{source_file}>
#include <map>
#include "rpp_cpp/parameter_description.hpp"

template <typename T, typename = std::void_t<>>
struct rpp_components_extractor {{
    static const std::map<std::string, std::string>* get() {{ return nullptr; }}
}};

template <typename T>
struct rpp_components_extractor<T, std::void_t<decltype(T::COMPONENTS)>> {{
    static const std::map<std::string, std::string>* get() {{ return &T::COMPONENTS; }}
}};

template <typename T, typename = std::void_t<>>
struct rpp_parameters_extractor {{
    static const std::vector<rpp::params::ParameterDescription>* get() {{ return nullptr; }}
}};

template <typename T>
struct rpp_parameters_extractor<T, std::void_t<decltype(T::PARAMETERS)>> {{
    static const std::vector<rpp::params::ParameterDescription>* get() {{ return &T::PARAMETERS; }}
}};


extern "C" {plugin_type}* create_plugin() {{
        return new {lib_namespace}{class_name}();
    }}

extern "C" void destroy_plugin({plugin_type}* plugin) {{
        delete plugin;
    }}

extern "C" const std::map<std::string, std::string>* get_plugin_components() {{
    return rpp_components_extractor<{lib_namespace}{class_name}>::get();
}}

extern "C" const std::vector<rpp::params::ParameterDescription>* get_plugin_parameters_description() {{
    return rpp_parameters_extractor<{lib_namespace}{class_name}>::get();
}}

"""
