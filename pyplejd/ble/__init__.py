import asyncio
import binascii
import logging
import os
from datetime import datetime, timedelta
from typing import Callable
import time

from bleak import BleakClient, BleakError
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from .crypto import auth_response, encrypt_decrypt
from ..const import PLEJD_AUTH, PLEJD_LASTDATA, PLEJD_LIGHTLEVEL, PLEJD_PING, PLEJD_DATA

_LOGGER = logging.getLogger(__name__)
_DEVLOGGER = logging.getLogger("pyplejd.dev")


class PlejdMesh:
    def __init__(self):
        self._seen_nodes: dict[BLEDevice, int] = {}
        self._expected_nodes = set()
        self._connectable_nodes = set()
        self._gateway_node = None
        self._crypto_key: bytearray = None
        self._client: BleakClient = None

        self._connect_listeners = set()
        self._state_listeners = set()
        self._scene_listeners = set()
        self._button_listeners = set()

        self._ble_lock = asyncio.Lock()

    @property
    def connected(self):
        return self._client is not None

    def expect_device(self, BLEaddress: str, connectable=True):
        self._expected_nodes.add(BLEaddress.upper())
        if connectable:
            self._connectable_nodes.add(BLEaddress.upper())

    def see_device(self, node: BLEDevice, rssi: int):
        _LOGGER.debug(f"Saw device {node} (rssi: {rssi}, prev: {self._seen_nodes.get(node, -1e6)})")
        self._seen_nodes[node] = max(rssi, self._seen_nodes.get(node, -1e6))

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

    def subscribe_scene(self, listener: Callable):
        return self._subscribe(self._scene_listeners, listener)

    def subscribe_button(self, listener: Callable):
        return self._subscribe(self._button_listeners, listener)

    async def disconnect(self):
        if not self._client:
            return False
        try:
            await self._client.stop_notify(PLEJD_LASTDATA)
            await self._client.stop_notify(PLEJD_LIGHTLEVEL)
            await self._client.disconnect()
        except BleakError:
            pass
        self._client = None
        self._publish(self._connect_listeners, {"connected": False})

    async def connect(self):
        _LOGGER.debug("Trying to connect to mesh")
        if self.connected:
            return True

        def _disconnect(reason):
            _LOGGER.debug("_disconnect(%s)", reason)
            self._client = None
            self._gateway_node = None
            self._publish(self._connect_listeners, {"connected": False})

        # Try to connect to nodes in order of decreasing RSSI
        sorted_nodes = dict(
            sorted(self._seen_nodes.items(), key=lambda n: (n[0] in self._connectable_nodes, n[1]), reverse=True)
        )

        if not sorted_nodes:
            _LOGGER.debug(
                "Failed to connect to plejd mesh - No valid devices: %s (%s)",
                self._seen_nodes,
                self._connectable_nodes,
            )
            return False
        client = None
        for node in sorted_nodes:
            try:
                _LOGGER.debug("Attempting to connect to %s", node)
                client = await establish_connection(
                    BleakClient, node, "plejd", _disconnect
                )

                if not await self._authenticate(client):
                    await client.disconnect()
                    continue
                self._gateway_node = node.address
                break

            except (BleakError, asyncio.TimeoutError) as e:
                _LOGGER.warning("Failed to connect to %s: %s", node, str(e))

        else:
            _LOGGER.warning("Failed to connect to plejd mesh - %s", sorted_nodes)
            return False

        async def _lastdata_listener(_, lastdata: bytearray):
            self._parse_lastdata(lastdata)

        async def _lightlevel_listener(_, lightlevel: bytearray):
            self._parse_lightlevel(lightlevel)

        await client.start_notify(PLEJD_LASTDATA, _lastdata_listener)
        await client.start_notify(PLEJD_LIGHTLEVEL, _lightlevel_listener)
        self._client = client

        self._publish(self._connect_listeners, {"connected": True})
        await self.poll()
        return True

    async def poll(self):
        client = self._client
        if client is None:
            return
        _LOGGER.debug("Polling mesh for current state")
        await client.write_gatt_char(PLEJD_LIGHTLEVEL, b"\x01", response=True)

    async def ping(self):
        async with self._ble_lock:
            if not await self.connect():
                return False
            if await self._ping(self._client):
                await self.poll()
                return True
        return False

    async def set_state(self, address: int, state: bool, dim=0, colortemp=None):
        if state:
            if dim is None:
                payload = binascii.a2b_hex(f"{address:02x}0110009701")
            else:
                payload = binascii.a2b_hex(f"{address:02x}0110009801{dim:04x}")
        else:
            payload = binascii.a2b_hex(f"{address:02x}0110009700")
        await self._write(payload)

        if colortemp is not None:
            payload = binascii.a2b_hex(f"{address:02x}01100420030111{colortemp:04x}")
            await self._write(payload)

        return

    async def activate_scene(self, index: int):
        payload = binascii.a2b_hex(f"0201100021{index:02x}")
        return await self._write(payload)

    async def poll_time(self, address: int):
        client = self._client
        if client is None:
            return False
        payload = binascii.a2b_hex(f"{address:02x}0102001b")
        await self._write(payload)

        retval = await client.read_gatt_char(PLEJD_LASTDATA)
        data = encrypt_decrypt(self._crypto_key, self._gateway_node, retval)
        ts = int.from_bytes(data[5:9], "little")
        dt = datetime.fromtimestamp(ts)

        now = datetime.now() + timedelta(seconds=3600 * time.daylight)
        if abs(dt - now) > timedelta(seconds=60):
            _LOGGER.debug(f"Device {address} repported the wrong time {dt} ({now=})")
            return True
        return False

    async def broadcast_time(self):
        now = datetime.now() + timedelta(seconds=3600 * time.daylight)
        now_bytes = int(now.timestamp()).to_bytes(5, "little")
        payload = binascii.a2b_hex(f"000110001b{now_bytes.hex()}")
        await self._write(payload)

    async def _write(self, payload):
        client = self._client
        if client is None:
            return False
        try:
            async with self._ble_lock:
                _LOGGER.debug("Writing to plejd mesh: %s", payload.hex())
                data = encrypt_decrypt(self._crypto_key, self._gateway_node, payload)
                await self._client.write_gatt_char(PLEJD_DATA, data, response=True)
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
            await client.write_gatt_char(PLEJD_PING, ping, response=True)
            pong = await client.read_gatt_char(PLEJD_PING)
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
            _LOGGER.debug("Authenticating with plejd mesh")
            await client.write_gatt_char(PLEJD_AUTH, b"\0x00", response=True)
            challenge = await client.read_gatt_char(PLEJD_AUTH)
            response = auth_response(self._crypto_key, challenge)
            await client.write_gatt_char(PLEJD_AUTH, response, response=True)
            if not await self._ping(client):
                _LOGGER.debug("Authentication failed!")
                return False
            _LOGGER.debug("Authentication successful")
            return True
        except (BleakError, asyncio.TimeoutError) as e:
            _LOGGER.warning("Plejd mesh authentication failed: %s", str(e))
        return False

    def _parse_lastdata(self, lastdata: bytearray):
        data = encrypt_decrypt(self._crypto_key, self._gateway_node, lastdata)
        _LOGGER.debug("Parsing LASTDATA: %s", data.hex())

        address = int(data[0])
        cmd = data[1:3]
        if not cmd == b"\x01\x10":
            _LOGGER.debug("Got non-command LASTDATA: %s", data.hex())
            return
        cmd = data[3:5]

        if address == 0:
            # Broadcast packet
            pass

        if address == 1 and cmd == b"\x00\x1b":
            # _LOGGER.debug("Got time data")
            # Only received if the mesh is already keeping time
            # ts2 = int.from_bytes(data[5:9], "little")
            # dt = datetime.fromtimestamp(ts2)
            return

        if address == 2:
            # Scene update
            pass

        match cmd:
            case b"\x00\xc8" | b"\x00\x98":
                state = bool(data[5])
                dim = int.from_bytes(data[6:8], "little")
                extra_data = data[8:]
                _LOGGER.debug(
                    "Address: %s, state: %s, dim: %s, data: %s (%s / %s)",
                    address,
                    state,
                    dim,
                    extra_data,
                    int.from_bytes(extra_data, "little"),
                    int.from_bytes(extra_data, "big"),
                )
                _LOGGER.debug("DIM Message: %s", data)
                self._publish(
                    self._state_listeners,
                    {
                        "address": address,
                        "state": state,
                        "dim": dim,
                    },
                )
            case b"\x00\x97":
                state = bool(data[5])
                _LOGGER.debug("Address: %s, state: %s", address, state)
                self._publish(
                    self._state_listeners,
                    {
                        "address": address,
                        "state": state,
                    },
                )
            case b"\x00\x16":
                address = int(data[5])
                button = int(data[6])
                _LOGGER.debug("Address: %s, button: %s", address, button)
                self._publish(
                    self._button_listeners,
                    {
                        "address": address,
                        "button": button,
                    },
                )
            case b"\x00\x21":
                scene = int(data[5])
                _LOGGER.debug("Scene: %s", scene)
                self._publish(
                    self._scene_listeners,
                    {
                        "scene": scene,
                    },
                )
            case b"\x04\x20":
                if len(data) < 6:
                    return
                if data[6] == 1:
                    colortemp = int.from_bytes(data[8:10], "big")
                    _LOGGER.debug("Address: %s Colortemp: %s", address, colortemp)

                    self._publish(
                        self._state_listeners,
                        {
                            "address": address,
                            "colortemp": colortemp,
                        },
                    )
                elif data[6] == 3:
                    luminosity = int.from_bytes(data[-2:], "big")
                    _LOGGER.debug("Address: %s luminosity: %s", address, luminosity)
                    self._publish(
                        self._button_listeners,
                        {
                            "address": address,
                            "button": 0,
                        },
                    )
                else:
                    if len(data) > 10:
                        _DEVLOGGER.debug(
                            "Unknown new-style LASTDATA command - address: %s - %s %s %s %s %s",
                            address,
                            data.hex()[0:2],
                            data.hex()[2:6],
                            data.hex()[6:10],
                            data.hex()[10:16],
                            data.hex()[16:]
                        )
                    else:
                        _DEVLOGGER.debug(
                            "Unknown new-style LASTDATA command - address: %s - %s %s %s %s",
                            address,
                            data.hex()[0:2],
                            data.hex()[2:6],
                            data.hex()[6:10],
                            data.hex()[10:]
                        )
            case _:
                _LOGGER.debug("Unknown cmd (%s) to %s: %s", cmd, address, data[5:])
                _DEVLOGGER.debug("Unknown LASTDATA cmd (%s) to %s: %s", cmd, address, data[5:])

    def _parse_lightlevel(self, lightlevel: bytearray):
        _LOGGER.debug("Parsing LIGHTLEVEL: %s", lightlevel.hex())
        for i in range(0, len(lightlevel), 10):
            ll = lightlevel[i : i + 10]
            address = int(ll[0])
            state = bool(ll[1])
            dim = int.from_bytes(ll[5:7], "little")
            _LOGGER.debug("Address: %s, state: %s, dim: %s", address, state, dim)
            _LOGGER.debug("LL message: %s", ll)
            self._publish(
                self._state_listeners,
                {
                    "address": address,
                    "state": state,
                    "dim": dim,
                },
            )
        pass
