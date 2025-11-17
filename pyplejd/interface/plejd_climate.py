import time
import asyncio
import logging

from .plejd_device import PlejdOutput, PlejdDeviceType

_LOGGER = logging.getLogger(__name__)


SETPOINT_REFRESH_INTERVAL = 1  # Minimum seconds between automatic setpoint read requests
STALE_SETPOINT_THRESHOLD = 2.0  # Degrees Celsius difference to treat readback as stale

# State keys
STATE_KEY_SETPOINT = "setpoint"
STATE_KEY_TEMPERATURE = "temperature"
STATE_KEY_CURRENT_TEMPERATURE = "current_temperature"
STATE_KEY_MODE = "mode"
STATE_KEY_HEATING = "heating"
STATE_KEY_FLOOR_MIN_TEMPERATURE = "floor_min_temperature"
STATE_KEY_FLOOR_MAX_TEMPERATURE = "floor_max_temperature"
STATE_KEY_ROOM_MAX_TEMPERATURE = "room_max_temperature"
STATE_KEY_MAX_TEMPERATURE = "max_temperature"
STATE_KEY_AVAILABLE = "available"
STATE_KEY_MSG_TYPE = "msg_type"
STATE_KEY_FLOOR_MIN_TEMP = "floor_min_temp"
STATE_KEY_FLOOR_MAX_TEMP = "floor_max_temp"
STATE_KEY_ROOM_MAX_TEMP = "room_max_temp"
STATE_KEY_MAX_TEMP = "max_temp"

# Message types
MSG_TYPE_WRITE_ACK = "write_ack"
MSG_TYPE_PUSH_5C = "push_5c"
MSG_TYPE_READ_01_02 = "read_01_02"
MSG_TYPE_READ_01_02_PATTERN = "read_01_02_pattern"
MSG_TYPE_UNKNOWN = "unknown"

# Mode values
MODE_OFF = "off"
MODE_STANDBY = "standby"
MODE_HEATING = "heating"
MODE_HEAT = "heat"

# Trigger reasons
TRIGGER_TEMPERATURE_UPDATE = "temperature_update"
TRIGGER_DEVICE_AVAILABLE = "device_available"
TRIGGER_POST_SET_TEMPERATURE = "post_set_temperature"


