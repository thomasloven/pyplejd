from __future__ import annotations
from enum import IntFlag, StrEnum
from ..cloud import site_details as sd
from ..ble.lastdata import LastData
from ..ble.lightlevel import LightLevel

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..ble import PlejdMesh
    from .plejd_hardware import PlejdHardware


class PlejdTraits(IntFlag):
    POWER = 0x1  # Powerable
    DIM = 0x2  # Dimmable
    TEMP = 0x4  # WhiteTunable
    GROUP = 0x8  # Groupable

    COVER = 0x10  # Coverable
    TILT = 0x40  # CoverTiltable

    CLIMATE = 0x20  # ClimateControllable
    CLIMATE_PWM = 0x80


class PlejdDeviceType(StrEnum):
    LIGHT = "LIGHT"
    SWITCH = "RELAY"
    BUTTON = "SENSOR"
    MOTION = "MOTION"
    COVER = "COVERABLE"
    CLIMATE = "CLIMATE"
    SCENE = "SCENE"
    UNKNOWN = "UNKNOWN"


class PlejdDevice:
    def __init__(
        self,
        address: int,
        deviceAddress: int,
        device: sd.Device,
        plejdDevice: sd.PlejdDevice,
        settings: sd.PlejdDeviceOutputSetting | sd.PlejdDeviceInputSetting,
        room: sd.Room,
        mesh: PlejdMesh,
        rxAddress: int,
        *_,
        first_device: sd.Device = None,
        **__,
    ):
        self.address = address
        self.rxAddress = rxAddress
        self.deviceAddress = deviceAddress
        self.plejdDevice = plejdDevice
        self.settings = settings
        self.deviceData = device
        self.roomData = room

        self._mesh = mesh
        self._state = {}

        self._listeners = set()

        self.outputType = PlejdDeviceType.UNKNOWN
        self.identifier = None
        self.is_primary = first_device
        self.device_identifier = f"{plejdDevice.deviceId}:{device.objectId}"
        self.parent_identifier = (
            f"{plejdDevice.deviceId}:{first_device.objectId}"
            if first_device
            else self.device_identifier
        )
        self.capabilities = PlejdTraits(self.deviceData.traits)
        self.ble_mac = ":".join(
            device.deviceId[i : i + 2] for i in range(0, len(device.deviceId), 2)
        )
        self.hw: PlejdHardware = None

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.BLEaddress} ({self.address}) {self.name} [{self.hardware}] {self.outputType}-{self.capabilities!r}>"

    def match_state(self, state):
        if state.get("address") in [self.address, self.rxAddress]:
            return True
        return False

    def subscribe(self, listener):
        self._listeners.add(listener)

        def remover():
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remover

    async def parse_lightlevel(self, data: LightLevel):
        pass

    async def parse_lastdata(self, data: LastData):
        pass

    def set_available(self, available=False):
        self._state["available"] = available
        for listener in self._listeners:
            listener(self._state)

    @property
    def BLEaddress(self):
        return self.deviceData.deviceId

    @property
    def powered(self):
        return (
            PlejdTraits.POWER in self.capabilities
            or PlejdTraits.COVER in self.capabilities
            or PlejdTraits.CLIMATE in self.capabilities
        )

    @property
    def name(self):
        return self.deviceData.title

    @property
    def room(self):
        return self.roomData.title

    @property
    def hidden(self):
        return self.deviceData.hiddenFromRoomList

    @property
    def hardware(self):
        if self.plejdDevice.firmware.notes:
            return self.plejdDevice.firmware.notes.split()[0]
        return f"-UNKNOWN- ({self.plejdDevice.hardwareId})"

    @property
    def firmware(self):
        return self.plejdDevice.firmware.version


class PlejdOutput(PlejdDevice):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.settings: sd.PlejdDeviceOutputSetting
        self.identifier = (self.plejdDevice.deviceId, "O", str(self.settings.output))


class PlejdInput(PlejdDevice):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.settings: sd.PlejdDeviceInputSetting
        self.identifier = (self.plejdDevice.deviceId, "I", str(self.settings.input))

    def match_state(self, state):
        if "button" in state:
            if (
                state.get("address") == self.deviceAddress
                and state.get("button") == self.settings.input
            ):
                return True
            return False
        return super().match_state(state)
