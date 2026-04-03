from __future__ import annotations

from typing import Any, Dict

from .common import map_type_to_target, plugin_name_to_identifier


def generate(description: Dict[str, Any]) -> str:
    plugin = description.get("Plugin", {})
    lines = [
        "from __future__ import annotations",
        "",
        "from typing import Any, Protocol",
        "",
        f"class {plugin_name_to_identifier(plugin)}Plugin(Protocol):",
    ]

    interface = plugin.get("Interface", {})
    for method in interface.get("Methods", []):
        params_block = method.get("Params", [])
        params = ", ".join(
            f"{param.get('Name')}: {map_type_to_target(param.get('Type', 'any'), 'python')}"
            for param in params_block
        )
        param_list = f", {params}" if params else ""
        return_type = map_type_to_target(
            method.get("ReturnType", "any"),
            "python",
        )
        method_name = method.get("Name", "method")
        lines.append(f"    def {method_name}(self{param_list}) -> {return_type}: ...")

    return "\n".join(lines) + "\n"
