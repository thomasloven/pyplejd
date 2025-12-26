from .plejd_device import PlejdOutput, PlejdDeviceType
from ..ble import LastData
from ..ble.debug import rec_log


class PlejdRelay(PlejdOutput):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outputType = PlejdDeviceType.SWITCH

    async def parse_lastdata(self, data: LastData):
        state = self._state
        match data.command:
            case (
                LastData.CMD_GROUP_OUTPUT_STATE
                | LastData.CMD_GROUP_OUTPUT_STATE_AND_LEVEL
            ):
                state["state"] = bool(data.payload[0])
            case _:
                if data.address in [self.address, self.rxAddress]:
                    rec_log(f"Unknown command received: {data.command}", self.address)
                    rec_log(f"    {data.hex}", self.address)
                return

        for listener in self._listeners:
            listener(self._state)

    async def turn_on(self):
        if not self._mesh:
            return
        cmd = LastData(
            address=self.address,
            command=LastData.CMD_GROUP_OUTPUT_STATE,
            payload=[0x1],
        )
        await self._mesh.write(cmd.hex)

    async def turn_off(self):
        if not self._mesh:
            return
        cmd = LastData(
            address=self.address,
            command=LastData.CMD_GROUP_OUTPUT_STATE,
            payload=[0x0],
        )
        await self._mesh.write(cmd.hex)
