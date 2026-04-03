from __future__ import annotations

from typing import Any, Dict

from .common import map_type_to_target, plugin_name_to_identifier


def generate(description: Dict[str, Any]) -> str:
    plugin = description["plugin"]
    class_name = f"I{plugin_name_to_identifier(plugin)}Plugin"
    lines = [
        "#pragma once",
        "",
        "#include <string>",
        "",
        f"class {class_name} {{",
        "public:",
        f"    virtual ~{class_name}() = default;",
    ]

    for method in plugin["interface"]["methods"]:
        params = ", ".join(
            f"{map_type_to_target(param['type'], 'cpp')} {param['name']}" for param in method["params"]
        )
        return_type = map_type_to_target(method["return_type"], "cpp")
        lines.append(f"    virtual {return_type} {method['name']}({params}) = 0;")

    lines.append("};")
    lines.append("")
    return "\n".join(lines)
