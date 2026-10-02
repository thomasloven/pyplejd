import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakError
from bleak.exc import BleakCharacteristicNotFoundError

from pyplejd import ble
from pyplejd.ble import PlejdMesh, MeshDevice, MAX_CONSECUTIVE_KEEPALIVE_FAILURES
from pyplejd.ble import ble_characteristics as gatt

PING_BYTE = b"\x10"
PONG_BYTE = b"\x11"


class FakeClient:
    """Stands in for BleakClientWithServiceCache; failures are injected per call."""

    def __init__(self):
        self.is_connected = True
        self.ping_error: Exception | None = None
        self.write_error: Exception | None = None
        self.stop_notify = AsyncMock()
        self.start_notify = AsyncMock()
        self.clear_cache = AsyncMock(return_value=True)
        self.disconnect = AsyncMock(side_effect=self._disconnect)
        self.lastdata = b"\x00" * 16

    async def _disconnect(self):
        self.is_connected = False

    async def write_gatt_char(self, char, data, response=True):
        if char == gatt.PLEJD_PING and self.ping_error:
            raise self.ping_error
        if char == gatt.PLEJD_DATA and self.write_error:
            raise self.write_error

    async def read_gatt_char(self, char):
        if char == gatt.PLEJD_PING:
            if self.ping_error:
                raise self.ping_error
            return PONG_BYTE
        if char == gatt.PLEJD_LASTDATA:
            if self.write_error:
                raise self.write_error
            return self.lastdata
        raise AssertionError(f"unexpected read of {char}")


class Node(MeshDevice):
    def __init__(self, address: str, rssi: int):
        self.BLEaddress = address
        self.connectable = True
        self.rssi = rssi
        self.bleDevice = MagicMock(name=address)
        self.is_gateway = False

    def update(self):
        pass


@pytest.fixture(autouse=True)
def deterministic_ping(monkeypatch):
    monkeypatch.setattr(os, "urandom", lambda n: PING_BYTE)


@pytest.fixture
def clients(monkeypatch):
    """Each connection attempt gets a fresh FakeClient, recorded in order."""
    created: list[FakeClient] = []

    async def fake_establish_connection(_cls, _device, _name, disconnected_callback=None, **_):
        client = FakeClient()
        client.disconnected_callback = disconnected_callback
        created.append(client)
        return client

    monkeypatch.setattr(ble, "establish_connection", fake_establish_connection)
    return created


@pytest.fixture
def manager():
    return MagicMock()


@pytest.fixture
async def mesh(manager, clients, monkeypatch):
    mesh = PlejdMesh(manager)
    mesh.set_key("00" * 16)
    mesh.expect_device(Node("AABBCCDDEEFF", rssi=-50))
    monkeypatch.setattr(mesh, "_authenticate", AsyncMock(return_value=True))
    monkeypatch.setattr(mesh, "poll", AsyncMock())
    monkeypatch.setattr(mesh, "poll_buttons", AsyncMock())
    assert await mesh.connect()
    manager.connect_callback.reset_mock()
    return mesh


async def test_missing_characteristic_on_keepalive_drops_connection(mesh, clients, manager):
    client = clients[0]
    client.ping_error = BleakCharacteristicNotFoundError(gatt.PLEJD_PING)

    assert not await mesh.ping()

    assert not mesh.connected
    client.clear_cache.assert_awaited_once()
    client.disconnect.assert_awaited_once()
    manager.connect_callback.assert_called_once_with(False)


async def test_next_ping_after_drop_reconnects_on_fresh_client(mesh, clients):
    clients[0].ping_error = BleakCharacteristicNotFoundError(gatt.PLEJD_PING)
    await mesh.ping()

    assert await mesh.ping()

    assert len(clients) == 2
    assert mesh._client is clients[1]


async def test_single_timeout_keeps_connection(mesh, clients):
    clients[0].ping_error = asyncio.TimeoutError()

    assert not await mesh.ping()

    assert mesh._client is clients[0]
    clients[0].disconnect.assert_not_awaited()


