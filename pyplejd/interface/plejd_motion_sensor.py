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
            # CCL-01's built-in PIR is registered on the mesh as an input
            # (buttonType "CCLMotionSensor", same input-address table as a
            # regular push button - see PlejdDeviceInputSetting in the site
            # data), so a detection fires the same CMD_EVENT_FIRED the mesh
            # uses for button presses, addressed to this device's own
            # deviceAddress/input pair - not CMD_OUTPUT_SET, which this
            # class previously (and exclusively) listened for. That left
            # "motion" permanently unset: CMD_OUTPUT_SET does carry this
            # device's battery/lux reports, but never a real detection, so
            # self.trigger() was never reachable. Handling CMD_EVENT_FIRED
            # here, matched the same way PlejdButton.parse_lastdata does,
            # is what actually lets a detection reach self.trigger().
            case LastData.CMD_EVENT_FIRED:
                addr = int(data.payload[0])
                button = int(data.payload[1])
                if not (addr == self.deviceAddress and button == self.settings.input):
                    return
                if len(data.payload) == 3 and data.payload[2] == 0:
                    # "release" - a PIR has no meaningful release edge to
                    # report; only a fresh detection should (re)trigger.
                    return
                rec_log(f"MOTION {addr=} {button=}", self.address)
                self.trigger()
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

                cmd = LastData(
                    address=self.address,
                    command=LastData.CMD_AMBIENT_LIGHT_LEVEL,
                )
                cmd.command_type = LastData.CMDT_READ
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
