from __future__ import annotations

import importlib.util
import json
import sys, os
from pathlib import Path
from typing import Any, Dict

import json5


def to_pascal_case(text: str) -> str:
    """Convert text to PascalCase (capitalize first letter of each word, remove underscores)."""
    return "".join(word.capitalize() for word in text.replace("_", " ").split())

def to_snake_case(name: str) -> str:
    import re
    name = name.replace('-', '_').replace(':', '_')
    name = re.sub(r'(?<!^)(?<!_)(?=[A-Z])', '_', name).lower()
    return name

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


def import_module_from_path(module_path: str, allow_relative_imports=False):
    if not os.path.exists(module_path):
        raise ValueError(f"Module path '{module_path}' does not exist.")
    module_name = os.path.splitext(os.path.basename(module_path))[0]
    if not allow_relative_imports:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise ValueError(f"Could not find module '{module_name}' at path '{module_path}'.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    path = Path(module_path).resolve()
    module_name = path.stem
    parent_dir = path.parent
    package_name = parent_dir.name

    path_added = False
    if str(parent_dir) not in sys.path:
        path_added = True
        sys.path.insert(0, str(parent_dir))

    spec = importlib.util.spec_from_file_location(
        f"{package_name}.{module_name}",
        str(path)
    )

    if spec is None:
        raise ImportError(f"Unable to create specification for module {module_path}")

    module = importlib.util.module_from_spec(spec)

    module.__package__ = package_name
    module.__path__ = [str(parent_dir)]
    sys.modules[package_name] = sys.modules.get(package_name, module)
    sys.modules[f"{package_name}.{module_name}"] = module
    try:
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        # Čišćenje u slučaju greške
        sys.modules.pop(f"{package_name}.{module_name}", None)
        if path_added:
            sys.path = sys.path[1:]
        raise e

