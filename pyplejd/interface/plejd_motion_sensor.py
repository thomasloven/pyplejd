import asyncio
from .plejd_device import PlejdInput, PlejdDeviceType


class PlejdMotionSensor(PlejdInput):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outputType = PlejdDeviceType.MOTION

        self.cooldown = None
        # Motion sensors seem to timeout at 25-35 seconds
        # by the Nyquist criteria, we need our timeout to be at least
        # twice that time in order not to significantly miss any events.
        self.timeout = 75

    def parse_state(self, update, state):
        state = {**state}
        if state.get("motion", False):
            if self.cooldown:
                self.cooldown()
                self.cooldown = None

            def _callback():
                self.update_state(motion=False)

            loop = asyncio.get_running_loop()
            self.cooldown = loop.call_at(loop.time() + self.timeout, _callback).cancel

        self._state["motion"] = None
        return state
