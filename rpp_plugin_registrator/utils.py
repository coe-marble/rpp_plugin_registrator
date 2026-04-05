from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Dict

import json5


def to_pascal_case(text: str) -> str:
    """Convert text to PascalCase (capitalize first letter of each word, remove underscores)."""
    return "".join(word.capitalize() for word in text.replace("_", " ").split())

def to_snake_case(name: str) -> str:
    import re
    name = re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()
    return name.replace('-', '_')

def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_json5(path: Path) -> Dict[str, Any]:
    return json5.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Dict[str, Any], *, indent: int = 2, sort_keys: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=indent, sort_keys=sort_keys) + "\n",
        encoding="utf-8",
    )


def import_module_from_path(module_path: str):
    if not os.path.exists(module_path):
        raise ValueError(f"Module path '{module_path}' does not exist.")
    module_name = os.path.splitext(os.path.basename(module_path))[0]
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not find module '{module_name}' at path '{module_path}'.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module