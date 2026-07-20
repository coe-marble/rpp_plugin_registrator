#include <rpp_plugin_types/rpp_common/MotionController2D.hpp>
#include <rpp_schema/rpp_common/Path2D.hpp>
#include <rpp_schema/rpp_common/Command.hpp>


RPP_PARAM_STRUCT(TestStruct1,
    RPP_MEMBER(int, width, 640),
    RPP_MEMBER(std::string, height, "480"),
    RPP_MEMBER(double, fps, 30.0)
)

RPP_PARAM_STRUCT(TestStruct2,
    RPP_MEMBER(TestStruct1, struct1, TestStruct1()),
    RPP_MEMBER(std::vector<int>, values, std::vector<int>{1, 2, 3})
)

class ComponentPlugin : public rpp_common::MotionController2D
{


    public:
    RPP_COMPONENTS({
        {"ctl_1", "test_lib::ComponentPlugin"},
        {"ctl_2", "test_lib::ComponentPlugin_adapter_server"}
    })

    RPP_PARAMETERS({
        rpp::params::ParameterDescription::create<int>("int_var", 1),
        rpp::params::ParameterDescription::create<float>("float_var", 5.0f),
        rpp::params::ParameterDescription::create<std::string>("str_var", "test"),
        rpp::params::ParameterDescription::create<TestStruct1>("struct1_var", TestStruct1{}),
        rpp::params::ParameterDescription::create<TestStruct2>("struct2_var", TestStruct2{})
    })

    ComponentPlugin() = default;

    virtual ~ComponentPlugin() = default;

    VectorPlanar::Const step(Pose2D::Const state, double dt) override
    {

        rpp_schema::rpp_common::Path2D path;
        path.points().init(2);
        path.points()[0].x() = 1.0;
        path.points()[0].y() = 2.0;
        path.points()[1].x() = 3.0;
        path.points()[1].y() = 4.0;

        auto point_as_struct = path.points()[1].as_struct();

        rpp_schema::rpp_common::Command command;

        command.data().init(2);
        command.data()[0] = 0.0;
        command.data()[1] = 1.0;

        VectorPlanar vector;
        vector.x() = point_as_struct.x;
        vector.y() = command.data()[1];
        vector.yaw() = 3.14;
        return std::move(vector);
    }

    bool validate(Pose2D::Const state) override
    {
        auto x = state.position().x();
        return x > 5.0;
    }

};


