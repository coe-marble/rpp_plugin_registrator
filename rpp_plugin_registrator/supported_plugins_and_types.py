from typing import List

def get_supported_plugin_type_extensions() -> List[str]:
    return [".capnp"]

def get_supported_plugin_extensions() -> List[str]:
    return [".py", '.cpp', '.hpp']
