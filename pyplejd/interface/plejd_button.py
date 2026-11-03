import time

from .plejd_device import PlejdInput, PlejdDeviceType
from ..ble import LastData
from ..ble.debug import rec_log


# Hold updates were observed about every 0.2 seconds on WPH-01 firmware 4.41.3.
# Expire the pending input so later, unrelated state reports cannot drive it.
_WPH_GESTURE_IDLE_TIMEOUT = 1.5


class PlejdButton(PlejdInput):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outputType = PlejdDeviceType.BUTTON
        self._gesture_pending = False
        self._gesture_hold = False
        self._gesture_level = None
        self._gesture_last_seen = 0

    @property
    def button_id(self):
        return self.settings.input

    async def parse_lastdata(self, data: LastData):
        """Correlate native WPH-01 tap/dim reports with the pressed input."""
        if (
            data.address == self.deviceAddress
            and self.hardware.startswith("WPH-01")
            and self._gesture_pending
            and data.command in (
                LastData.CMD_GROUP_OUTPUT_STATE,
                LastData.CMD_GROUP_OUTPUT_STATE_AND_LEVEL,
            )
        ):
            now = time.monotonic()
            if now - self._gesture_last_seen > _WPH_GESTURE_IDLE_TIMEOUT:
                self._gesture_pending = False
                return
            self._gesture_last_seen = now
            if data.command == LastData.CMD_GROUP_OUTPUT_STATE and data.payload:
                if not self._gesture_hold:
                    self._gesture_pending = False
                    self._emit("click", on=bool(data.payload[0]))
                return
            if (
                data.command == LastData.CMD_GROUP_OUTPUT_STATE_AND_LEVEL
                and len(data.payload) >= 3
            ):
                level = int(data.payload[2])
                delta = (
                    level - self._gesture_level
                    if self._gesture_level is not None
                    else 0
                )
                self._gesture_level = level
                self._gesture_hold = True
                self._emit("dim", brightness=level, brightness_delta=delta)
                return

        match data.command:
            case LastData.CMD_EVENT_FIRED:
                addr = int(data.payload[0])
                button = int(data.payload[1])
                if addr != self.deviceAddress:
                    return
                if button != self.settings.input:
                    self._gesture_pending = False
                    self._gesture_hold = False
                    self._gesture_level = None
                    return
                action = "press"

                if len(data.payload) >= 3 and data.payload[-1] == 0:
                    action = "release"
                self._gesture_pending = action == "press"
                self._gesture_last_seen = time.monotonic()
                self._gesture_hold = False
                self._gesture_level = None

                rec_log(f"BUTTON {addr=} {button=} {action=}", self.address)

                self._emit(action)
            case _:
                return

    def _emit(self, action, **details):
        for listener in self._listeners:
            listener(
                {
                    **self._state,
                    "button": self.settings.input,
                    "action": action,
                    **details,
                }
            )
