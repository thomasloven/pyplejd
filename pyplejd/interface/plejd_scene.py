from __future__ import annotations
from ..cloud import site_details as sd
from .plejd_device import PlejdDeviceType

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

    def __repr__(self):
        return f"<{self.__class__.__name__} ({self.index}) {self.name}>"

    def match_state(self, state):
        if state.get("scene") == self.index:
            return True
        return False

    def subscribe(self, listener):
        self._listeners.add(listener)

        def remover():
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remover

    def update_state(self, **state):
        self._state.update(state)
        state = self._state
        for listener in self._listeners:
            listener(state)
        self._state["triggered"] = False

    async def activate(self):
        await self._mesh.activate_scene(self.index)

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
