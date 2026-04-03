from __future__ import annotations

from typing import Any, Dict


def map_type_to_target(source_type: str, target_lang: str) -> str:
    normalized = source_type.lower()
    mapping = {
        "python": {
            "string": "str",
            "str": "str",
            "any": "Any",
            "int": "int",
            "float": "float",
            "bool": "bool",
            "none": "None",
            "void": "None",
        },
        "cpp": {
            "string": "std::string",
            "str": "std::string",
            "any": "std::string",
            "int": "int",
            "float": "double",
            "bool": "bool",
            "none": "void",
            "void": "void",
        },
    }

    return mapping.get(target_lang, {}).get(normalized, mapping.get(target_lang, {}).get("any", "unknown"))


def plugin_name_to_identifier(plugin: Dict[str, Any]) -> str:
    return plugin["name"].title().replace("_", "")
