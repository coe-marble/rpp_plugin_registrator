from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from rpp_plugin_registrator.plugin_descriptors.core import PluginTypeInfo

from .python_scaffold import scaffold_python_from_capnp
from .cpp_scaffold import scaffold_cpp



def scaffold_plugin(description: PluginTypeInfo, output_path: Path, languages=None, only_stubs: bool = False) -> Dict[str, Any]:
    """Scaffold plugin class by inferring language from file extension."""
    if languages is None:
        languages = ["all"]

    if output_path.suffix == "":
        output_path.mkdir(parents=True, exist_ok=True)
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    any_scaffolded = False
    if "python" in languages or "all" in languages:
        scaffold_python_from_capnp(
            description, output_path, only_stubs=only_stubs)
        any_scaffolded = True
    if "cpp" in languages or "all" in languages:
        scaffold_cpp(
            description, output_path, only_stubs=only_stubs)
        any_scaffolded = True

    return any_scaffolded