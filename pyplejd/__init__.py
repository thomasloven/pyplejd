import logging
from datetime import timedelta

from bleak_retry_connector import close_stale_connections

from .ble import PlejdMesh
from .cloud import PlejdCloudSite

from .const import PLEJD_SERVICE, LIGHT, SENSOR, SWITCH, UNKNOWN

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "PlejdManager",
    "get_sites",
    "PLEJD_SERVICE",
    "LIGHT",
    "SENSOR",
    "SWITCH",
    "UNKNOWN",
]

get_sites = PlejdCloudSite.get_sites


class PlejdManager:
    def __init__(self, credentials):
        self.credentials = credentials
        self.mesh = PlejdMesh()
        self.devices = []
        self.scenes = []
        self.cloud = PlejdCloudSite(**credentials)

    async def init(self):
        await self.cloud.ensure_details_loaded()

        self.mesh.set_key(self.cloud.cryptokey)
        self.mesh.subscribe_state(self._update_device)

        self.devices = self.cloud.devices
        for d in self.devices:
            self.mesh.expect_device(d.BLEaddress)
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
        _LOGGER.debug("Saw plejd device %s", device)
        return self.mesh.see_device(device, rssi)

    async def close_stale(self, device):
        _LOGGER.debug("Closing stale connections for %s", device)
        await close_stale_connections(device)

    @property
    def connected(self):
        return self.mesh is not None and self.mesh.connected

    @property
    def site_data(self):
        return self.cloud.details

    def _update_device(self, deviceState):
        _LOGGER.debug("New data: %s", deviceState)

        for d in self.devices:
            if d.address == deviceState["address"]:
                d.update_state(**deviceState)

    @property
    def ping_interval(self):
        return timedelta(minutes=10)

    async def ping(self):
        retval = await self.mesh.ping()
        return retval

    async def disconnect(self):
        _LOGGER.debug("DISCONNECT")
        await self.mesh.disconnect()