class PlejdClimate(PlejdOutput):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outputType = PlejdDeviceType.CLIMATE
        self._setpoint_read_in_progress = False
        self._last_setpoint_refresh = 0.0
        self._setpoint_read_task = None
        self._max_temp_read_task = None
        self._floor_min_temp = None
        self._floor_max_temp = None
        self._room_max_temp = None

    def match_state(self, state):
        """
        Climate devices only respond to thermostat-specific messages.
        """
        # Climate devices respond to messages with these thermostat-specific fields
        climate_keys = {
            STATE_KEY_MODE,
            STATE_KEY_TEMPERATURE,
            STATE_KEY_SETPOINT,
            STATE_KEY_HEATING,
            STATE_KEY_FLOOR_MIN_TEMPERATURE,
            STATE_KEY_FLOOR_MAX_TEMPERATURE,
            STATE_KEY_ROOM_MAX_TEMPERATURE,
            STATE_KEY_MAX_TEMPERATURE,
        }
        if any(key in state for key in climate_keys):
            return super().match_state(state)
        
        # Ignore everything else (including LIGHTLEVEL dim/state messages)
        return False

    def _maybe_schedule_setpoint_read(self, reason: str, *, force: bool = False):
        now = time.monotonic()

        if (not force) and ((now - self._last_setpoint_refresh) < SETPOINT_REFRESH_INTERVAL):
            return

        if self._setpoint_read_in_progress or not self._mesh:
            return

        self._setpoint_read_in_progress = True

        async def do_read():
            try:
                await asyncio.sleep(1.0)
                _LOGGER.debug(f"PlejdClimate: Requesting setpoint read ({reason})")
                await self._mesh.read_setpoint(self.address)
            finally:
                self._setpoint_read_in_progress = False
                self._setpoint_read_task = None

        task = asyncio.create_task(do_read())
        self._setpoint_read_task = task

    def update_state(self, **state):
        
        _LOGGER.debug(f"PlejdClimate.update_state() received: {state}")
        
        state = dict(state)
        trigger_reason = None
        
        # Handle setpoint from 0x5c messages
        if STATE_KEY_SETPOINT in state:
            msg_type = state.get(STATE_KEY_MSG_TYPE)
            setpoint_value = state[STATE_KEY_SETPOINT]
            source = MSG_TYPE_UNKNOWN
            should_process_setpoint = True
            
            if msg_type == MSG_TYPE_WRITE_ACK:
                source = MSG_TYPE_WRITE_ACK
            elif msg_type == MSG_TYPE_PUSH_5C:
                source = MSG_TYPE_PUSH_5C
            elif msg_type == MSG_TYPE_READ_01_02:
                source = MSG_TYPE_READ_01_02_PATTERN
                # Check if readback is close to cached value (within threshold)
                # This prevents old readback values from overwriting newly set values
                cached_setpoint = self._state.get(STATE_KEY_SETPOINT)
                if cached_setpoint is not None:
                    diff = abs(setpoint_value - cached_setpoint)
                    if diff > STALE_SETPOINT_THRESHOLD:
                        _LOGGER.warning(
                            f"PlejdClimate: Ignoring stale readback: {setpoint_value}°C "
                            f"(cached: {cached_setpoint}°C, diff: {diff:.1f}°C)"
                        )
                        # Remove setpoint from state so it doesn't overwrite cached value
                        state.pop(STATE_KEY_SETPOINT, None)
                        state.pop(STATE_KEY_MSG_TYPE, None)
                        should_process_setpoint = False
                        # Continue processing other fields, just skip this setpoint
                    else:
                        _LOGGER.debug(f"PlejdClimate: Got setpoint via 01 02 pattern: {setpoint_value}°C")
                else:
                    _LOGGER.debug(f"PlejdClimate: Got setpoint via 01 02 pattern: {setpoint_value}°C")
            
            if should_process_setpoint:
                _LOGGER.debug(f"PlejdClimate: Processing setpoint={setpoint_value}°C (source={source})")
                # Setpoint is already in state, will be passed to parent
                # This overrides any cached setpoint with device-confirmed value
                self._last_setpoint_refresh = time.monotonic()
        
        # Handle status messages (0x98 pattern)
        # Status messages contain "temperature" (current) field from status2 byte
        if STATE_KEY_TEMPERATURE in state:
            state[STATE_KEY_CURRENT_TEMPERATURE] = state[STATE_KEY_TEMPERATURE]
            _LOGGER.debug(f"PlejdClimate: Processing status message, current={state[STATE_KEY_CURRENT_TEMPERATURE]}")
            trigger_reason = trigger_reason or TRIGGER_TEMPERATURE_UPDATE

        if STATE_KEY_MAX_TEMPERATURE in state:
            max_temp_value = state[STATE_KEY_MAX_TEMPERATURE]
            _LOGGER.debug(f"PlejdClimate: Received max_temperature={max_temp_value}°C (msg_type={state.get(STATE_KEY_MSG_TYPE)})")

        if STATE_KEY_FLOOR_MIN_TEMPERATURE in state:
            self._floor_min_temp = state[STATE_KEY_FLOOR_MIN_TEMPERATURE]
            state[STATE_KEY_FLOOR_MIN_TEMP] = self._floor_min_temp
        if STATE_KEY_FLOOR_MAX_TEMPERATURE in state:
            self._floor_max_temp = state[STATE_KEY_FLOOR_MAX_TEMPERATURE]
            state[STATE_KEY_FLOOR_MAX_TEMP] = self._floor_max_temp
        if STATE_KEY_ROOM_MAX_TEMPERATURE in state:
            self._room_max_temp = state[STATE_KEY_ROOM_MAX_TEMPERATURE]
            state[STATE_KEY_ROOM_MAX_TEMP] = self._room_max_temp

        if state.get(STATE_KEY_AVAILABLE):
            trigger_reason = trigger_reason or TRIGGER_DEVICE_AVAILABLE
        self._maybe_schedule_limit_read()
        
        _LOGGER.debug(f"PlejdClimate.update_state() calling parent with: {state}")
        
        # Call parent to update state and notify listeners
        super().update_state(**state)

        if trigger_reason:
            self._maybe_schedule_setpoint_read(trigger_reason)
        else:
            # Ensure we still fetch max temperature even if no trigger reason set yet
            if not self._state.get(STATE_KEY_MAX_TEMPERATURE):
                self._maybe_schedule_limit_read()
            elif not self._has_all_limits():
                self._maybe_schedule_limit_read()

    def parse_state(self, update, state):
        available = state.get(STATE_KEY_AVAILABLE, False)
        
        # Note: 'update' is the new update, 'state' is the accumulated state (already merged)
        # Temperature and setpoint are now stored separately in state
        
        parsed = {
            STATE_KEY_AVAILABLE: available,
            STATE_KEY_MODE: state.get(STATE_KEY_MODE, MODE_OFF),  # Default to "off" if not set
        }
        
        # Get current temperature - always use "current_temperature" key
        if STATE_KEY_CURRENT_TEMPERATURE in state:
            parsed[STATE_KEY_CURRENT_TEMPERATURE] = state[STATE_KEY_CURRENT_TEMPERATURE]

        # Get setpoint temperature
        if STATE_KEY_SETPOINT in state:
            parsed[STATE_KEY_SETPOINT] = state[STATE_KEY_SETPOINT]

        if STATE_KEY_MAX_TEMPERATURE in state:
            parsed[STATE_KEY_MAX_TEMP] = state[STATE_KEY_MAX_TEMPERATURE]

        if self._floor_min_temp is not None:
            parsed[STATE_KEY_FLOOR_MIN_TEMP] = self._floor_min_temp
        if self._floor_max_temp is not None:
            parsed[STATE_KEY_FLOOR_MAX_TEMP] = self._floor_max_temp
        if self._room_max_temp is not None:
            parsed[STATE_KEY_ROOM_MAX_TEMP] = self._room_max_temp
        
        return parsed

    async def set_temperature(self, setpoint: float):
        """Set the target temperature (setpoint) for the thermostat."""
        if not self._mesh:
            return
        
        # Send the command and get back the actual value that was sent
        # The returned value is what was encoded and sent to the device
        sent_values = await self._mesh.set_state(self.address, setpoint=setpoint)
        
        # Update local state with the ACTUAL setpoint that was sent
        # This is the source of truth, not the unreliable device readback
        if sent_values and STATE_KEY_SETPOINT in sent_values:
            self.update_state(setpoint=sent_values[STATE_KEY_SETPOINT])
        
        self._maybe_schedule_setpoint_read(TRIGGER_POST_SET_TEMPERATURE, force=True)

    async def set_mode(self, mode: str):
        """Set thermostat HVAC mode ("off" or "heat")."""
        if not self._mesh:
            return

        normalized = mode.lower()
        if normalized in (MODE_OFF, MODE_STANDBY):
            target = MODE_OFF
            payload_mode = MODE_OFF
        else:
            target = MODE_HEATING
            payload_mode = MODE_HEAT

        current = self._state.get(STATE_KEY_MODE)
        if current == target:
            return

        await self._mesh.set_state(self.address, thermostat_mode=payload_mode)

    async def turn_off(self):
        if not self._mesh:
            return
        await self.set_mode(MODE_OFF)

    async def turn_on(self):
        if not self._mesh:
            return
        await self.set_mode(MODE_HEAT)

    def _maybe_schedule_limit_read(self):

        if self._max_temp_read_task or not self._mesh:
            return

        if self._has_all_limits():
            return
            
        async def do_read():
            try:
                await asyncio.sleep(0.5)
                _LOGGER.debug("PlejdClimate: Requesting thermostat limits read")
                await self._mesh.read_thermostat_limits(self.address)
            finally:
                self._max_temp_read_task = None

        self._max_temp_read_task = asyncio.create_task(do_read())

    def _has_all_limits(self):
        return (
            self._state.get(STATE_KEY_MAX_TEMPERATURE) is not None
            and self._floor_min_temp is not None
            and self._floor_max_temp is not None
            and self._room_max_temp is not None
        )

