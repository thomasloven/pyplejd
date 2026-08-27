import asyncio
import binascii
import logging
import os
from datetime import datetime, timedelta
from typing import Callable
import time

from bleak import BleakClient, BleakError
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection, BleakClientWithServiceCache

from .crypto import auth_response, encrypt_decrypt
from . import ble_characteristics as gatt
from . import payload_encode
from .lastdata import LastData, MiniPkg
from .lightlevel import parse_lightlevels, LightLevel
from .ble_characteristics import PLEJD_SERVICE
from .debug import rec_log

_LOGGER = logging.getLogger(__name__)
_CONNECTION_LOG = logging.getLogger("pyplejd.ble.connection")

# Connection parameters requested once the mesh connection is up.
#
# A Plejd unit is not only a GATT peripheral: the same radio also carries the
# Plejd mesh, relaying and re-announcing traffic for every other unit. Home
# Assistant's Bluetooth stack asks BlueZ for an aggressive 8.75-11.25 ms
# connection interval, which leaves the unit too little radio time for that
# second duty. Measured on a two-unit mesh with a local adapter, the effects
# began abruptly below 15 ms and were severe at 11.25 ms:
#
#   interval    behaviour
#   11.25 ms    unit emits a 1.6 s on/off state pulse train, relays almost
#               nothing from its peers, and switches its own output unbidden
#   12.50 ms    same, less frequent
#   15.00 ms    clean
#   20.00 ms    clean
#   45.00 ms    clean
#
# 30-50 ms is chosen rather than the measured 15 ms boundary because that
# boundary was found on the smallest possible mesh. A larger installation has
# more traffic to relay and therefore needs more radio time, not less, so the
# margin protects meshes bigger than the one it was measured on. For lighting,
# the added latency of a few tens of milliseconds is imperceptible.
CONN_MIN_INTERVAL = 0x18  # 24 * 1.25 ms = 30 ms
CONN_MAX_INTERVAL = 0x28  # 40 * 1.25 ms = 50 ms
CONN_LATENCY = 0
CONN_TIMEOUT = 800  # 800 * 10 ms = 8 s


class MeshDevice:
    BLEaddress: str
    connectable: bool
    last_seen: datetime = None
    rssi: int = None
    bleDevice: BLEDevice = None
    is_gateway: bool = False

    def see(self, rssi, bleDevice: BLEDevice) -> bool:
        # Returns true if first seen
        if first_seen := (self.rssi is None):
            self.bleDevice = bleDevice
            self.rssi = rssi

        self.last_seen = datetime.now()
        self.rssi = max(self.rssi, rssi)

        return first_seen

    def update():
        pass


def normalize_address(addr: str) -> str:
    return addr.replace(":", "").upper()


