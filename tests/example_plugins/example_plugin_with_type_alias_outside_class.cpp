#include <rpp_plugin_types/rpp_common/MotionController2D.hpp>


using Controller = rpp_common::MotionController2D;

class ComponentPluginWithTypeAliasOutsideClass : public Controller
{


public:
    ComponentPluginWithTypeAliasOutsideClass() = default;

    virtual ~ComponentPluginWithTypeAliasOutsideClass() = default;

    Controller::VectorPlanar::Const step(Controller::Pose2D::Const state, double dt) override
    {
        auto a = 5;
    }

    bool validate(rpp_common::MotionController2D::Pose2D::Const state) override
    {
        auto a = 5;
        return true;
    }

};


