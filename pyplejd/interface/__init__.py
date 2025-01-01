from __future__ import annotations
from enum import Enum

try:
    from pydantic.v1 import BaseModel, PrivateAttr
except ImportError:
    from pydantic import BaseModel, PrivateAttr
from typing import Literal, TYPE_CHECKING, Callable, TypedDict, Type
from ..cloud import site_details as sd, PlejdEntityData

from .plejd_device import PlejdBaseDevice as PlejdDevice
from .plejd_light import PlejdLight
from .plejd_relay import PlejdRelay
from .plejd_cover import PlejdCover
from .plejd_motion_sensor import PlejdMotionSensor
from .plejd_button import PlejdButton
from .plejd_fellowship_follower import PlejdFellowshipFollower
from .plejd_scene import PlejdScene

from .device_type import PlejdDeviceType

if TYPE_CHECKING:
    from ..ble import PlejdMesh


class PlejdCloudCredentials(TypedDict):
    username: str
    password: str
    siteId: str


class PlejdSiteSummary(BaseModel):
    title: str
    deviceCount: int
    siteId: str


def outputDeviceClass(device: PlejdEntityData) -> Type[PlejdDevice]:

    if device["plejdDevice"].isFellowshipFollower:
        return PlejdFellowshipFollower

    tpe = device["device"].outputType
    if tpe == "LIGHT":
        return PlejdLight
    if tpe == "RELAY":
        return PlejdRelay
    if tpe == "COVERABLE":
        return PlejdCover

    return PlejdDevice


def inputDeviceClass(device: PlejdEntityData) -> Type[PlejdDevice]:
    if device["motion"]:
        return PlejdMotionSensor
    return PlejdButton
    return PlejdDevice
