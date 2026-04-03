"""rpp_plugin_registrator package."""

from .registry_api import get_plugin_tags, get_plugin_types, load_registry, resolve_registry_path

__all__ = [
	"__version__",
	"get_plugin_tags",
	"get_plugin_types",
	"load_registry",
	"resolve_registry_path",
]
__version__ = "0.1.0"
