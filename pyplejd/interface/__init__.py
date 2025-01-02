from __future__ import annotations

from typing import TypedDict, Type

from . import device_type as DeviceTypes
from ..cloud import PlejdEntityData, PlejdSceneData

dt = DeviceTypes


def outputDeviceClass(device: PlejdEntityData) -> Type[dt.PlejdDevice]:

    if device["plejdDevice"].isFellowshipFollower:
        return dt.PlejdFellowshipFollower

    tpe = device["device"].outputType
    if tpe == "LIGHT":
        return dt.PlejdLight
    if tpe == "RELAY":
        return dt.PlejdRelay
    if tpe == "COVERABLE":
        return dt.PlejdCover

    return dt.PlejdDevice


def inputDeviceClass(device: PlejdEntityData) -> Type[dt.PlejdDevice]:
    if device["motion"]:
        return dt.PlejdMotionSensor
    return dt.PlejdButton
    return PlejdDevice


def sceneDeviceClass(device: PlejdSceneData) -> Type[dt.PlejdDevice]:
    return dt.PlejdScene
