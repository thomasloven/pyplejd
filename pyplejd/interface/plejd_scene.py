from __future__ import annotations
from ..cloud import site_details as sd
from .plejd_device import PlejdDeviceType
from ..ble import LastData
from ..ble.debug import rec_log

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..ble import PlejdMesh

import logging

_LOGGER = logging.getLogger(__name__)


class PlejdScene:
    def __init__(
        self,
        scene: sd.Scene,
        index: int,
        mesh: PlejdMesh,
    ):
        self.scene = scene
        self.index = index

        self._mesh = mesh
        self._state = {}

        self._listeners = set()

        self.outputType = PlejdDeviceType.SCENE
        self.identifier = self.scene.sceneId
        self.address = 2
        self.rxAddress = -1
        self.hw = None
        self.is_primary = False

    def __repr__(self):
        return f"<{self.__class__.__name__} ({self.index}) {self.name}>"

    def subscribe(self, listener):
        self._listeners.add(listener)

        def remover():
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remover

    async def activate(self):
        await self._mesh.write(
            LastData(command=LastData.CMD_SCENE, payload=[self.index]).hex
        )

    async def parse_lastdata(self, data: LastData):
        match data.command:
            case LastData.CMD_SCENE:
                scene = int(data.payload[0])
                if not scene == self.index:
                    return
                for listener in self._listeners:
                    listener(
                        {
                            **self._state,
                            "triggered": True,
                        }
                    )

        pass

    def set_available(self, available=False):
        self._state["available"] = available
        for listener in self._listeners:
            listener(self._state)

    @property
    def BLEaddress(self):
        return None

    @property
    def name(self):
        return self.scene.title

    @property
    def hidden(self):
        return self.scene.hiddenFromSceneList

    @property
    def powered(self):
        return False
