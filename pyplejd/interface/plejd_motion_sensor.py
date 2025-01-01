from .plejd_device import PlejdInput
from .device_type import PlejdDeviceType


class PlejdMotionSensor(PlejdInput):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outputType = PlejdDeviceType.MOTION
