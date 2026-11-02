from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
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


def import_module_from_path(module_path: str | Path, allow_relative_imports: bool = False):
    path = Path(module_path).resolve()
    if not path.is_file():
        raise ValueError(f"Module path '{module_path}' does not exist.")
    module_name = path.stem
    if not allow_relative_imports:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ValueError(f"Could not find module '{module_name}' at path '{module_path}'.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    parent_dir = path.parent
    path_hash = hashlib.sha256(str(parent_dir).encode("utf-8")).hexdigest()[:16]
    package_name = f"_rpp_plugin_{path_hash}"
    qualified_name = f"{package_name}.{module_name}"

    cached_module = sys.modules.get(qualified_name)
    cached_path = getattr(cached_module, "__file__", None)
    if cached_module is not None and cached_path and Path(cached_path).resolve() == path:
        return cached_module

    package_created = package_name not in sys.modules
    if package_created:
        package = ModuleType(package_name)
        package.__path__ = [str(parent_dir)]
        package.__package__ = package_name
        package.__file__ = str(parent_dir / "__init__.py")
        sys.modules[package_name] = package

    spec = importlib.util.spec_from_file_location(
        qualified_name,
        str(path)
    )

    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to create specification for module {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified_name] = module
    try:
        spec.loader.exec_module(module)
        return module
    except Exception:
        sys.modules.pop(qualified_name, None)
        if package_created:
            sys.modules.pop(package_name, None)
        raise

