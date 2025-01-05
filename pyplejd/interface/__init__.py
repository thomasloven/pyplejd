from __future__ import annotations

from typing import Type

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

    traits = dt.PlejdTraits(device["device"].traits)
    if dt.PlejdTraits.COVER in traits:
        return dt.PlejdCover
    if dt.PlejdTraits.POWER in traits:
        if notes := device["plejdDevice"].firmware.notes:
            if "CTR" in notes:
                return dt.PlejdRelay
        return dt.PlejdLight

    return dt.PlejdDevice


def inputDeviceClass(device: PlejdEntityData) -> Type[dt.PlejdDevice]:
    if device["motion"]:
        return dt.PlejdMotionSensor
    return dt.PlejdButton
    return PlejdDevice


def sceneDeviceClass(device: PlejdSceneData) -> Type[dt.PlejdDevice]:
    return dt.PlejdScene
