"""Button event decoding without a Bluetooth connection or cloud credentials."""

from types import SimpleNamespace
import unittest

from pyplejd.ble.lastdata import LastData
from pyplejd.interface.plejd_button import PlejdButton


class PlejdButtonTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        device_id = "000000000000"
        self.button = PlejdButton(
            address=41,
            deviceAddress=39,
            device=SimpleNamespace(
                deviceId=device_id, objectId="button", traits=0
            ),
            plejdDevice=SimpleNamespace(deviceId=device_id),
            settings=SimpleNamespace(input=1),
            room=None,
            mesh=None,
            rxAddress=41,
        )
        self.events = []
        self.button.subscribe(self.events.append)

    async def test_captured_extended_press_and_release(self):
        # WPH-01, firmware 4.41.3: five-byte payload, flag in the last byte.
        for frame, action in (
            ("000110001627019d0a01", "press"),
            ("000110001627011c0b00", "release"),
        ):
            with self.subTest(action=action):
                await self.button.parse_lastdata(LastData(bytearray.fromhex(frame)))
                self.assertEqual(self.events[-1], {"button": 1, "action": action})
        self.assertEqual(len(self.events), 2)

    async def test_legacy_button_events(self):
        for payload, action in (
            ([39, 1], "press"),
            ([39, 1, 1], "press"),
            ([39, 1, 0], "release"),
        ):
            with self.subTest(payload=payload):
                self.events.clear()
                await self.button.parse_lastdata(
                    LastData(command=LastData.CMD_EVENT_FIRED, payload=payload)
                )
                self.assertEqual(self.events, [{"button": 1, "action": action}])

    async def test_extended_press_with_zero_in_legacy_flag_position(self):
        await self.button.parse_lastdata(
            LastData(command=LastData.CMD_EVENT_FIRED, payload=[39, 1, 0, 11, 1])
        )
        self.assertEqual(self.events, [{"button": 1, "action": "press"}])

    async def test_lower_button_extended_release(self):
        self.button.settings.input = 3
        await self.button.parse_lastdata(
            LastData(command=LastData.CMD_EVENT_FIRED, payload=[39, 3, 28, 11, 0])
        )
        self.assertEqual(self.events, [{"button": 3, "action": "release"}])

    async def test_variable_length_payloads_use_final_flag(self):
        for payload, action in (
            ([39, 1, 11, 0], "release"),
            ([39, 1, 28, 11, 1, 0], "release"),
            ([39, 1, 11, 1], "press"),
            ([39, 1, 28, 11, 0, 1], "press"),
        ):
            with self.subTest(payload=payload):
                self.events.clear()
                await self.button.parse_lastdata(
                    LastData(command=LastData.CMD_EVENT_FIRED, payload=payload)
                )
                self.assertEqual(self.events, [{"button": 1, "action": action}])

    async def test_other_devices_and_inputs_are_ignored(self):
        for payload in ([40, 1, 28, 11, 0], [39, 3, 28, 11, 0]):
            with self.subTest(payload=payload):
                await self.button.parse_lastdata(
                    LastData(command=LastData.CMD_EVENT_FIRED, payload=payload)
                )
                self.assertEqual(self.events, [])

    async def test_other_commands_are_ignored(self):
        await self.button.parse_lastdata(
            LastData(command=LastData.CMD_SCENE, payload=[39, 1, 28, 11, 0])
        )
        self.assertEqual(self.events, [])


if __name__ == "__main__":
    unittest.main()
