from .plejd_device import PlejdInput
from .device_type import PlejdDeviceType

class PlejdButton(PlejdInput):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outputType = PlejdDeviceType.BUTTON

    @property
    def button_id(self):
        return self.settings.input