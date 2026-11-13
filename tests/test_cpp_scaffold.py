import pytest

from rpp_plugin_registrator.plugin_descriptors.core import FieldInfo, StructInfo, TypeInfo
from rpp_plugin_registrator.plugin_scaffold.cpp_scaffold import (
    generate_methods_for_foreign_language_adapter_client,
    scaffold_structs,
)


def test_generated_adapter_client_captures_noncopyable_parameters_by_reference():
    methods = [{
        "Name": "validate",
        "Params": [{
            "Name": "state",
            "Type": {
                "Kind": "struct",
                "Name": "Pose2D",
                "CapnpTypeDisplayName": "rpp_common/Pose2D",
            },
        }],
        "Results": [{
            "Name": "ok",
            "Type": {"Kind": "primitive", "Name": "bool"},
        }],
    }]

    generated = generate_methods_for_foreign_language_adapter_client(methods)

    assert "executor_->get().call([this, &state]" in generated


def test_generated_adapter_client_retains_borrowed_results():
    """Returned Cap'n Proto readers must keep their response alive for the caller."""
    pose = {
        "Kind": "struct",
        "Name": "Pose2D",
        "CapnpTypeDisplayName": "rpp_common/Pose2D",
    }
    methods = [{
        "Name": "read_state",
        "Params": [],
        "Results": [
            {"Name": "pose", "Type": pose},
            {"Name": "history", "Type": {"Kind": "list", "ElementType": pose}},
            {"Name": "payload", "Type": {"Kind": "primitive", "Name": "data"}},
        ],
    }]

    generated = generate_methods_for_foreign_language_adapter_client(methods)

    assert "auto response_owner = executor_->get().retain(std::move(response));" in generated
    assert "Pose2D::Const(response_owner->getPose(), response_owner)" in generated
    assert "Pose2D::Const::List(response_owner->getHistory(), response_owner)" in generated
    assert "rpp::DataConst(response_owner->getPayload(), response_owner)" in generated
    # Direct clients do not have an executor, but must give the returned readers
    # equivalent shared ownership of their response.
    assert "std::make_shared<decltype(response)>(std::move(response))" in generated


def test_struct_const_scaffold_propagates_response_lifetime(tmp_path):
    pose = TypeInfo(name="Pose2D", kind="struct",
                    capnp_type_display_name="rpp_common/Pose2D")
    envelope = StructInfo(name="StateEnvelope", fields=[
        FieldInfo(name="pose", type=pose),
        FieldInfo(name="history", type=TypeInfo(name=None, kind="list", element_type=pose)),
        FieldInfo(name="payload", type=TypeInfo(name="data", kind="primitive")),
    ])

    scaffold_structs({envelope.name: envelope}, "state.capnp", "rpp_testing", tmp_path)

    header = (tmp_path / "cpp/rpp_schema/rpp_testing/StateEnvelope.hpp").read_text()
    assert "std::shared_ptr<void> message_lifetime_;" in header
    assert "std::shared_ptr<void> lifetime = nullptr" in header
    assert "message_lifetime_(std::move(lifetime))" in header
    assert "return Const(this->reader_, this->message_lifetime_);" in header
    assert (
        "::rpp_schema::rpp_common::Pose2D::Const(reader_.getPose(), message_lifetime_)"
        in header
    )
    assert (
        "::rpp_schema::rpp_common::Pose2D::Const::List{reader_.getHistory(), "
        "message_lifetime_}"
        in header
    )
    assert "rpp::DataConst(reader_.getPayload(), message_lifetime_)" in header


@pytest.mark.parametrize("dependency_library", ["rpp_common", "rpp_control"])
def test_struct_headers_qualify_nested_wrappers_and_native_types(tmp_path, dependency_library):
    matrix = TypeInfo(name="FloatMatrix", kind="struct",
                      capnp_type_display_name=f"{dependency_library}/msgs.capnp:FloatMatrix")
    struct = StructInfo(name="ControllerHandoverState", fields=[
        FieldInfo(name="state", type=matrix),
        FieldInfo(name="history", type=TypeInfo(name=None, kind="list", element_type=matrix)),
    ])

    scaffold_structs({struct.name: struct}, "controllers.capnp", "rpp_control", tmp_path)

    header = (tmp_path / "cpp/rpp_schema/rpp_control/ControllerHandoverState.hpp").read_text()
    qualified = f"::rpp_schema::{dependency_library}::FloatMatrix"
    assert f'#include "rpp_schema/{dependency_library}/FloatMatrix.hpp"' in header
    assert f"{qualified}_Native state;" in header
    assert f"std::vector<{qualified}_Native> history;" in header
    assert f"inline {qualified}::Const state() const" in header
    assert f"{qualified} state()" in header
    assert f"{qualified}::List history()" in header
    assert f"{qualified}::Const::List history() const" in header
    assert f"{qualified}::Const(reader_.getState()).as_struct()" in header
    assert f"{qualified}::Const(builder_.asReader().getState()).as_struct()" in header
    assert f"{qualified}::Const(capnp_history[i]).as_struct()" in header
