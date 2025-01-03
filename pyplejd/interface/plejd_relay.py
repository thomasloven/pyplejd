from .plejd_device import PlejdOutput, PlejdTraits


class PlejdRelay(PlejdOutput):

    def parse_state(self, state):
        available = state.get("available", False)

        return {
            "available": available,
            "state": state.get("state", False) if available else False,
        }

    async def turn_on(self):
        if not self._mesh:
            return
        await self._mesh.set_state(self.address, True)

    async def turn_off(self):
        if not self._mesh:
            return
        await self._mesh.set_state(self.address, False)
