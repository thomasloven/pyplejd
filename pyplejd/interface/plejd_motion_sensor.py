from .plejd_device import PlejdInput


class PlejdMotionSensor(PlejdInput):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outputType = "MOTION"

    def parse_state(self, update, state):
        state = {**state}
        self._state["motion"] = None
        return state
