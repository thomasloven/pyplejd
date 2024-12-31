from enum import StrEnum

class PlejdDeviceType(StrEnum):
    LIGHT = "LIGHT"
    SWITCH = "RELAY"
    BUTTON = "SENSOR"
    MOTION = "MOTION"
    COVER = "COVERABLE"
    SCENE = "SCENE"
    UNKNOWN = "UNKNOWN"