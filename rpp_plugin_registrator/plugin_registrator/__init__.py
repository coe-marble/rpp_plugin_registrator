from __future__ import annotations
from .dispatch import (
    register_plugin, unregister_plugin,
    register_plugin_type, unregister_plugin_type,
    generate_plugin_type_interface, remove_plugin_type_interface
)




__all__ = [
    "register_plugin",
    "unregister_plugin",
    "register_plugin_type",
    "unregister_plugin_type",
    "generate_plugin_type_interface",
    "remove_plugin_type_interface",
]
