from rpp_plugin_registrator.plugin_scaffold.cpp_scaffold import (
    generate_methods_for_foreign_language_adapter_client,
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
