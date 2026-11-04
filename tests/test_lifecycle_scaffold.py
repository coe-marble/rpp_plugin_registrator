"""Lifecycle state bindings through schema parsing and native code generation."""

import importlib.util
import inspect
from pathlib import Path
import shutil
import subprocess
import sys
from types import ModuleType

import pytest
import rpp_common

from rpp_plugin_registrator.plugin_descriptors import capnp as descriptor
from rpp_plugin_registrator.plugin_descriptors.core import PluginTypeInfo
from rpp_plugin_registrator.payload_builders import build_plugin_type_info_payload
from rpp_plugin_registrator.plugin_scaffold.cpp_scaffold import generate_plugin_type_hpp
from rpp_plugin_registrator.plugin_scaffold.python_scaffold import (
    generate_plugin_adapter_client, generate_plugin_class, generate_structs,
)


@pytest.fixture
def schema(tmp_path, monkeypatch):
    root = tmp_path / "interfaces"
    annotations = root / "rpp_common" / "anot.capnp"
    annotations.parent.mkdir(parents=True)
    common = Path(rpp_common.__file__).parent
    shutil.copyfile(common / "common_plugin_types/rpp_common/anot.capnp", annotations)
    (annotations.parent / "foreign.capnp").write_text(
        "@0xb9930f627dccb8de; struct ForeignState { value @0 :Float64; }")
    monkeypatch.setattr(descriptor, "get_app_capnp_interfaces_path", lambda: root)

    def parse(binding=None, *, minimal=False):
        annotation = "" if binding is None else f'$Anot.lifecycleState("{binding}")'
        extras = "" if minimal else '''
using Imported = import "rpp_common/foreign.capnp".ForeignState;
struct Generic(T) { value @0 :T; }
interface Other {}
'''
        source = tmp_path / "localizer.capnp"
        source.write_text(f'''@0xd7f3d1e3ffb2d307;
using Anot = import "rpp_common/anot.capnp";
struct Estimate {{ position @0 :List(Float64); }}
{extras}
interface Localizer $Anot.plugin("Localizer") {annotation} {{}}
''')
        return descriptor.parse_capnp_plugin(source, None, relative_to_source=False)

    return parse


def description(result):
    assert result.is_valid, result.message
    interface = result.data.interfaces["Localizer"]
    info = build_plugin_type_info_payload(
        result.data.plugins[0], interface, Path(result.data.source_file))
    info["Library"] = "lifecycle_fixture"
    return PluginTypeInfo(info, parse_data=result.data)


def test_absent_binding_is_stateless(schema):
    desc = description(schema())
    assert desc.get_interface().lifecycle_state is None
    assert desc.info.get("LifecycleState") is None


def test_binding_records_struct_and_stable_schema_identity(schema):
    first = description(schema("Estimate"))
    second = description(schema("Estimate"))
    state = first.info["LifecycleState"]
    assert state["Name"] == "Estimate"
    assert state["Kind"] == "struct"
    assert state["SchemaId"] == second.info["LifecycleState"]["SchemaId"]
    assert int(state["SchemaId"], 16) > 0


@pytest.mark.parametrize("binding", ["Missing", "Other", "", "Estimate.position",
                                     "Generic", "Imported"])
def test_invalid_binding_is_rejected(schema, binding):
    result = schema(binding)
    assert not result.is_valid
    assert result.data is None
    assert "lifecycleState" in result.message
    assert "Localizer" in result.message


