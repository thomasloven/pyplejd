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
    if tpe == "CLIMATE":
        return dt.PlejdThermostat

    traits = dt.PlejdTraits(device["device"].traits)
    if dt.PlejdTraits.CLIMATE in traits:
        return dt.PlejdThermostat
    if dt.PlejdTraits.COVER in traits:
        return dt.PlejdCover
    if dt.PlejdTraits.POWER in traits:
        if dt.PlejdTraits.DIM in traits:
            return dt.PlejdLight
        return dt.PlejdRelay

    return dt.PlejdDevice


def inputDeviceClass(device: PlejdEntityData) -> Type[dt.PlejdDevice]:
    if device["motion"]:
        return dt.PlejdMotionSensor
    return dt.PlejdButton


def sceneDeviceClass(device: PlejdSceneData) -> Type[dt.PlejdDevice]:
    return dt.PlejdScene
