from pydantic import BaseModel, PrivateAttr
from typing import Literal, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from .ble.mesh import PlejdMesh

_LOGGER = logging.getLogger(__name__)


class PlejdSiteSummary(BaseModel):
    title: str
    deviceCount: int
    siteId: str


class PlejdDevice(BaseModel):
    objectId: str
    address: int
    BLEaddress: str

    name: str
    hardware: str
    dimmable: bool | None
    outputType: Literal["LIGHT", "SENSOR", "RELAY", "UNKNOWN"] | None
    room: str
    firmware: str
    inputAddress: list[int]

    _state: bool = PrivateAttr()
    _dim: int = PrivateAttr()
    _available: bool = PrivateAttr()
    _listeners: set = PrivateAttr()
    _mesh: "PlejdMesh" = PrivateAttr()

    def __init__(self, **data):
        super().__init__(**data)
        self._state = None
        self._dim = None
        self._available = None
        self._listeners = set()
        self._mesh = None

    def connect_mesh(self, mesh: "PlejdMesh"):
        self._mesh = mesh

    def subscribe_state(self, listener):
        self._listeners.add(listener)

        def remover():
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remover

    async def update_state(self, state=None, dim=None, available=True, **_):
        update = False
        if state is not None and state != self._state:
            self._state = state
            update = True
        if dim is not None and dim != self._dim:
            self._dim = dim
            update = True
        if available is not None and available != self._available:
            self._available = available
            update = True

        if update:
            for listener in self._listeners:
                listener(
                    {
                        "state": self._state if self._available else False,
                        "dim": self._dim / 256 if self._dim else 0,
                        "available": self._available,
                    }
                )

    async def turn_on(self, dim=0):
        await self._mesh.set_state(self.address, True, dim)

    async def turn_off(self):
        await self._mesh.set_state(self.address, False)


class PlejdScene(BaseModel):
    sceneId: str
    index: int
    title: str

    _mesh: "PlejdMesh" = PrivateAttr()

    def __init__(self, **data):
        super().__init__(**data)
        self._mesh = None

    def connect_mesh(self, mesh: "PlejdMesh"):
        self._mesh = mesh

    async def activate(self):
        await self._mesh.activate_scene(self.index)
