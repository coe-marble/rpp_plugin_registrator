"""Async belongs to component methods and works without a manager."""

import asyncio
import importlib.util
from pathlib import Path

import pytest

from rpp_plugin_registrator.plugin_descriptors.core import (
    FieldInfo, InterfaceInfo, MethodInfo, ParsePluginTypeData, PluginTypeInfo, TypeInfo,
)
from rpp_plugin_registrator.plugin_descriptors.python import parse_python_plugin
from rpp_plugin_registrator.plugin_scaffold.python_scaffold import generate_plugin_class


@pytest.mark.parametrize("async_implementation", [False, True])
def test_generated_native_component_is_awaitable_on_the_callers_loop(tmp_path, async_implementation):
    value = TypeInfo(name="int32", kind="primitive")
    description = PluginTypeInfo(
        info={"ClassName": "Calculator", "Library": "test"},
        parse_data=ParsePluginTypeData(source_file="calculator.capnp", source_language="capnp",
            interfaces={"Calculator": InterfaceInfo(name="Calculator", methods=[
                MethodInfo(name="compute", params=[FieldInfo("value", value)],
                           results=[FieldInfo("result", value)])])}))
    path, _ = generate_plugin_class(description, tmp_path / "Calculator.py")
    spec = importlib.util.spec_from_file_location("test_async_base", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class Synchronous(module.Calculator):
        def compute(self, value):
            return value * 2

    class Asynchronous(module.Calculator):
        async def compute(self, value):
            self.loop = asyncio.get_running_loop()
            await asyncio.sleep(0)
            return value * 2

    component = Asynchronous() if async_implementation else Synchronous()

    async def application():
        assert await component.compute_async(3) == 6
        if async_implementation:
            assert component.loop is asyncio.get_running_loop()

    asyncio.run(application())


def test_async_plugin_methods_are_included_in_the_descriptor(tmp_path):
    path = tmp_path / "plugin.py"
    path.write_text('''from rpp_py.plugin import Plugin
class AsyncCalculator(Plugin):
    async def compute(self, value: int) -> int:
        return value * 2
''')
    parsed = parse_python_plugin(path, None)
    assert parsed.is_valid
    methods = parsed.data.plugins[0]["Methods"]
    assert [method["Name"] for method in methods] == ["compute"]
