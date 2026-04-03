from __future__ import annotations

from pathlib import Path


def scaffold_cpp(plugin_id: str, class_name: str, output_path: Path) -> None:
    content = f'''#include <string>

#include "rpp/plugin.hpp"

namespace {{

class {class_name} final : public rpp::Plugin {{
public:
    std::string name() const override {{
        return "{plugin_id}";
    }}

    std::string execute(const std::string& input) override {{
        return input;
    }}
}};

}}  // namespace

extern "C" rpp::Plugin* create_plugin() {{
    return new {class_name}();
}}

extern "C" void destroy_plugin(rpp::Plugin* plugin) {{
    delete plugin;
}}
'''
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")