class PlejdMesh:
    def __init__(self, manager):
        self.manager = manager
        self._mesh_devices: dict[str, MeshDevice] = {}
        self._gateway_node: MeshDevice | None = None
        self._crypto_key: bytearray = None
        self._client: BleakClient = None

        self._ble_lock = asyncio.Lock()

    @property
    def connected(self):
        return self._client is not None

    def expect_device(self, node: MeshDevice = None):
        self._mesh_devices[node.BLEaddress] = node

    def see_device(self, node: BLEDevice, rssi: int) -> bool:
        _CONNECTION_LOG.debug(f"Saw device {node} (rssi: {rssi})")
        addr = normalize_address(node.address)
        if hw := self._mesh_devices.get(addr):
            return hw.see(rssi, node)
        return False

    def set_key(self, key: str):
        self._crypto_key = key

    async def disconnect(self):
        if not self.connected:
            return False

        try:
            await self._client.stop_notify(gatt.PLEJD_LASTDATA)
            await self._client.stop_notify(gatt.PLEJD_LIGHTLEVEL)
            await self._client.disconnect()
        except BleakError:
            pass

        self._client = None
        self.manager.connect_callback(False)

    async def connect(self):
        if self.connected:
            return True
        _CONNECTION_LOG.debug("Trying to connect to BLE mesh")

        def _disconnect(client: BleakClient):
            _CONNECTION_LOG.debug("Disconected from BLE mesh (%s)", client)
            self._client = None
            if self._gateway_node:
                self._gateway_node.is_gateway = False
                self._gateway_node.update()
                self._gateway_node = None
            self.manager.connect_callback(False)

        # Try to connect to nodes in order of decreasing RSSI
        filtered_nodes = filter(
            lambda n: n.connectable and n.rssi is not None,
            self._mesh_devices.values(),
        )
        sorted_nodes = sorted(filtered_nodes, key=lambda n: n.rssi, reverse=True)

        if not sorted_nodes:
            return False
        client = None
        for node in sorted_nodes:
            try:
                _CONNECTION_LOG.debug("Attempting to connect to %s", node)
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    node.bleDevice,
                    node.bleDevice.name,
                    max_attempts=2,
                )

                # Workaround for problem in plejd firmware 2026-05-20
                # Disconnect and connect again
                _CONNECTION_LOG.debug(
                    "BT Proxy workaround - Disconnecting for 5 seconds."
                )
                await client.disconnect()
                await asyncio.sleep(5)
                _CONNECTION_LOG.debug("BT Proxy workaround - Reconnecting")
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    node.bleDevice,
                    node.bleDevice.name,
                    _disconnect,
                )

                if not await self._authenticate(client):
                    await client.disconnect()
                    continue
                await self._relax_connection_params(client)
                self._gateway_node = node
                node.is_gateway = True
                self._gateway_node.update()
                break

            except (BleakError, asyncio.TimeoutError) as e:
                _CONNECTION_LOG.warning("Failed to connect to %s: %s", node, str(e))

        else:
            _CONNECTION_LOG.warning(
                "Failed to connect to plejd mesh - %s", sorted_nodes
            )
            return False

        async def _lastdata_listener(_arg, lastdata: bytearray):
            if not self.connected:
                return

            data = encrypt_decrypt(
                self._crypto_key, self._gateway_node.BLEaddress, lastdata
            )

            ld = LastData(data)
            rec_log(f"lastdata {ld}")
            await self.manager.lastdata_callback(ld)

            if ld.command == LastData.CMD_EVENT_FIRED:
                await self.poll_buttons()
            return True

        async def _lightlevel_listener(_, lightlevel: bytearray):
            if not self.connected:
                return

            rec_log(f"lightlevel {lightlevel}")
            await self.manager.lightlevel_callback(parse_lightlevels(lightlevel))

        await client.start_notify(gatt.PLEJD_LASTDATA, _lastdata_listener)
        await client.start_notify(gatt.PLEJD_LIGHTLEVEL, _lightlevel_listener)
        self._client = client

        self.manager.connect_callback(True)

        await self.poll()
        return True

    async def poll(self):
        if not self.connected:
            return

        _LOGGER.debug("Polling mesh for current state")
        await self._client.write_gatt_char(
            gatt.PLEJD_LIGHTLEVEL, b"\x01", response=True
        )

    async def poll_buttons(self):
        await self.write(LastData(command=LastData.CMD_EVENT_PREPARE).hex)

    async def ping(self):
        async with self._ble_lock:
            if not await self.connect():
                return False
            if not await self._ping(self._client):
                return False

        await self.poll()
        await self.poll_buttons()
        return True

    async def poll_time(self, address: int):
        if not self.connected:
            return

        payloads = payload_encode.request_time(self, address)
        await self.write(payloads)

        retval = await self._client.read_gatt_char(gatt.PLEJD_LASTDATA)
        data = encrypt_decrypt(self._crypto_key, self._gateway_node.BLEaddress, retval)
        ts = int.from_bytes(data[5:9], "little")
        dt = datetime.fromtimestamp(ts)

        now = datetime.now() + timedelta(seconds=3600 * time.daylight)
        if abs(dt - now) > timedelta(seconds=60):
            _LOGGER.debug(f"Device {address} repported the wrong time {dt} ({now=})")
            return True
        return False

    async def broadcast_time(self):
        payloads = payload_encode.set_time(self)
        await self.write(payloads)

    async def write(self, *payloads: list[str]):
        if not self.connected:
            return

        pl = [
            encrypt_decrypt(
                self._crypto_key,
                self._gateway_node.BLEaddress,
                binascii.a2b_hex(payload.replace(" ", "")),
            )
            for payload in payloads
        ]
        _LOGGER.debug(f"Write: {payloads}")
        await self._write(pl)

    async def _write(self, payloads):
        if not self.connected:
            return

        try:
            async with self._ble_lock:
                for payload in payloads:
                    _LOGGER.debug("Writing to plejd mesh: %s", payload.hex())
                    await self._client.write_gatt_char(
                        gatt.PLEJD_DATA, payload, response=True
                    )
        except (BleakError, asyncio.TimeoutError) as e:
            _LOGGER.warning("Writing to plejd mesh failed: %s", str(e))
            return False
        return True

    async def _ping(self, client):
        if client is None:
            return False
        try:
            ping = bytearray(os.urandom(1))
            _LOGGER.debug("Ping(%s)", int.from_bytes(ping, "little"))
            await client.write_gatt_char(gatt.PLEJD_PING, ping, response=True)
            pong = await client.read_gatt_char(gatt.PLEJD_PING)
            _LOGGER.debug("Pong(%s)", int.from_bytes(pong, "little"))
            if (ping[0] + 1) & 0xFF == pong[0]:
                return True
        except (BleakError, asyncio.TimeoutError) as e:
            _LOGGER.warning("Plejd mesh keepalive signal failed: %s", str(e))
        return False

    async def _relax_connection_params(self, client: BleakClient) -> None:
        """Ask the host stack for a gentler connection interval.

        See CONN_MIN_INTERVAL above for why this is wanted.

        Best effort by design. The call is habluetooth's
        HaBleakClientWrapper.set_connection_params(), which is present when
        running under Home Assistant and handles both the local BlueZ mgmt
        path and ESPHome proxies. Plain bleak offers no portable equivalent,
        so a missing method - or a call that fails - is not an error.
        """
        set_params = getattr(client, "set_connection_params", None)
        if set_params is None:
            return
        try:
            await set_params(
                CONN_MIN_INTERVAL, CONN_MAX_INTERVAL, CONN_LATENCY, CONN_TIMEOUT
            )
        except Exception:  # a failed optimisation must not fail the connection
            _CONNECTION_LOG.debug("Could not set connection parameters", exc_info=True)
        else:
            _CONNECTION_LOG.debug(
                "Requested connection interval %.2f-%.2f ms",
                CONN_MIN_INTERVAL * 1.25,
                CONN_MAX_INTERVAL * 1.25,
            )

    async def _authenticate(self, client: BleakClient):
        if client is None:
            return False
        try:
            _CONNECTION_LOG.debug("Authenticating with plejd mesh")
            await client.write_gatt_char(gatt.PLEJD_AUTH, b"\x00", response=True)
            _CONNECTION_LOG.debug("Requested auth")
            challenge = await client.read_gatt_char(gatt.PLEJD_AUTH)
            _CONNECTION_LOG.debug("Got challenge")
            response = auth_response(self._crypto_key, challenge)
            await client.write_gatt_char(gatt.PLEJD_AUTH, response, response=True)
            _CONNECTION_LOG.debug("Wrote response")
            if not await self._ping(client):
                _CONNECTION_LOG.debug("Authentication failed!")
                return False
            _CONNECTION_LOG.debug("Authentication successful")
            return True
        except (BleakError, asyncio.TimeoutError) as e:
            _CONNECTION_LOG.warning("Plejd mesh authentication failed: %s", str(e))
        return False
