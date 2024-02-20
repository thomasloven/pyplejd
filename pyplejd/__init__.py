from __future__ import annotations
import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from bleak_retry_connector import close_stale_connections

from .ble import PlejdMesh
from .cloud import PlejdCloudSite

from .const import PLEJD_SERVICE, LIGHT, SENSOR, MOTION, SWITCH, UNKNOWN
from .errors import AuthenticationError, ConnectionError
from .interface import PlejdCloudCredentials

if TYPE_CHECKING:
    from .interface import PlejdDevice, PlejdScene

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "PlejdManager",
    "get_sites",
    "verify_credentials"
    "PLEJD_SERVICE",
    "LIGHT",
    "SENSOR",
    "MOTION",
    "SWITCH",
    "UNKNOWN",
    "AuthenticationError",
    "ConnectionError",
    "PlejdCloudCredentials"
]

get_sites = PlejdCloudSite.get_sites
verify_credentials = PlejdCloudSite.verify_credentials


class PlejdManager:
    def __init__(self, credentials: PlejdCloudCredentials):
        self.credentials: PlejdCloudCredentials = credentials
        self.mesh = PlejdMesh()
        self.devices: list[PlejdDevice] = []
        self.scenes: list[PlejdScene] = []
        self.cloud = PlejdCloudSite(**credentials)

    async def init(self, sitedata=None):
        await self.cloud.load_site_details(sitedata)

        self.mesh.set_key(self.cloud.cryptokey)
        self.mesh.subscribe_connect(self._update_connected)
        self.mesh.subscribe_state(self._update_device)
        self.mesh.subscribe_scene(self._update_scene)
        self.mesh.subscribe_button(self._update_button)

        self.devices = self.cloud.devices
        for d in self.devices:
            self.mesh.expect_device(d.BLEaddress, d.outputType in [LIGHT, SWITCH])
            d.connect_mesh(self.mesh)

        self.scenes = self.cloud.scenes
        for s in self.scenes:
            s.connect_mesh(self.mesh)

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("Devices:")
            for d in self.devices:
                _LOGGER.debug(d)
            _LOGGER.debug("Scenes:")
            for s in self.scenes:
                _LOGGER.debug(s)

    def add_mesh_device(self, device, rssi):
        return self.mesh.see_device(device, rssi)

    async def close_stale(self, device):
        await close_stale_connections(device)

    @property
    def connected(self):
        return self.mesh is not None and self.mesh.connected

    @property
    def site_data(self):
        return self.cloud.details

    async def get_raw_sitedata(self):
        return await self.cloud.get_raw_details()

    def _update_connected(self, state):
        for d in self.devices:
            d.update_state(available=state["connected"])

    def _update_device(self, state):
        for d in self.devices:
            if d.address == state["address"] or d.rxaddress == state["address"]:
                d.update_state(**state)

    def _update_scene(self, state):
        for s in self.scenes:
            if s.index == state["scene"]:
                s.activated()

    def _update_button(self, state):
        for d in self.devices:
            if d.address == state["address"]:
                d.trigger_event(state)

    @property
    def ping_interval(self):
        return timedelta(minutes=10)

    async def ping(self):
        retval = await self.mesh.ping()
        return retval

    async def broadcast_time(self):
        for d in self.devices:
            if d.outputType in [LIGHT, SWITCH]:
                if await self.mesh.poll_time(d.address):
                    await self.mesh.broadcast_time()
                    return

    async def disconnect(self):
        await self.mesh.disconnect()
