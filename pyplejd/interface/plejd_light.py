from .plejd_device import PlejdOutput, PlejdTraits, PlejdDeviceType
from ..ble import LastData, MiniPkg, LightLevel
from ..ble.debug import rec_log


class PlejdLight(PlejdOutput):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.outputType = PlejdDeviceType.LIGHT
        self.dimmable = PlejdTraits.DIM in self.capabilities

        self.colortemp = None
        if PlejdTraits.TEMP in self.capabilities and (
            ct := self.settings.colorTemperature
        ):
            self.colortemp = [ct.minTemperature, ct.maxTemperature]

    async def parse_lightlevel(self, level: LightLevel):
        state = self._state
        state.update(
            {
                "state": level.state,
                "dim": level.dim / 256,
            }
        )
        for listener in self._listeners:
            listener(self._state)

    async def parse_lastdata(self, data: LastData):
        state = self._state
        match data.command:
            case LastData.CMD_GROUP_OUTPUT_STATE:
                state["state"] = bool(data.payload[0])
            case (
                LastData.CMD_GROUP_OUTPUT_STATE_AND_LEVEL
                | LastData.CMD_OUTPUT_STATE_AND_LEVEL
            ):
                state["state"] = bool(data.payload[0])
                if state["state"]:
                    state["dim"] = data.payload[2]
            case LastData.CMD_OUTPUT_SET:
                for p in data.minipkgs:
                    if p.type == MiniPkg.TPE_WHITEBALANCE:
                        state["colortemp"] = int.from_bytes(p.payload, byteorder="big")

                rec_log(f"MiniPkg:", self.address)
                rec_log(f"{list(data.minipkgs)}", self.address)
            case _:
                if data.address in [self.address, self.rxAddress]:
                    rec_log(f"Unknown command received: {data.command}", self.address)
                    rec_log(f"    {data.hex}", self.address)
                return

        for listener in self._listeners:
            listener(self._state)

    async def turn_on(self, dim=None, colortemp=None):
        if not self._mesh:
            return
        commands: list[LastData] = []
        if dim is not None:
            dim = int(dim)
            commands.append(
                LastData(
                    address=self.address,
                    command=LastData.CMD_GROUP_OUTPUT_STATE_AND_LEVEL,
                    payload=[0x1, dim, dim],
                )
            )
        else:
            commands.append(
                LastData(
                    address=self.address,
                    command=LastData.CMD_GROUP_OUTPUT_STATE,
                    payload=[0x1],
                )
            )
        if colortemp is not None:
            colortemp = int(1e6 / colortemp)
            commands.append(
                LastData(
                    address=self.address,
                    command=LastData.CMD_OUTPUT_SET,
                    payload=[
                        MiniPkg(
                            type=MiniPkg.TPE_SOURCE,
                            payload=[MiniPkg.SRC_MANUAL],
                        ),
                        MiniPkg(
                            type=MiniPkg.TPE_WHITEBALANCE,
                            payload=colortemp.to_bytes(2),
                        ),
                    ],
                )
            )

        await self._mesh.write(*(c.hex for c in commands))

    async def turn_off(self):
        if not self._mesh:
            return

        cmd = LastData(
            address=self.address,
            command=LastData.CMD_GROUP_OUTPUT_STATE,
            payload=[0x0],
        )
        await self._mesh.write(cmd.hex)