async def test_repeated_timeouts_drop_connection(mesh, clients):
    clients[0].ping_error = asyncio.TimeoutError()

    for _ in range(MAX_CONSECUTIVE_KEEPALIVE_FAILURES):
        await mesh.ping()

    assert not mesh.connected
    clients[0].disconnect.assert_awaited_once()


async def test_successful_keepalive_resets_failure_count(mesh, clients):
    client = clients[0]
    for _ in range(MAX_CONSECUTIVE_KEEPALIVE_FAILURES * 2):
        client.ping_error = asyncio.TimeoutError()
        await mesh.ping()
        client.ping_error = None
        assert await mesh.ping()

    assert mesh._client is client


async def test_teardown_disconnects_even_when_stop_notify_fails(mesh, clients):
    client = clients[0]
    client.stop_notify.side_effect = BleakError("characteristic not found")
    client.ping_error = BleakCharacteristicNotFoundError(gatt.PLEJD_PING)

    await mesh.ping()

    client.disconnect.assert_awaited_once()


async def test_explicit_disconnect_survives_failing_stop_notify(mesh, clients, manager):
    client = clients[0]
    client.stop_notify.side_effect = BleakError("characteristic not found")

    await mesh.disconnect()

    client.disconnect.assert_awaited_once()
    client.clear_cache.assert_not_awaited()
    manager.connect_callback.assert_called_once_with(False)


async def test_missing_characteristic_on_write_drops_connection(mesh, clients):
    clients[0].write_error = BleakCharacteristicNotFoundError(gatt.PLEJD_DATA)

    assert not await asyncio.wait_for(mesh._write([b"\x01"]), timeout=1)

    assert not mesh.connected
    clients[0].disconnect.assert_awaited_once()


async def test_timeout_on_write_keeps_connection(mesh, clients):
    clients[0].write_error = asyncio.TimeoutError()

    assert not await mesh._write([b"\x01"])

    assert mesh._client is clients[0]


async def test_missing_characteristic_on_time_poll_drops_connection(mesh, clients, monkeypatch):
    monkeypatch.setattr(mesh, "write", AsyncMock())
    clients[0].write_error = BleakCharacteristicNotFoundError(gatt.PLEJD_LASTDATA)

    assert await mesh.poll_time(1) is False

    assert not mesh.connected


async def test_time_poll_stops_when_its_write_dropped_the_connection(mesh, clients):
    clients[0].write_error = BleakCharacteristicNotFoundError(gatt.PLEJD_DATA)

    assert await mesh.poll_time(1) is False

    assert not mesh.connected


async def test_disconnect_callback_after_own_teardown_is_ignored(mesh, clients, manager):
    client = clients[0]
    client.ping_error = BleakCharacteristicNotFoundError(gatt.PLEJD_PING)
    await mesh.ping()
    manager.connect_callback.reset_mock()

    client.disconnected_callback(client)

    manager.connect_callback.assert_not_called()


async def test_link_drop_reported_by_bleak_marks_mesh_disconnected(mesh, clients, manager):
    client = clients[0]
    client.is_connected = False

    client.disconnected_callback(client)

    assert mesh._client is None
    manager.connect_callback.assert_called_once_with(False)


async def test_late_callback_from_old_client_keeps_new_connection(mesh, clients, manager):
    old = clients[0]
    old.ping_error = BleakCharacteristicNotFoundError(gatt.PLEJD_PING)
    await mesh.ping()
    assert await mesh.ping()
    manager.connect_callback.reset_mock()

    old.disconnected_callback(old)

    assert mesh._client is clients[1]
    manager.connect_callback.assert_not_called()


async def test_link_lost_without_callback_is_torn_down_before_reconnect(mesh, clients):
    stale = clients[0]
    stale.is_connected = False

    assert await mesh.ping()

    stale.disconnect.assert_awaited_once()
    assert mesh._client is clients[1]
