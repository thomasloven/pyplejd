from __future__ import annotations

try:
    from pydantic.v1 import BaseModel, PrivateAttr
except ImportError:
    from pydantic import BaseModel, PrivateAttr
from typing import Literal, TYPE_CHECKING, Callable, TypedDict

if TYPE_CHECKING:
    from .ble import PlejdMesh

class PlejdCloudCredentials(TypedDict):
    username: str
    password: str
    siteId: str

class PlejdSiteSummary(BaseModel):
    title: str
    deviceCount: int
    siteId: str


class PlejdDevice(BaseModel):
    objectId: str
    address: int
    rxaddress: int | None
    BLEaddress: str

    name: str
    hardware: str
    dimmable: bool | None
    colortemp: list | bool
    outputType: Literal["LIGHT", "SENSOR", "RELAY", "MOTION", "UNKNOWN"] | None
    room: str
    firmware: str
    inputAddress: list[int]
    hidden: bool

    _state: bool = PrivateAttr()
    _dim: int = PrivateAttr()
    _colortemp: int = PrivateAttr()
    _available: bool = PrivateAttr()
    _state_listeners: set = PrivateAttr()
    _event_listeners: set = PrivateAttr()
    _mesh: "PlejdMesh" = PrivateAttr()

    def __init__(self, **data):
        super().__init__(**data)
        self._state = None
        self._dim = None
        self._colortemp = None
        self._available = None
        self._state_listeners = set()
        self._event_listeners = set()
        self._mesh = None

    def connect_mesh(self, mesh: PlejdMesh):
        self._mesh = mesh

    def _subscribe(self, set_: set, listener: Callable):
        set_.add(listener)

        def remover():
            if listener in set_:
                set_.remove(listener)

        return remover

    def subscribe_state(self, listener):
        return self._subscribe(self._state_listeners, listener)

    def subscribe_event(self, listener):
        return self._subscribe(self._event_listeners, listener)

    def update_state(self, state=None, dim=None, available=True, colortemp=None, **_):
        update = False
        if state is not None and state != self._state:
            self._state = state
            update = True
        if dim is not None and dim != self._dim:
            self._dim = dim
            update = True
        if colortemp is not None and colortemp != self._colortemp:
            self._colortemp = colortemp
            update = True
        if available is not None and available != self._available:
            self._available = available
            update = True

        if update:
            for listener in self._state_listeners:
                listener(
                    {
                        "state": self._state if self._available else False,
                        "dim": self._dim / 256 if self._dim else 0,
                        "colortemp": self._colortemp,
                        "available": self._available,
                    }
                )

    def trigger_event(self, event):
        for listener in self._event_listeners:
            listener(event)

    async def turn_on(self, dim=0, colortemp=None):
        if dim is not None:
            dim = dim << 8 | dim
        if colortemp is not None:
            colortemp = int(1e6/colortemp)
        await self._mesh.set_state(self.address, True, dim, colortemp)

    async def turn_off(self):
        await self._mesh.set_state(self.address, False)


class PlejdScene(BaseModel):
    sceneId: str
    index: int
    title: str
    hidden: bool

    _mesh: "PlejdMesh" = PrivateAttr()
    _listeners: set = PrivateAttr()

    def __init__(self, **data):
        super().__init__(**data)
        self._mesh = None
        self._listeners = set()

    def connect_mesh(self, mesh: PlejdMesh):
        self._mesh = mesh

    def subscribe_activate(self, listener):
        self._listeners.add(listener)

        def remover():
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remover

    def activated(self):
        for listener in self._listeners:
            listener()

    async def activate(self):
        await self._mesh.activate_scene(self.index)
