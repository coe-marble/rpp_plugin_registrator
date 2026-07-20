#include <rpp_plugin_types/rpp_common/MotionController2D.hpp>



using namespace rpp_common;

class ComponentPluginWithUsingNamespace : public MotionController2D
{
public:
    ComponentPluginWithUsingNamespace() = default;

    virtual ~ComponentPluginWithUsingNamespace() = default;

    VectorPlanar::Const step(Pose2D::Const state, double dt) override
    {
        auto a = 5;
    }

    bool validate(Pose2D::Const state) override
    {
        Pose2D_S native_struct = state.as_struct();
        auto x = native_struct.position.x;
        return x > 5.0;
    }

};


