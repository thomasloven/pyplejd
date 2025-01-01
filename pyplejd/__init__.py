from __future__ import annotations
import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from bleak_retry_connector import close_stale_connections

from .ble import PlejdMesh
from .cloud import PlejdCloudSite

from .const import PLEJD_SERVICE, LIGHT, SENSOR, MOTION, SWITCH, COVERABLE, UNKNOWN
from .errors import AuthenticationError, ConnectionError
from .interface import (
    PlejdCloudCredentials,
    outputDeviceClass,
    inputDeviceClass,
    PlejdDevice,
    PlejdScene,
)


_LOGGER = logging.getLogger(__name__)


get_sites = PlejdCloudSite.get_sites
verify_credentials = PlejdCloudSite.verify_credentials


class PlejdManager:
    def __init__(self, credentials: PlejdCloudCredentials):
        self.credentials: PlejdCloudCredentials = credentials
        self.mesh = PlejdMesh(self)
        self.devices: list[PlejdDevice | PlejdScene] = []
        self.cloud = PlejdCloudSite(**credentials)
        self.options = {}

    async def init(self, sitedata=None):
        await self.cloud.load_site_details(sitedata)

        self.mesh.set_key(self.cloud.cryptokey)

        self.mesh.subscribe_connect(self._update_connected)
        self.mesh.subscribe_state(self._update_device)

        _LOGGER.debug("Output Devices:")
        for device in self.cloud.outputs:
            cls = outputDeviceClass(device)
            dev = cls(**device, mesh=self.mesh)
            _LOGGER.debug(dev)
            self.devices.append(dev)
            self.mesh.expect_device(dev.BLEaddress, dev.connectable)

        _LOGGER.debug("Input Devices:")
        for device in self.cloud.inputs:
            cls = inputDeviceClass(device)
            dev = cls(**device, mesh=self.mesh)
            _LOGGER.debug(dev)
            self.devices.append(dev)
            self.mesh.expect_device(dev.BLEaddress, dev.connectable)

        _LOGGER.debug("Scenes:")
        for scene in self.cloud.scenes:
            scn = PlejdScene(**scene, mesh=self.mesh)
            _LOGGER.debug(scn)
            self.devices.append(scn)

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
            if d.match_state(state):
                d.update_state(**state)

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
