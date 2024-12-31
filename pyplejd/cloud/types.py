try:
    from pydantic.v1 import BaseModel
except ImportError:
    from pydantic import BaseModel

from typing import TypedDict

from .site_details import Device, PlejdDevice, PlejdDeviceOutputSetting, PlejdDeviceInputSetting, Room, Scene


class PlejdCloudCredentials(TypedDict):
    username: str
    password: str
    siteId: str

class PlejdSiteSummary(BaseModel):
    title: str
    deviceCount: int
    siteId: str

class PlejdEntityData(TypedDict):
    address: int
    deviceAddress: int
    device: Device
    plejdDevice: PlejdDevice
    settings: PlejdDeviceOutputSetting | PlejdDeviceInputSetting
    room: Room
    motion: bool|None

class PlejdSceneData(TypedDict):
    scene: Scene
    index: int