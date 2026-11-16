import asyncio
import unittest
from unittest.mock import AsyncMock, Mock

from pyplejd import PlejdManager
from pyplejd.ble import LastData
from pyplejd.interface.plejd_light import PlejdLight
from pyplejd.interface.plejd_relay import PlejdRelay
from pyplejd.interface.plejd_cover import PlejdCover
from pyplejd.interface.plejd_thermostat import PlejdThermostat


def device(cls):
    # Only parser state is needed; no cloud credentials or BLE connection.
    obj = cls.__new__(cls)
    obj.address = 1
    obj.rxAddress = 2
    obj._state = {"state": True, "dim": 42}
    obj._listeners = {Mock()}
    obj.regulation_mode = "temperature"
    return obj


class LastDataTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_payload_preserves_state_and_does_not_notify(self):
        commands = {
            PlejdLight: [0x0097, 0x0098, 0x00C8, 0x0420],
            PlejdRelay: [0x0097, 0x0098],
            PlejdCover: [0x0098, 0x00C8],
            PlejdThermostat: [0x0098, 0x00C8, 0x045C, 0x0461],
        }
        for cls, values in commands.items():
            for command in values:
                with self.subTest(device=cls.__name__, command=command):
                    obj = device(cls)
                    before = obj._state.copy()
                    await obj.parse_lastdata(LastData(address=1, command=command))
                    self.assertEqual(obj._state, before)
                    next(iter(obj._listeners)).assert_not_called()

    async def test_valid_light_and_relay_messages_update_and_notify(self):
        for cls in (PlejdLight, PlejdRelay):
            with self.subTest(device=cls.__name__):
                obj = device(cls)
                await obj.parse_lastdata(
                    LastData(address=1, command=0x0097, payload=[0])
                )
                self.assertFalse(obj._state["state"])
                next(iter(obj._listeners)).assert_called_once_with(obj._state)

    async def test_valid_cover_and_thermostat_messages_update_and_notify(self):
        for cls in (PlejdCover, PlejdThermostat):
            with self.subTest(device=cls.__name__):
                obj = device(cls)
                await obj.parse_lastdata(
                    LastData(address=1, command=0x0098, payload=[0, 0, 0])
                )
                next(iter(obj._listeners)).assert_called_once_with(obj._state)
                self.assertIn("position" if cls is PlejdCover else "target", obj._state)

    async def test_device_failure_does_not_stop_delivery(self):
        for address in (0, 1, 2):
            with self.subTest(address=address):
                manager = PlejdManager.__new__(PlejdManager)
                first = Mock(
                    address=1,
                    rxAddress=2,
                    parse_lastdata=AsyncMock(side_effect=ValueError("bad message")),
                )
                second = Mock(address=1, rxAddress=2, parse_lastdata=AsyncMock())
                manager.devices = [first, second]
                message = LastData(address=address, command=0x0098)
                with self.assertLogs("pyplejd", level="WARNING"):
                    await manager.lastdata_callback(message)
                first.parse_lastdata.assert_awaited_once_with(message)
                second.parse_lastdata.assert_awaited_once_with(message)

    async def test_cancellation_is_not_swallowed(self):
        manager = PlejdManager.__new__(PlejdManager)
        manager.devices = [
            Mock(
                address=1,
                rxAddress=2,
                parse_lastdata=AsyncMock(side_effect=asyncio.CancelledError),
            )
        ]
        with self.assertRaises(asyncio.CancelledError):
            await manager.lastdata_callback(LastData(address=1, command=0x0098))

    async def test_unaddressed_devices_do_not_receive_message(self):
        manager = PlejdManager.__new__(PlejdManager)
        obj = Mock(address=1, rxAddress=2, parse_lastdata=AsyncMock())
        manager.devices = [obj]
        await manager.lastdata_callback(LastData(address=3, command=0x0098))
        obj.parse_lastdata.assert_not_awaited()
