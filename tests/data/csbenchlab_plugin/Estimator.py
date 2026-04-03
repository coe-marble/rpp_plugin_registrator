from abc import abstractmethod
from rpp_common.py.RPP_Plugin import RPP_Plugin

class Estimator(RPP_Plugin):
    tag : str = "est"

    def __init__(self, **kwargs):
        pass

    @abstractmethod
    def on_configure(self):
        """Called when the controller is configured with parameters."""
        pass

    @abstractmethod
    def on_step(self, y, dt):
        """Called on each step with the current parameters."""
        pass

    @abstractmethod
    def on_reset(self):
        """Called to reset the controller state."""
        pass