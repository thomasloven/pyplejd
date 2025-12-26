from .plejd_device import PlejdOutput, PlejdDeviceType, LightLevel
from ..ble import LastData, MiniPkg
from ..ble.debug import rec_log


class PlejdCover(PlejdOutput):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # settings.coverableSettings.coverableTiltStart
        # settings.coverableSettings.coverableTiltEnd
        self.previous_position = None
        self.outputType = PlejdDeviceType.COVER

    def _parse_state(self, state: int, payload: list[int]):
        moving = bool(state)
        direction = "up" if bool(payload[0] & 0x80) else "down"

        stopping = bool(payload[1] & 0x80)
        position = payload[0] & 0x7F
        target = payload[1] & 0x7F
        lost = (position > target) if direction == "up" else (target > position)

        position = position / 0x7F * 100
        target = target / 0x7F * 100

        rec_log(
            f"{moving=} {direction}, {position=:.1f}% {target=:.1f}% extra={"".join(f"{b:02x}" for b in payload[2:])}",
            self.address,
        )
        return {
            "position": None if lost else position,
            "moving": moving,
            "opening": direction == "up",
        }

    async def parse_lightlevel(self, level: LightLevel):
        state = self._state
        state.update(self._parse_state(level.state, level.payload))
        for listener in self._listeners:
            listener(self._state)

    async def parse_lastdata(self, data: LastData):
        state = self._state
        if data.command in [
            LastData.CMD_OUTPUT_STATE_AND_LEVEL,
            LastData.CMD_GROUP_OUTPUT_STATE_AND_LEVEL,
        ]:
            state.update(self._parse_state(data.payload[0], data.payload[1:]))
            # moving = bool(data.payload[0])
            # direction = "up" if bool(data.payload[1] & 0x80) else "down"

            # # stopping = bool(data.payload[2] & 0x80)
            # position = data.payload[1] & 0x7F
            # target = data.payload[2] & 0x7F
            # lost = (position > target) if direction == "up" else (target > position)

            # position = position / 0x7F * 100
            # target = target / 0x7F * 100
            # rec_log(
            #     f"{moving=} {direction}, {position=:.1f}% {target=:.1f}% extra={"".join(f"{b:02x}" for b in data.payload[3:])}",
            #     self.address,
            # )
            # state["position"] = None if lost else position
            # state["moving"] = moving
            # state["opening"] = direction == "up"

        elif data.command == LastData.CMD_OUTPUT_SET:
            rec_log(f"MiniPkg:", self.address)
            rec_log(f"{list(data.minipkgs)}", self.address)
            return
        else:
            if data.address in [self.address, self.rxAddress]:
                rec_log(f"Unknown command received: {data.command}", self.address)
                rec_log(f"    {data.hex}", self.address)
            return

        for listener in self._listeners:
            listener(self._state)

    # def parse_state(self, update, state):
    #     available = state.get("available", False)
    #     moving = bool(state.get("state", 0))
    #     position = state.get("cover_position", 0) / 0x7FFF * 100
    #     opening = None
    #     if moving:
    #         opening = bool(position > self.previous_position)
    #     self.previous_position = position
    #     return {
    #         "available": available,
    #         "moving": bool(state.get("state", 0)),
    #         "position": state.get("cover_position", 0) / 0x7FFF * 100,
    #         "angle": state.get("cover_angle", 0) * 5,
    #         "opening": opening,
    #     }

    async def open(self):
        await self.set_position(100)

    async def close(self):
        await self.set_position(0)

    async def stop(self):
        await self._mesh.write(
            LastData(
                address=self.address,
                command=LastData.CMD_OUTPUT_SET,
                payload=[
                    MiniPkg(
                        type=MiniPkg.TPE_SOURCE,
                        payload=[MiniPkg.SRC_APP],
                    ),
                    MiniPkg(
                        type=MiniPkg.TPE_WINDOWCONTROL,
                        payload=[0],
                    ),
                ],
            ).hex
        )

    async def set_position(self, position=None, tilt=None):

        if position is None and tilt is None:
            return
        payload = [
            MiniPkg(
                type=MiniPkg.TPE_SOURCE,
                payload=[MiniPkg.SRC_APP],
            )
        ]

        if position is not None:
            level = int(255 * position / 100)
            level = level & 0xFF
            payload.append(
                MiniPkg(
                    type=MiniPkg.TPE_WINDOWCONTROL,
                    payload=[1, level, level],
                )
            )

        if tilt is not None:
            payload.append(
                MiniPkg(
                    type=MiniPkg.TPE_TILT,
                    payload=[tilt & 0xFF],
                )
            )

        await self._mesh.write(
            LastData(
                address=self.address,
                command=LastData.CMD_OUTPUT_SET,
                payload=payload,
            ).hex
        )
