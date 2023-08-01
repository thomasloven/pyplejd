import logging
from datetime import timedelta

from bleak_retry_connector import close_stale_connections

from .ble.mesh import PlejdMesh
from .cloud import PlejdCloudSite

# from .plejd_device import PlejdDevice, PlejdScene

from .const import PLEJD_SERVICE, LIGHT, SWITCH

_LOGGER = logging.getLogger(__name__)

get_sites = PlejdCloudSite.get_sites


class PlejdManager:
    def __init__(self, credentials):
        self.credentials = credentials
        self.mesh = PlejdMesh()
        self.mesh.statecallback = self._update_device
        self.devices = []
        self.scenes = []
        self.cloud = PlejdCloudSite(**credentials)

    async def init(self):
        await self.cloud.ensure_details_loaded()

        self.devices = self.cloud.devices
        for d in self.devices:
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
        _LOGGER.debug("Adding plejd %s", device)
        # for d in self.devices.values():
        #     addr = device.address.replace(":","").replace("-","").upper()
        #     if d.BLE_address.upper() == addr or addr in device.name:
        return self.mesh.add_mesh_node(device, rssi)
        # _LOGGER.debug("Device was not expected in current mesh")

    async def close_stale(self, device):
        _LOGGER.debug("Closing stale connections for %s", device)
        await close_stale_connections(device)

    @property
    def connected(self):
        return self.mesh is not None and self.mesh.connected

    async def get_site_data(self):
        await self.cloud.ensure_details_loaded()
        return self.cloud.details

    async def _update_device(self, deviceState):
        _LOGGER.debug("New data:")
        _LOGGER.debug(deviceState)

        for d in self.devices:
            if d.address == deviceState["address"]:
                await d.update_state(**deviceState)

    @property
    def keepalive_interval(self):
        return timedelta(minutes=10)

    async def keepalive(self):
        await self.cloud.ensure_details_loaded()
        if self.mesh.crypto_key is None:
            self.mesh.set_crypto_key(self.cloud.cryptokey)
        if not self.mesh.connected:
            if not await self.mesh.connect():
                return False
        retval = await self.mesh.ping()
        if retval and self.mesh.pollonWrite:
            await self.mesh.poll()
        return retval

    async def disconnect(self):
        _LOGGER.debug("DISCONNECT")
        await self.mesh.disconnect()

    async def poll(self):
        await self.mesh.poll()

    async def ping(self):
        retval = await self.mesh.ping()
        if self.mesh.pollonWrite:
            await self.poll()
        return retval
