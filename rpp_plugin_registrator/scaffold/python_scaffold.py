from __future__ import annotations

from pathlib import Path


def scaffold_python(plugin_id: str, class_name: str, output_path: Path) -> None:
    content = f'''from rpp_common.py.RPP_Plugin import RPP_Plugin


class {class_name}(RPP_Plugin):
    param_description = []
    log_description = []
    input_description = []
    output_description = []

    def name(self) -> str:
        return "{plugin_id}"

    def execute(self, input: str) -> str:
        return input


def create_plugin() -> {class_name}:
    return {class_name}()


def destroy_plugin(plugin: {class_name}) -> None:
    del plugin
'''
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")