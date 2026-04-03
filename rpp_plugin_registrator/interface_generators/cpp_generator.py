from __future__ import annotations

from typing import Any, Dict

from .common import map_type_to_target, plugin_name_to_identifier


def generate(description: Dict[str, Any]) -> str:
    plugin = description.get("Plugin", {})
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

    interface = plugin.get("Interface", {})
    for method in interface.get("Methods", []):
        params_block = method.get("Params", [])
        params = ", ".join(
            f"{map_type_to_target(param.get('Type', 'any'), 'cpp')} {param.get('Name')}"
            for param in params_block
        )
        return_type = map_type_to_target(
            method.get("ReturnType", "any"),
            "cpp",
        )
        method_name = method.get("Name", "method")
        lines.append(f"    virtual {return_type} {method_name}({params}) = 0;")

    lines.append("};")
    lines.append("")
    return "\n".join(lines)
