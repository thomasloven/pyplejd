from .plejd_device import PlejdInput, PlejdDeviceType


class PlejdButton(PlejdInput):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outputType = PlejdDeviceType.BUTTON

    @property
    def button_id(self):
        return self.settings.input

    def parse_state(self, update, state):
        state = {**state}
        self._state["action"] = None  # Don't save the action
        return state
