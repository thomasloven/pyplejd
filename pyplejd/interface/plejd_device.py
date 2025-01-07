from __future__ import annotations
from enum import IntFlag, StrEnum
from ..cloud import site_details as sd

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..ble import PlejdMesh


class PlejdTraits(IntFlag):
    POWER = 0x8
    TEMP = 0x4
    DIM = 0x2
    GROUP = 0x1

    COVER = 0x10
    TILT = 0x40


class PlejdDeviceType(StrEnum):
    LIGHT = "LIGHT"
    SWITCH = "RELAY"
    BUTTON = "SENSOR"
    MOTION = "MOTION"
    COVER = "COVERABLE"
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
        *_,
        **__,
    ):
        self.address = address
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
        self.device_identifier = (plejdDevice.deviceId, device.objectId)
        self.capabilities = PlejdTraits(self.deviceData.traits)

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.BLEaddress} ({self.address}) {self.name} [{self.hardware}] {self.outputType}-{self.capabilities!r}>"

    def match_state(self, state):
        if state.get("address") == self.address:
            return True
        return False

    def subscribe(self, listener):
        self._listeners.add(listener)

        def remover():
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remover

    def parse_state(self, update, state):
        return state

    def update_state(self, **state):
        self._state.update(state)
        state = self.parse_state(state, self._state)
        for listener in self._listeners:
            listener(state)

    @property
    def BLEaddress(self):
        return self.deviceData.deviceId

    @property
    def powered(self):
        return PlejdTraits.POWER in self.capabilities

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