@pytest.mark.parametrize("stateful", [False, True])
def test_generated_python_callbacks_and_dispatch(schema, tmp_path, monkeypatch, stateful):
    desc = description(schema("Estimate" if stateful else None))
    generate_structs(desc, tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path / "python"))
    # Keep temporary generated schema modules scoped to this test.
    original_modules = set(sys.modules)
    plugin_file, _ = generate_plugin_class(desc, tmp_path)
    try:
        spec = importlib.util.spec_from_file_location("lifecycle_test_base", plugin_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        base = module.Localizer
        assert base().configure(object()).success
        assert base().cleanup().success
        assert list(inspect.signature(base.on_activate).parameters) == (
            ["self", "state"] if stateful else ["self"])
        from rpp_py.lifecycle import CallbackResult, DeactivationResult
        if stateful:
            from rpp_schema.lifecycle_fixture.Estimate import Estimate

            class Implementation(base):
                def on_activate(self, state=None):
                    self.estimate = state
                    return CallbackResult()

                def on_deactivate(self):
                    return DeactivationResult(state=self.estimate)

            plugin = Implementation()
            incoming = Estimate(position=[1.0])
            plugin.activate_state(incoming)
            incoming.position.append(2.0)
            assert plugin.deactivate_state().state.position == [1.0]
        else:
            assert base().activate_state().success
            assert base().deactivate_state().state is None

        # A remote adapter must not report a local no-op as successful control
        # of the hosted plugin. Stateful adapters must supply concrete callbacks.
        desc.info["PluginTypeName"] = "lifecycle_fixture::Localizer"
        for name in ("rpp_plugin_types", "rpp_plugin_types.lifecycle_fixture"):
            package = ModuleType(name)
            package.__path__ = []
            monkeypatch.setitem(sys.modules, name, package)
        monkeypatch.setitem(sys.modules, "rpp_plugin_types.lifecycle_fixture.Localizer", module)
        adapter_file = generate_plugin_adapter_client(desc, plugin_file)
        adapter_spec = importlib.util.spec_from_file_location("lifecycle_test_adapter", adapter_file)
        adapter_module = importlib.util.module_from_spec(adapter_spec)
        adapter_spec.loader.exec_module(adapter_module)
        adapter = adapter_module.Localizer_AdapterClient()
        from rpp_py.lifecycle import LifecycleError
        for operation, args in (("configure", (object(),)), ("activate_state", ()),
                                ("deactivate_state", ()), ("cleanup", ())):
            with pytest.raises(LifecycleError, match="Remote lifecycle"):
                getattr(adapter, operation)(*args)
    finally:
        for name in set(sys.modules) - original_modules:
            if name == "rpp_schema" or name.startswith("rpp_schema."):
                sys.modules.pop(name, None)


@pytest.mark.parametrize("stateful", [False, True])
def test_generated_cpp_uses_lifecycle_base(schema, tmp_path, stateful):
    desc = description(schema("Estimate" if stateful else None))
    output = tmp_path / "Localizer.hpp"
    generate_plugin_type_hpp(desc, output)
    # Isolate the generated base from runtime/adapters: this test verifies that
    # users can override its native callback signatures in real C++.
    support = tmp_path / "rpp_cpp"
    support.mkdir()
    runtime_header = Path(__file__).resolve().parents[2] / "rpp_cpp/include/rpp_cpp/plugin_def.hpp"
    (support / "plugin.hpp").write_text(f'#include "{runtime_header}"\n')
    (support / "context.hpp").write_text("")
    (tmp_path / "Localizer_Adapter_Client.hpp").write_text("")
    (tmp_path / "Localizer_Adapter_Server.hpp").write_text("")
    if stateful:
        state_header = tmp_path / "rpp_schema/lifecycle_fixture/Estimate.hpp"
        state_header.parent.mkdir(parents=True)
        state_header.write_text('''#include <vector>
namespace rpp_schema::lifecycle_fixture {
struct Estimate_Native {std::vector<double> position;};
}
''')
        callbacks = '''
    rpp::CallbackResult on_activate(const std::optional<LifecycleState> &) override {return {};}
    rpp::DeactivationResult<LifecycleState> on_deactivate() override {return {};}
'''
    else:
        callbacks = '''
    rpp::CallbackResult on_activate() override {return {};}
    rpp::CallbackResult on_deactivate() override {return {};}
'''
    source = tmp_path / "check.cpp"
    source.write_text('''#include "Localizer.hpp"
class Implementation : public lifecycle_fixture::Localizer {
    rpp::CallbackResult on_configure(const rpp::ComponentContext &) override {return {};}
    rpp::CallbackResult on_cleanup() override {return {};}
''' + callbacks + '''
};
static_assert(!std::is_abstract_v<Implementation>);
''')
    result = subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Wpedantic", "-fsyntax-only",
         "-I", str(tmp_path), str(source)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("stateful", [False, True])
def test_real_cpp_adapters_compile_and_reject_unsupported_lifecycle(
        schema, tmp_path, monkeypatch, stateful):
    # Runtime headers are generated by Cap'n Proto 1.1.0. Run the real compiler
    # test in the pinned integration environment rather than stub its headers.
    if "1.1.0" not in subprocess.check_output(["capnp", "--version"], text=True):
        pytest.skip("Requires the pinned Cap'n Proto 1.1.0 integration environment")
    from rpp_plugin_registrator import registry_config as rp
    from rpp_plugin_registrator.plugin_registrator.capnp import register_capnp_plugin_type
    from rpp_plugin_registrator.plugin_registrator.cpp_helpers import (
        RPP_CPP_PATH, get_cpp_imports_for_rpp, get_rpp_cpp_core_shared_library_path,
    )
    from rpp_plugin_registrator.plugin_scaffold.cpp_scaffold import scaffold_cpp
    from rpp_plugin_registrator.plugin_scaffold.scaffold_capnp_stubs import scaffold_capnp_stubs

    desc = description(schema("Estimate" if stateful else None, minimal=True))
    desc.info["PluginTypeName"] = "lifecycle_fixture::Localizer"
    monkeypatch.setattr(rp, "RPP_HOME", tmp_path / "home")
    capnp_root = rp.get_app_capnp_interfaces_path()
    annotations = capnp_root / "rpp_common/anot.capnp"
    annotations.parent.mkdir(parents=True)
    shutil.copyfile(Path(rpp_common.__file__).parent /
                    "common_plugin_types/rpp_common/anot.capnp", annotations)
    registered = register_capnp_plugin_type(desc)
    assert registered.success, registered.message
    desc.register_data = registered.register_data
    output = rp.get_app_interfaces_path()
    output.mkdir(parents=True, exist_ok=True)
    scaffold_capnp_stubs(annotations, "rpp_common", output, "c++", "cpp")
    scaffold_cpp(desc, output)

    source = tmp_path / "adapter.cpp"
    source.write_text('''#include <rpp_plugin_types/lifecycle_fixture/Localizer.hpp>
#include <type_traits>
namespace rpp {
class ComponentContextAccess {
public:
    static ComponentContext make() {return ComponentContext(std::shared_ptr<RppLogger>{});}
};
}
using Client = lifecycle_fixture::hidden::Localizer_Adapter_Client;
static_assert(!std::is_abstract_v<Client>);
int main() {
    Client client;
    auto context = rpp::ComponentContextAccess::make();
    if (client.configure(context).success || client.cleanup().success) {return 1;}
    if (client.activate_state().success) {return 2;}
    auto stopped = client.deactivate_state();
    if (stopped.result.success || stopped.state.has_value()) {return 3;}
    return 0;
}
''')
    core_path, core_library = get_rpp_cpp_core_shared_library_path()
    executable = tmp_path / "adapter"
    sources = [*sorted((output / "cpp/capnp_gen").rglob("*.c++")),
               RPP_CPP_PATH / "src/plugin_runtime.capnp.c++"]
    command = ["g++", "-std=c++17", str(source), *(str(path) for path in sources),
               *(f"-I{path}" for path in get_cpp_imports_for_rpp()),
               f"-L{core_path}", f"-l{core_library}", f"-Wl,-rpath,{core_path}",
               "-lcapnp-rpc", "-lcapnp", "-lkj-async", "-lkj", "-pthread",
               "-o", str(executable)]
    compiled = subprocess.run(command, capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    executed = subprocess.run([str(executable)], capture_output=True, text=True)
    assert executed.returncode == 0, executed.stderr
