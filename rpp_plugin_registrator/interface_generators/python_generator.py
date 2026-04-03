from __future__ import annotations

from typing import Any, Dict

from .common import map_type_to_target, plugin_name_to_identifier


def generate(description: Dict[str, Any]) -> str:
    plugin = description["plugin"]
    lines = [
        "from __future__ import annotations",
        "",
        "from typing import Any, Protocol",
        "",
        f"class {plugin_name_to_identifier(plugin)}Plugin(Protocol):",
    ]

    for method in plugin["interface"]["methods"]:
        params = ", ".join(
            f"{param['name']}: {map_type_to_target(param['type'], 'python')}" for param in method["params"]
        )
        param_list = f", {params}" if params else ""
        return_type = map_type_to_target(method["return_type"], "python")
        lines.append(f"    def {method['name']}(self{param_list}) -> {return_type}: ...")

    return "\n".join(lines) + "\n"
