from .plejd_device import PlejdOutput, PlejdTraits, PlejdDeviceType
from ..ble import LastData, MiniPkg, LightLevel


# Modes:
# 0 service
# 1 Curing
# 2 Vacation
# 3 Boost
# 4 FrostProtection
# 5 NightTimeReduction
# 7 Normal


class PlejdThermostat(PlejdOutput):

    def _parse_state(self, state: int, payload: list[int]):

        data = state << 16 + payload[0] << 8 + payload[1]

        # 0000 000S 1111 1111 2222 2222
        # S = State bit
        # 1 = Payload byte 0
        # 2 = Payload byte 1

        # 0000 000M MMET TTTT TTCC CCCC
        # M = Mode
        # E = Error
        # T = Target
        # C = Current

        mode = (data & 0x01C000) >> 14
        error = bool(data & 0x002000)
        target = (data & 0x001FC0) >> 6
        current = data & 0x00003F

        return {
            "mode": -1 if error else mode,
            "target": target - 10,
            "current": current - 10,
        }

    async def parse_lightlevel(self, level: LightLevel):
        state = self._state

        state.update(self._parse_state(level.state, level.payload))

        for listener in self._listeners:
            listener(self._state)

    async def parse_lastdata(self, data):
        state = self._state
        if data.command in [
            LastData.CMD_OUTPUT_STATE_AND_LEVEL,
            LastData.CMD_GROUP_OUTPUT_STATE_AND_LEVEL,
        ]:
            state.update(self._parse_state(data.payload[0], data.payload[1:]))
        for listener in self._listeners:
            listener(self._state)


def target_temp(temp):
    num1 = temp * 10
    num2 = (num1 & 0x8) >> 8

    (LastData.CMD_TRM_TEMPERATURE_REGULATING_SETPOINT, [num1, num2])
    pass
