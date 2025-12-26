from .plejd_device import PlejdInput, PlejdDeviceType
from ..ble import LastData
from ..ble.debug import rec_log


class PlejdButton(PlejdInput):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outputType = PlejdDeviceType.BUTTON

    @property
    def button_id(self):
        return self.settings.input

    async def parse_lastdata(self, data: LastData):
        match data.command:
            case LastData.CMD_EVENT_FIRED:
                addr = int(data.payload[0])
                button = int(data.payload[1])
                if not (addr == self.deviceAddress and button == self.settings.input):
                    return
                action = "press"
                if len(data.payload) == 3 and data.payload[2] == 0:
                    action = "release"

                rec_log(f"BUTTON {addr=} {button=} {action=}", self.address)

                for listener in self._listeners:
                    listener(
                        {
                            **self._state,
                            "button": button,
                            "action": action,
                        }
                    )
            case _:
                return
