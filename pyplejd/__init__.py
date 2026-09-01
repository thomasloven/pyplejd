from __future__ import annotations
import logging
import asyncio
from datetime import datetime, timedelta

from bleak_retry_connector import close_stale_connections

from .ble import PlejdMesh, PLEJD_SERVICE, LastData, LightLevel
from .ble.debug import rec_log
from .cloud import PlejdCloudSite

from .errors import AuthenticationError, ConnectionError
from .interface import (
    outputDeviceClass,
    inputDeviceClass,
    sceneDeviceClass,
    DeviceTypes,
)

__all__ = [
    "PlejdManager",
    "get_sites",
    "verify_credentials",
    "DeviceTypes",
    "AuthenticationError",
    "ConnectionError",
    "PLEJD_SERVICE",
]

dt = DeviceTypes


get_sites = PlejdCloudSite.get_sites
verify_credentials = PlejdCloudSite.verify_credentials


class PlejdManager:
    def __init__(self, username: str, password: str, siteId: str):
        self.credentials = {
            "username": username,
            "password": password,
            "siteId": siteId,
        }

        self.mesh = PlejdMesh(self)
        self.devices: list[dt.PlejdDevice | dt.PlejdScene] = []
        self.hardware: dict[str, dt.PlejdHardware] = {}
        self._blacklist = set()  # TODO: MAKE WORK
        self.cloud = PlejdCloudSite(**self.credentials)
        self.options = {}
        self.connection_monitor = None
        self._diagnostics_polled = None

    @property
    def blacklist(self):
        return self._blacklist

    @blacklist.setter
    def blacklist(self, blacklist):
        self._blacklist = set(a.replace(":", "").upper() for a in blacklist)

    def _get_hw(self, addr: str, device: dt.PlejdDevice) -> dt.PlejdHardware:
        addr = addr.replace(":", "").upper()
        if addr not in self.hardware:
            self.hardware[addr] = dt.PlejdHardware(
                addr,
                device.powered,
                blacklisted=addr in self.blacklist,
            )
        return self.hardware[addr]

    def connect_callback(self, connected: bool):
        for d in self.devices:
            d.set_available(connected)
        if self.connection_monitor:
            self.connection_monitor(connected)

    async def lightlevel_callback(self, lightlevels: list[LightLevel]):
        for ll in lightlevels:
            for d in self.devices:
                if ll.address == d.address:
                    await d.parse_lightlevel(ll)

    async def lastdata_callback(self, data: LastData):
        found = False
        for d in self.devices:
            if data.address in [d.address, d.rxAddress, 0]:
                found = True
                await d.parse_lastdata(data)

        if not found:
            rec_log(f"Unknown command received: {data.command}")
            rec_log(f"    {data.hex}")

    async def init(self, sitedata=None):
        await self.cloud.load_site_details(sitedata)

        self.mesh.set_key(self.cloud.cryptokey)

        LOGGER = logging.getLogger("pyplejd.device_list")

        LOGGER.debug("Output Devices:")
        for device in self.cloud.outputs:
            cls = outputDeviceClass(device)
            dev = cls(**device, mesh=self.mesh)
            LOGGER.debug(dev)
            self.devices.append(dev)

            hw = self._get_hw(dev.BLEaddress, dev)
            hw.devices.add(dev)
            dev.hw = hw

            self.mesh.expect_device(hw)

        LOGGER.debug("Input Devices:")
        for device in self.cloud.inputs:
            cls = inputDeviceClass(device)
            dev = cls(**device, mesh=self.mesh)
            LOGGER.debug(dev)
            self.devices.append(dev)

            hw = self._get_hw(dev.BLEaddress, dev)
            hw.devices.add(dev)
            dev.hw = hw

            self.mesh.expect_device(hw)

        LOGGER.debug("Scenes:")
        for scene in self.cloud.scenes:
            cls = sceneDeviceClass(scene)
            scn = cls(**scene, mesh=self.mesh)
            LOGGER.debug(scn)
            self.devices.append(scn)

    def add_mesh_device(self, device, rssi) -> bool:
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

    @property
    def ping_interval(self):
        return timedelta(minutes=3)

    @property
    def diagnostics_interval(self):
        """How often to read per-device diagnostics.

        Deliberately infrequent. Every read puts a request and a response on the
        air, and mesh airtime is the scarce resource here - a unit busy talking
        is a unit not relaying for its neighbours.
        """
        return timedelta(minutes=15)

    async def ping(self, retry=True):
        retval = await self.mesh.ping()
        if not retval and retry:
            await asyncio.sleep(30)
            retval = await self.mesh.ping()
        if retval:
            await self._maybe_poll_diagnostics()
        return retval

    async def _maybe_poll_diagnostics(self):
        """Poll diagnostics if diagnostics_interval has elapsed.

        Driven off ping so the data appears without the integration having to
        schedule anything, while staying on its own slower clock.
        """
        now = datetime.now()
        if (
            self._diagnostics_polled is not None
            and now - self._diagnostics_polled < self.diagnostics_interval
        ):
            return
        self._diagnostics_polled = now
        await self.poll_diagnostics()

    async def poll_diagnostics(self):
        """Read temperature and fault state from every mains powered device.

        Battery powered units are asleep and will not answer; they are skipped
        rather than waited for. A device that does not answer keeps its previous
        values so a single missed read does not blank the sensors.
        """
        if not self.mesh.connected:
            return

        LOGGER = logging.getLogger("pyplejd.diagnostics")
        for hw in self.hardware.values():
            # Mains powered, not connectable: a unit excluded from gateway
            # selection still answers reads perfectly well.
            if not hw.powered:
                continue
            address = next(
                (d.deviceAddress for d in hw.devices if d.deviceAddress is not None),
                None,
            )
            if address is None:
                continue

            updated = False
            for command, attribute in (
                (LastData.CMD_INTERNAL_TEMPERATURE, "internal_temperature"),
                (LastData.CMD_EXTERNAL_TEMPERATURE, "external_temperature"),
            ):
                response = await self.mesh.request(address, command)
                if response is None or len(response) < 2:
                    continue
                setattr(hw, attribute, int.from_bytes(response[:2], "little"))
                updated = True

            response = await self.mesh.request(address, LastData.CMD_HARDFAULT_REASON)
            if response is not None:
                # An empty payload means the device has nothing to report.
                hw.hardfault = any(response)
                updated = True

            if updated:
                hw.diagnostics_updated = datetime.now()
                hw.update()
                LOGGER.debug(
                    "Diagnostics for %s: internal=%s external=%s hardfault=%s",
                    hw.BLEaddress,
                    hw.internal_temperature,
                    hw.external_temperature,
                    hw.hardfault,
                )

    async def broadcast_time(self):
        for d in self.devices:
            if d.powered:
                if await self.mesh.poll_time(d.address):
                    await self.mesh.broadcast_time()
                    return

    async def disconnect(self):
        await self.mesh.disconnect()

    async def set_blacklist(self, blacklist):
        self.blacklist = blacklist
        reconnect = False
        for hw in self.hardware.values():
            hw.blacklisted = hw.BLEaddress in self.blacklist
            if hw.blacklisted and hw.is_gateway:
                reconnect = True
        if reconnect:
            await self.mesh.disconnect()
        await self.ping()
