from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .core import (
    MethodParam,
    MethodSpec,
    build_description,
    normalize_plugin_id,
    read_text,
)


def parse_cpp_plugin(source_file: Path, plugin_id: Optional[str]) -> Dict[str, Any]:
    text = read_text(source_file)

    class_match = re.search(
        r"class\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:final\s*)?:\s*public\s+rpp::Plugin",
        text,
        re.MULTILINE,
    )
    class_name = class_match.group(1) if class_match else None

    name_match = re.search(
        r"name\s*\(\s*\)\s*const\s*override\s*\{[\s\S]*?return\s+\"([^\"]+)\"\s*;",
        text,
        re.MULTILINE,
    )
    plugin_name = name_match.group(1) if name_match else (plugin_id or (class_name or source_file.stem))

    has_execute = bool(
        re.search(
            r"execute\s*\(\s*const\s+std::string\s*&\s*[A-Za-z_][A-Za-z0-9_]*\s*\)\s*override",
            text,
            re.MULTILINE,
        )
    )

    methods: List[MethodSpec] = [MethodSpec(name="name", return_type="string", params=[])]
    if has_execute:
        methods.append(
            MethodSpec(
                name="execute",
                return_type="string",
                params=[MethodParam(name="input", type="string")],
            )
        )

    return build_description(
        plugin_id=plugin_id or normalize_plugin_id(plugin_name),
        plugin_name=plugin_name,
        language="cpp",
        source_file=source_file,
        class_name=class_name,
        plugin_type=class_name,
        descriptions={
            "param_description": [],
            "log_description": [],
            "input_description": [],
            "output_description": [],
        },
        create_symbol="create_plugin",
        destroy_symbol="destroy_plugin",
        methods=methods,
    )
