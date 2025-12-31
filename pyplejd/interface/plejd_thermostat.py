from .plejd_device import PlejdOutput, PlejdDeviceType, PlejdTraits
from ..ble import LastData, LightLevel


# Modes:
# 0 service
# 1 Curing
# 2 Vacation
# 3 Boost
# 4 FrostProtection
# 5 NightTimeReduction
# 6 DayTimeReduction
# 7 Normal


class PlejdThermostat(PlejdOutput):

    MODE_SERVICE = 0
    MODE_VACATION = 2
    MODE_BOOST = 3
    MODE_FROST = 4
    MODE_NIGHT = 5
    MODE_LOW = 6
    MODE_NORMAL = 7

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.outputType = PlejdDeviceType.CLIMATE
        self.regulation_mode = "TEMP"
        if self.settings.climateSettings.regulationMode == "PWM":
            self.limits = {
                "min": self.settings.climateSettings.pwmRegulationConfig.minDutyUserInput,
                "max": self.settings.climateSettings.pwmRegulationConfig.maxDutyUserInput,
                "step": self.settings.climateSettings.pwmRegulationConfig.interval,
            }
            self.outputType = PlejdDeviceType.PWM
            self.regulation_mode = "PWM"
        else:
            self.limits = {
                "min": self.settings.climateSettings.temperatureLimits.minUserInputTemperature,
                "max": self.settings.climateSettings.temperatureLimits.maxUserInputTemperature,
            }

    def _parse_state(self, state: int, payload: list[int]):

        data = (state << 16) | (payload[0] << 8) | payload[1]

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
        heating = None
        if len(payload) > 2:
            heating = bool(payload[2] & 0x80)

        return {
            "mode": None if error else mode,
            "target": target - 10,
            "current": current - 10,
            "heating": heating,
        }

    async def parse_lightlevel(self, level: LightLevel):
        if self.regulation_mode == "PWM":
            return
        state = self._state

        state.update(self._parse_state(level.state, level.payload))

        for listener in self._listeners:
            listener(self._state)

    async def parse_lastdata(self, data):
        state = self._state
        match data.command:
            case (
                LastData.CMD_OUTPUT_STATE_AND_LEVEL
                | LastData.CMD_GROUP_OUTPUT_STATE_AND_LEVEL
            ):
                state.update(self._parse_state(data.payload[0], data.payload[1:]))
            case LastData.CMD_TRM_TEMPERATURE_REGULATING_SETPOINT:
                state["target"] = int.from_bytes(data.payload[5:7], byteorder="little")
            case LastData.CMD_TRM_PWM_DUTY:
                state["target"] = int(data.payload[5])

        for listener in self._listeners:
            listener(self._state)

    async def set_target_temp(self, temp):
        if self.regulation_mode == "PWM":
            await self._mesh.write(
                LastData(
                    address=self.address,
                    command=LastData.CMD_TRM_PWM_DUTY,
                    payload=[temp & 0xFF],
                )
            )
        else:
            temp = int(temp) * 10
            await self._mesh.write(
                LastData(
                    address=self.address,
                    command=LastData.CMD_TRM_TEMPERATURE_REGULATING_SETPOINT,
                    payload=[temp & 0xFF, (temp >> 8) & 0xFF],
                ).hex
            )

    async def turn_on(self):
        await self._mesh.write(
            LastData(
                address=self.address,
                command=LastData.CMD_TRM_OPERATING_MODE,
                payload=[PlejdThermostat.MODE_NORMAL],
            ).hex
        )

    async def turn_off(self):
        await self._mesh.write(
            LastData(
                address=self.address,
                command=LastData.CMD_TRM_OPERATING_MODE,
                payload=[PlejdThermostat.MODE_SERVICE],
            ).hex
        )

    async def set_mode(self, mode=None):
        if self.regulation_mode == "PWM":
            return
        if mode is None:
            await self._mesh.write(
                LastData(
                    address=self.address,
                    command=LastData.CMD_TRM_OPERATING_MODE,
                    payload=[PlejdThermostat.MODE_NORMAL],
                ).hex
            )
        else:
            await self._mesh.write(
                LastData(
                    address=self.address,
                    command=LastData.CMD_TRM_OPERATING_MODE,
                    payload=[mode],
                ).hex
            )

    @property
    def preset(self):
        return self._state.get("mode", None)
