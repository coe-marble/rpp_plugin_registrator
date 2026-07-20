from __future__ import annotations


from rpp_plugin_types.rpp_common import MotionController2D
from rpp_plugin_types.rpp_common import DisturbanceGenerator2D
from rpp_common import ParameterDescription

class SuperClass:
    def __init__(self, a = 1, b = 2):
        self.a = a
        self.b = b

class ComponentPluginPy(MotionController2D):
    COMPONENTS = {
        "ctl_main": "rpp_common::MotionController2D",
        "ctl_disturbance": "rpp_common::DisturbanceGenerator2D",
    }

    PARAMETERS = [
        ParameterDescription("param1", 1.1),
        ParameterDescription("param2", 2),
        ParameterDescription("param3", "default_string"),
        ParameterDescription("param4", True),
        ParameterDescription("param5", [1, 2, 3]),
        ParameterDescription("param6", {"key1": "value1", "key2": 2}),
        ParameterDescription("param7", SuperClass(a=10))
    ]

    def __init__(self):
        super().__init__()

    def validate(self, state : MotionController2D.Pose2D) -> bool:

        x = state.position.x
        return x > 5.0

    def step(self, state: MotionController2D.Pose2D, dt: float) -> None:
        # Implement the control logic here
        pass
