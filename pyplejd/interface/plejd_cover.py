from .plejd_device import PlejdOutput, PlejdDeviceType


class PlejdCover(PlejdOutput):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # settings.coverableSettings.coverableTiltStart
        # settings.coverableSettings.coverableTiltEnd
        self.previous_position = None
        self.outputType = PlejdDeviceType.COVER

    def parse_state(self, update, state):
        available = state.get("available", False)
        moving = bool(state.get("state", 0))
        position = state.get("cover_position", 0) / 0x7FFF * 100
        opening = None
        if moving:
            opening = bool(position > self.previous_position)
        self.previous_position = position
        return {
            "available": available,
            "moving": bool(state.get("state", 0)),
            "position": state.get("cover_position", 0) / 0x7FFF * 100,
            "angle": state.get("cover_angle", 0) * 5,
            "opening": opening,
        }

    async def open(self):
        await self._mesh.set_state(self.address, cover=1 * 0xFFFF)

    async def close(self):
        await self._mesh.set_state(self.address, cover=0)

    async def stop(self):
        await self._mesh.set_state(self.address, cover=-1)

    async def set_position(self, position):
        await self._mesh.set_state(self.address, cover=int(position / 100 * 0xFFFF))
