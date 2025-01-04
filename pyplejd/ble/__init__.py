import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Callable
import time

from bleak import BleakClient, BleakError
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from .crypto import auth_response, encrypt_decrypt
from . import ble_characteristics as gatt
from . import payload_encode
from .parse_data import parse_data
from .parse_lightlevel import parse_lightlevel
from .ble_characteristics import PLEJD_SERVICE

_LOGGER = logging.getLogger(__name__)
_CONNECTION_LOG = logging.getLogger("pyplejd.ble.connection")


class PlejdMesh:
    def __init__(self, manager):
        self.manager = manager
        self._seen_nodes: dict[BLEDevice, int] = {}
        self._expected_nodes = set()
        self._connectable_nodes = set()
        self._gateway_node = None
        self._crypto_key: bytearray = None
        self._client: BleakClient = None

        self._connect_listeners = set()
        self._state_listeners = set()

        self._ble_lock = asyncio.Lock()

    @property
    def connected(self):
        return self._client is not None

    def expect_device(self, BLEaddress: str, connectable=True):
        self._expected_nodes.add(BLEaddress.replace(":", "").upper())
        if connectable:
            self._connectable_nodes.add(BLEaddress.replace(":", "").upper())

    def see_device(self, node: BLEDevice, rssi: int) -> bool:
        _CONNECTION_LOG.debug(
            f"Saw device {node} (rssi: {rssi}, prev: {self._seen_nodes.get(node, -1e6)})"
        )
        new_device = node not in self._seen_nodes
        self._seen_nodes[node] = max(rssi, self._seen_nodes.get(node, -1e6))
        return new_device

    def set_key(self, key: str):
        self._crypto_key = key

    def _subscribe(self, set_: set, listener: Callable):
        set_.add(listener)

        def remover():
            if listener in set_:
                set_.remove(listener)

        return remover

    def _publish(self, set_: set, *args, **kwargs):
        for listener in set_:
            listener(*args, **kwargs)

    def subscribe_connect(self, listener: Callable):
        return self._subscribe(self._connect_listeners, listener)

    def subscribe_state(self, listener: Callable):
        return self._subscribe(self._state_listeners, listener)

    async def disconnect(self):
        if not self._client:
            return False
        try:
            await self._client.stop_notify(gatt.PLEJD_LASTDATA)
            await self._client.stop_notify(gatt.PLEJD_LIGHTLEVEL)
            await self._client.disconnect()
        except BleakError:
            pass
        self._client = None
        self._publish(self._connect_listeners, {"connected": False})

    async def connect(self):
        if self.connected:
            return True
        _CONNECTION_LOG.debug("Trying to connect to BLE mesh")

        def _disconnect(reason):
            _CONNECTION_LOG.debug("Disconected from BLE mesh (%s)", reason)
            self._client = None
            self._gateway_node = None
            self._publish(self._connect_listeners, {"connected": False})

        # Try to connect to nodes in order of decreasing RSSI
        filtered_nodes = dict(
            filter(
                lambda n: n[0].address.replace(":", "").upper()
                in self._connectable_nodes,
                self._seen_nodes.items(),
            )
        )
        sorted_nodes = dict(
            sorted(filtered_nodes.items(), key=lambda n: n[1], reverse=True)
        )

        _CONNECTION_LOG.debug(f"Expected nodes: {self._expected_nodes}")
        _CONNECTION_LOG.debug(f"Connectable expected nodes: {self._connectable_nodes}")

        _CONNECTION_LOG.debug(f"Seen nodes: {self._seen_nodes}")
        _CONNECTION_LOG.debug(f"Connectable, seen nodes: {filtered_nodes}")
        _CONNECTION_LOG.debug(f"Sorted by signal strength: {sorted_nodes}")

        if not sorted_nodes:
            _CONNECTION_LOG.debug(
                "Failed to connect to plejd mesh - No valid devices: %s (%s)",
                self._seen_nodes,
                self._connectable_nodes,
            )
            return False
        client = None
        for node in sorted_nodes:
            try:
                _CONNECTION_LOG.debug("Attempting to connect to %s", node)
                client = await establish_connection(
                    BleakClient, node, "plejd", _disconnect
                )

                if not await self._authenticate(client):
                    await client.disconnect()
                    continue
                self._gateway_node = node.address
                break

            except (BleakError, asyncio.TimeoutError) as e:
                _CONNECTION_LOG.warning("Failed to connect to %s: %s", node, str(e))

        else:
            _CONNECTION_LOG.warning(
                "Failed to connect to plejd mesh - %s", sorted_nodes
            )
            return False

        async def _lastdata_listener(_, lastdata: bytearray):

            data = encrypt_decrypt(self._crypto_key, self._gateway_node, lastdata)
            retval = parse_data(data)

            self._publish(self._state_listeners, retval)

            if "button" in retval:
                await self.poll_buttons()

        async def _lightlevel_listener(_, lightlevel: bytearray):
            for state in parse_lightlevel(lightlevel):
                self._publish(self._state_listeners, state)

        await client.start_notify(gatt.PLEJD_LASTDATA, _lastdata_listener)
        await client.start_notify(gatt.PLEJD_LIGHTLEVEL, _lightlevel_listener)
        self._client = client

        self._publish(self._connect_listeners, {"connected": True})
        await self.poll()
        return True

    async def poll(self):
        client = self._client
        if client is None:
            return
        _LOGGER.debug("Polling mesh for current state")
        await client.write_gatt_char(gatt.PLEJD_LIGHTLEVEL, b"\x01", response=True)

    async def poll_buttons(self):
        await self._write(payload_encode.request_button(self))

    async def ping(self):
        async with self._ble_lock:
            if not await self.connect():
                retval = False
            if await self._ping(self._client):
                await self.poll()
                retval = True
        if retval:
            await self.poll_buttons()
        return retval

    async def set_state(self, address: int, **state):
        payloads = payload_encode.set_state(self, address, **state)
        await self._write(payloads)

    async def activate_scene(self, index: int):
        payloads = payload_encode.trigger_scene(self, index)
        return await self._write(payloads)

    async def poll_time(self, address: int):
        client = self._client
        if client is None:
            return False
        payloads = payload_encode.request_time(self, address)
        await self._write(payloads)

        retval = await client.read_gatt_char(gatt.PLEJD_LASTDATA)
        data = encrypt_decrypt(self._crypto_key, self._gateway_node, retval)
        ts = int.from_bytes(data[5:9], "little")
        dt = datetime.fromtimestamp(ts)

        now = datetime.now() + timedelta(seconds=3600 * time.daylight)
        if abs(dt - now) > timedelta(seconds=60):
            _LOGGER.debug(f"Device {address} repported the wrong time {dt} ({now=})")
            return True
        return False

    async def broadcast_time(self):
        payloads = payload_encode.set_time(self)
        await self._write(payloads)

    async def _write(self, payloads):
        client = self._client
        if client is None:
            return False
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

    async def _authenticate(self, client: BleakClient):
        if client is None:
            return False
        try:
            _CONNECTION_LOG.debug("Authenticating with plejd mesh")
            await client.write_gatt_char(gatt.PLEJD_AUTH, b"\0x00", response=True)
            challenge = await client.read_gatt_char(gatt.PLEJD_AUTH)
            response = auth_response(self._crypto_key, challenge)
            await client.write_gatt_char(gatt.PLEJD_AUTH, response, response=True)
            if not await self._ping(client):
                _CONNECTION_LOG.debug("Authentication failed!")
                return False
            _CONNECTION_LOG.debug("Authentication successful")
            return True
        except (BleakError, asyncio.TimeoutError) as e:
            _CONNECTION_LOG.warning("Plejd mesh authentication failed: %s", str(e))
        return False
