from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict

from .cpp_generator import generate as generate_cpp
from .python_generator import generate as generate_python

_GENERATORS: Dict[str, Callable[[Dict], str]] = {
    "python": generate_python,
    "cpp": generate_cpp,
}


def generate_interface(description_path: Path, target_lang: str, output_path: Path) -> None:
    """Generate interface code for a plugin description."""
    description = json.loads(description_path.read_text(encoding="utf-8"))
    if target_lang not in _GENERATORS:
        raise ValueError(f"Unsupported target language '{target_lang}'. Supported: {sorted(_GENERATORS)}")

    content = _GENERATORS[target_lang](description)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
