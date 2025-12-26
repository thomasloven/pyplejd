import asyncio
from .plejd_device import PlejdInput, PlejdDeviceType
from ..ble import LastData, MiniPkg
from ..ble.debug import rec_log


class PlejdMotionSensor(PlejdInput):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outputType = PlejdDeviceType.MOTION

        self.cooldown = None
        # Motion sensors seem to timeout at 25-35 seconds
        # by the Nyquist criteria, we need our timeout to be at least
        # twice that time in order not to significantly miss any events.
        self.timeout = 75

    async def parse_lastdata(self, data: LastData):
        state = self._state
        match data.command:
            case LastData.CMD_OUTPUT_SET:
                for p in data.minipkgs:
                    if (
                        p.type == MiniPkg.TPE_SOURCE
                        and p.payload
                        and p.payload[0] == MiniPkg.SRC_MOTION
                    ):
                        self.trigger()
                    if p.type == MiniPkg.TPE_BATTERYINFO:
                        state["battery"] = int.from_bytes(p.payload, byteorder="big")
                    if p.type == MiniPkg.TPE_LUX:
                        state["bright"] = p.payload[0] == 2

                rec_log(f"MiniPkg:", self.address)
                rec_log(f"{list(data.minipkgs)}", self.address)

                # for p in data.minipkgs:
                #     if p.type == MiniPkg.TPE_LUX:
                #         if p.payload.get(0,0) == 1:
                #             # dark
                #             pass
                #         elif p.payload.get(0,0) == 2:
                #             # light
                #             pass

                cmd = LastData(
                    address=self.address,
                    command=LastData.CMD_AMBIENT_LIGHT_LEVEL,
                )
                cmd.command_type=LastData.CMDT_READ
                rec_log(f"Write {cmd.hex}", self.address)
                await self._mesh.write(cmd.hex)
            case _:
                if data.address in [self.address, self.rxAddress]:
                    rec_log(f"Unknown command received: {data.command}", self.address)
                    rec_log(f"    {data.hex}", self.address)
                return

        for listener in self._listeners:
            listener(self._state)
        self._state["motion"] = None

    def trigger(self):
        self._state["motion"] = True
        if self.cooldown:
            self.cooldown()
            self.cooldown = None

        def _callback():
            self._state["motion"] = False
            for listener in self._listeners:
                listener(self._state)

        loop = asyncio.get_running_loop()
        self.cooldown = loop.call_at(loop.time() + self.timeout, _callback).cancel
        pass
