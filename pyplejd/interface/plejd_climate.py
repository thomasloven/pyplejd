import time
import asyncio
import logging

from .plejd_device import PlejdOutput, PlejdDeviceType

_LOGGER = logging.getLogger(__name__)


SETPOINT_REFRESH_INTERVAL = 1  # Minimum seconds between automatic setpoint read requests
STALE_SETPOINT_THRESHOLD = 2.0  # Degrees Celsius difference to treat readback as stale


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
            'mode',
            'temperature',
            'setpoint',
            'heating',
            'floor_min_temperature',
            'floor_max_temperature',
            'room_max_temperature',
            'max_temperature',
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
        if "setpoint" in state:
            msg_type = state.get("msg_type")
            setpoint_value = state["setpoint"]
            source = "unknown"
            should_process_setpoint = True
            
            if msg_type == "write_ack":
                source = "write_ack"
            elif msg_type == "push_5c":
                source = "push_5c"
            elif msg_type == "read_01_02":
                source = "read_01_02_pattern"
                # Check if readback is close to cached value (within threshold)
                # This prevents old readback values from overwriting newly set values
                cached_setpoint = self._state.get("setpoint")
                if cached_setpoint is not None:
                    diff = abs(setpoint_value - cached_setpoint)
                    if diff > STALE_SETPOINT_THRESHOLD:
                        _LOGGER.warning(
                            f"PlejdClimate: Ignoring stale readback: {setpoint_value}°C "
                            f"(cached: {cached_setpoint}°C, diff: {diff:.1f}°C)"
                        )
                        # Remove setpoint from state so it doesn't overwrite cached value
                        state.pop("setpoint", None)
                        state.pop("msg_type", None)
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
        if "temperature" in state:
            state["current_temperature"] = state["temperature"]
            _LOGGER.debug(f"PlejdClimate: Processing status message, current={state['current_temperature']}")
            trigger_reason = trigger_reason or "temperature_update"

        if "max_temperature" in state:
            max_temp_value = state["max_temperature"]
            _LOGGER.debug(f"PlejdClimate: Received max_temperature={max_temp_value}°C (msg_type={state.get('msg_type')})")

        if "floor_min_temperature" in state:
            self._floor_min_temp = state["floor_min_temperature"]
            state["floor_min_temp"] = self._floor_min_temp
        if "floor_max_temperature" in state:
            self._floor_max_temp = state["floor_max_temperature"]
            state["floor_max_temp"] = self._floor_max_temp
        if "room_max_temperature" in state:
            self._room_max_temp = state["room_max_temperature"]
            state["room_max_temp"] = self._room_max_temp

        if state.get("available"):
            trigger_reason = trigger_reason or "device_available"
        self._maybe_schedule_limit_read()
        
        _LOGGER.debug(f"PlejdClimate.update_state() calling parent with: {state}")
        
        # Call parent to update state and notify listeners
        super().update_state(**state)

        if trigger_reason:
            self._maybe_schedule_setpoint_read(trigger_reason)
        else:
            # Ensure we still fetch max temperature even if no trigger reason set yet
            if not self._state.get("max_temperature"):
                self._maybe_schedule_limit_read()
            elif not self._has_all_limits():
                self._maybe_schedule_limit_read()

    def parse_state(self, update, state):
        available = state.get("available", False)
        
        # Note: 'update' is the new update, 'state' is the accumulated state (already merged)
        # Temperature and setpoint are now stored separately in state
        
        parsed = {
            "available": available,
            "mode": state.get("mode", "off"),  # Default to "off" if not set
        }
        
        # Get current temperature - always use "current_temperature" key
        if "current_temperature" in state:
            parsed["current_temperature"] = state["current_temperature"]

        # Get setpoint temperature
        if "setpoint" in state:
            parsed["setpoint"] = state["setpoint"]

        if "max_temperature" in state:
            parsed["max_temp"] = state["max_temperature"]

        if self._floor_min_temp is not None:
            parsed["floor_min_temp"] = self._floor_min_temp
        if self._floor_max_temp is not None:
            parsed["floor_max_temp"] = self._floor_max_temp
        if self._room_max_temp is not None:
            parsed["room_max_temp"] = self._room_max_temp
        
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
        if sent_values and "setpoint" in sent_values:
            self.update_state(setpoint=sent_values["setpoint"])
        
        self._maybe_schedule_setpoint_read("post_set_temperature", force=True)

    async def set_mode(self, mode: str):
        """Set thermostat HVAC mode ("off" or "heat")."""
        if not self._mesh:
            return

        normalized = mode.lower()
        if normalized in ("off", "standby"):
            target = "off"
            payload_mode = "off"
        else:
            target = "heating"
            payload_mode = "heat"

        current = self._state.get("mode")
        if current == target:
            return

        await self._mesh.set_state(self.address, thermostat_mode=payload_mode)

    async def turn_off(self):
        if not self._mesh:
            return
        await self.set_mode("off")

    async def turn_on(self):
        if not self._mesh:
            return
        await self.set_mode("heat")

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
            self._state.get("max_temperature") is not None
            and self._floor_min_temp is not None
            and self._floor_max_temp is not None
            and self._room_max_temp is not None
        )

