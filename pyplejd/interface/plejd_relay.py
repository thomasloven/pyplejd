from .plejd_device import PlejdOutput, PlejdDeviceType


class PlejdRelay(PlejdOutput):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outputType = PlejdDeviceType.SWITCH

    def parse_state(self, update, state):
        available = state.get("available", False)

        return {
            "available": available,
            "state": state.get("state", False) if available else False,
        }

    async def turn_on(self):
        if not self._mesh:
            return
        await self._mesh.set_state(self.address, state=True)

    async def turn_off(self):
        if not self._mesh:
            return
        await self._mesh.set_state(self.address, state=False)
