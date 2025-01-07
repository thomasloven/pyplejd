from .plejd_device import PlejdOutput, PlejdTraits, PlejdDeviceType


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

    def parse_state(self, update, state):
        available = state.get("available", False)
        return {
            "available": available,
            "state": bool(state.get("state", False)) if available else False,
            "dim": state.get("dim", 0) / 0xFF * 255,
            "colortemp": state.get("colortemp", None),
        }

    async def turn_on(self, dim=None, colortemp=None):
        if not self._mesh:
            return
        if dim is not None:
            dim = int(dim)
        if colortemp is not None:
            colortemp = int(1e6 / colortemp)

        await self._mesh.set_state(
            self.address, state=True, dim=dim, colortemp=colortemp
        )

    async def turn_off(self):
        if not self._mesh:
            return
        await self._mesh.set_state(self.address, state=False)
