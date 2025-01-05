""" All device types handled by pyplejd """

from enum import StrEnum

from .plejd_device import PlejdDevice, PlejdInput, PlejdOutput, PlejdTraits
from .plejd_button import PlejdButton
from .plejd_cover import PlejdCover
from .plejd_fellowship_follower import PlejdFellowshipFollower
from .plejd_light import PlejdLight
from .plejd_motion_sensor import PlejdMotionSensor
from .plejd_relay import PlejdRelay
from .plejd_scene import PlejdScene

__all__ = [
    "PlejdDeviceType",
    "PlejdDevice",
    "PlejdInput",
    "PlejdOutput",
    "PlejdButton",
    "PlejdCover",
    "PlejdFellowshipFollower",
    "PlejdLight",
    "PlejdMotionSensor",
    "PlejdRelay",
    "PlejdScene",
    "PlejdTraits",
]


class PlejdDeviceType(StrEnum):
    LIGHT = "LIGHT"
    SWITCH = "RELAY"
    BUTTON = "SENSOR"
    MOTION = "MOTION"
    COVER = "COVERABLE"
    SCENE = "SCENE"
    UNKNOWN = "UNKNOWN"
