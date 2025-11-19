import time
import asyncio
import logging

from .plejd_device import PlejdOutput, PlejdDeviceType

_LOGGER = logging.getLogger(__name__)


STALE_SETPOINT_THRESHOLD = 2.0  # Degrees Celsius difference to treat readback as stale
STALE_SETPOINT_RECENT_WRITE_TIME = 3.0  # Seconds after write to use stricter threshold
STALE_SETPOINT_RECENT_WRITE_DIFF = 0.5  # Stricter threshold (degrees C) for readbacks after recent write

# Task scheduling delays (seconds)
SETPOINT_READ_DELAY = 1.0  # Delay before requesting setpoint read
LIMIT_READ_DELAY = 0.5  # Delay before requesting limit read

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
TRIGGER_DEVICE_AVAILABLE = "device_available"


class PlejdClimate(PlejdOutput):
    """Represents a Plejd thermostat/climate control device.
    
    Handles temperature setpoint, current temperature, HVAC mode, and temperature limits.
    Manages background tasks for reading device state and prevents stale data from overwriting
    recent writes.
    """

    def __init__(self, *args, **kwargs):
        """Initialize the PlejdClimate device.
        
        Sets up device type, internal state tracking, and background task management.
        """
        super().__init__(*args, **kwargs)
        self.outputType = PlejdDeviceType.CLIMATE
        self._setpoint_read_in_progress = False
        self._setpoint_read_task = None
        self._max_temp_read_task = None
        self._floor_min_temp = None
        self._floor_max_temp = None
        self._room_max_temp = None
        self._was_available = False  # Track previous availability state to detect transitions
        self._last_setpoint_write_time = 0.0  # Track when setpoint was last written to reject stale readbacks

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
        
        return False

    def _maybe_schedule_setpoint_read(self, reason: str):
        """Schedule a setpoint read task if not already in progress.
        
        Args:
            reason: Reason for the read (e.g., "device_available") for logging purposes
        """
        if not self._mesh:
            return

        # Check if task is already running (consistent with _maybe_schedule_limit_read)
        if self._setpoint_read_task and not self._setpoint_read_task.done():
            return

        self._setpoint_read_in_progress = True

        # Use a list to hold task reference that can be updated after closure creation
        task_container = [None]

        async def do_read():
            try:
                await asyncio.sleep(SETPOINT_READ_DELAY)
                # Check if task was cancelled or device is no longer valid
                if not self._mesh:
                    return
                _LOGGER.debug(f"PlejdClimate: Requesting setpoint read ({reason})")
                await self._mesh.read_setpoint(self.address)
            except asyncio.CancelledError:
                _LOGGER.debug(f"PlejdClimate: Setpoint read task cancelled ({reason})")
                raise
            except Exception as e:
                _LOGGER.warning(f"PlejdClimate: Error in setpoint read task: {e}")
            finally:
                # Only reset if this task is still the current one (prevents race condition)
                # This prevents a cancelled task from resetting state after a new task has started
                if self._setpoint_read_task is task_container[0]:
                    self._setpoint_read_in_progress = False
                    self._setpoint_read_task = None

        task = asyncio.create_task(do_read())
        task_container[0] = task
        self._setpoint_read_task = task

    def update_state(self, **state):
        """Update device state from incoming BLE messages.
        
        Processes setpoint updates (with stale readback detection), temperature updates,
        mode updates, and limit updates. Handles availability transitions to trigger
        initialization reads. Filters out stale setpoint readbacks that might overwrite
        recently written values.
        
        Args:
            **state: Dictionary containing device state updates (setpoint, temperature,
                    mode, limits, available, etc.)
        """
        _LOGGER.debug(f"PlejdClimate.update_state() received: {state}")
        
        state = dict(state)
        
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
                now = time.monotonic()
                time_since_write = now - self._last_setpoint_write_time
                
                # If we recently wrote a setpoint (within STALE_SETPOINT_RECENT_WRITE_TIME), be more strict about rejecting readbacks
                # This prevents readbacks from overwriting values we just set
                if cached_setpoint is not None:
                    diff = abs(setpoint_value - cached_setpoint)
                    # Use >= instead of > to catch edge cases, and be stricter if we just wrote
                    threshold = STALE_SETPOINT_THRESHOLD if time_since_write > STALE_SETPOINT_RECENT_WRITE_TIME else STALE_SETPOINT_RECENT_WRITE_DIFF
                    
                    if diff >= threshold:
                        _LOGGER.warning(
                            f"PlejdClimate: Ignoring stale readback: {setpoint_value}°C "
                            f"(cached: {cached_setpoint}°C, diff: {diff:.1f}°C, "
                            f"time_since_write: {time_since_write:.1f}s)"
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
        
        # Handle status messages (0x98 pattern)
        # Status messages contain "temperature" (current) field from status2 byte
        if STATE_KEY_TEMPERATURE in state:
            state[STATE_KEY_CURRENT_TEMPERATURE] = state[STATE_KEY_TEMPERATURE]
            _LOGGER.debug(f"PlejdClimate: Processing status message, current={state[STATE_KEY_CURRENT_TEMPERATURE]}")
            # Don't trigger setpoint reads on temperature updates - temperature changes frequently
            # Setpoint only changes when user sets it or device initializes

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

        # Check for availability transition (False → True) to trigger initialization reads
        current_available = state.get(STATE_KEY_AVAILABLE, self._was_available)
        availability_transition = current_available and not self._was_available
        
        if current_available:
            # Schedule limit reads if missing (keeps retrying until all limits received)
            if not self._has_all_limits():
                self._maybe_schedule_limit_read()
        else:
            # Device became unavailable - cancel all background tasks
            self._cancel_all_tasks()
        
        # Update availability tracking
        self._was_available = current_available
        
        _LOGGER.debug(f"PlejdClimate.update_state() calling parent with: {state}")
        
        # Call parent to update state and notify listeners
        super().update_state(**state)

        # Only schedule setpoint read on device availability transition (initialization)
        if availability_transition:
            self._maybe_schedule_setpoint_read(TRIGGER_DEVICE_AVAILABLE)

    def parse_state(self, update, state):
        """Parse and format device state for external consumption.
        
        Converts internal state keys to standardized format expected by consumers
        (e.g., Home Assistant). Maps temperature limits from internal storage to
        parsed state dictionary.
        
        Args:
            update: New state update dictionary
            state: Accumulated state dictionary (already merged with update)
        
        Returns:
            dict: Parsed state with standardized keys (available, mode, current_temperature,
                  setpoint, max_temp, floor_min_temp, floor_max_temp, room_max_temp)
        """
        available = state.get(STATE_KEY_AVAILABLE, False)
                
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
        """Set the target temperature (setpoint) for the thermostat.
        
        Sends the setpoint command to the device via BLE. The device will confirm
        the write via write_ack or push_5c notification, which will update the
        local state. Tracks write time to reject stale readbacks.
        
        Args:
            setpoint: Target temperature in degrees Celsius (will be rounded to nearest degree)
        """
        if not self._mesh:
            return
        
        # Send the command - device will confirm via write_ack or push_5c notification
        await self._mesh.set_state(self.address, setpoint=setpoint)
        
        # Track when we wrote the setpoint to reject any stale readbacks that might come in
        # State will be updated when device confirms via write_ack or push_5c
        self._last_setpoint_write_time = time.monotonic()

    async def set_mode(self, mode: str):
        """Set thermostat HVAC mode.
        
        Accepts "off", "standby", or "heat" (case-insensitive). If the device
        is already in the requested mode, no command is sent.
        
        Args:
            mode: HVAC mode string ("off", "standby", or "heat")
        """
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
        """Turn off the thermostat (set mode to OFF).
        
        Convenience method that sets the HVAC mode to "off".
        """
        if not self._mesh:
            return
        await self.set_mode(MODE_OFF)

    async def turn_on(self):
        """Turn on the thermostat (set mode to HEAT).
        
        Convenience method that sets the HVAC mode to "heat".
        """
        if not self._mesh:
            return
        await self.set_mode(MODE_HEAT)

    def _maybe_schedule_limit_read(self):
        """Schedule a limit read task if not already in progress and limits are missing.
        
        Reads thermostat temperature limits (floor min/max, room max, max temperature)
        from the device. Only schedules if limits are not already known.
        """
        # Check if task is already running (not just if it exists)
        if self._max_temp_read_task and not self._max_temp_read_task.done():
            return

        if not self._mesh:
            return

        if self._has_all_limits():
            return
            
        async def do_read():
            try:
                await asyncio.sleep(LIMIT_READ_DELAY)
                # Check if task was cancelled or device is no longer valid
                if not self._mesh:
                    return
                _LOGGER.debug("PlejdClimate: Requesting thermostat limits read")
                await self._mesh.read_thermostat_limits(self.address)
            except asyncio.CancelledError:
                _LOGGER.debug("PlejdClimate: Limit read task cancelled")
                raise
            except Exception as e:
                _LOGGER.warning(f"PlejdClimate: Error in limit read task: {e}")
            finally:
                self._max_temp_read_task = None

        self._max_temp_read_task = asyncio.create_task(do_read())

    def _has_all_limits(self):
        """Check if all required thermostat temperature limits have been received.
        
        Returns:
            bool: True if all limits (max_temperature, floor_min_temp, 
                  floor_max_temp, room_max_temp) are known, False otherwise
        """
        return (
            self._state.get(STATE_KEY_MAX_TEMPERATURE) is not None
            and self._floor_min_temp is not None
            and self._floor_max_temp is not None
            and self._room_max_temp is not None
        )

    def _cancel_all_tasks(self):
        """Cancel all running background tasks to prevent them from outliving the device instance."""
        tasks_cancelled = 0
        
        if self._setpoint_read_task and not self._setpoint_read_task.done():
            self._setpoint_read_task.cancel()
            tasks_cancelled += 1
            _LOGGER.debug("PlejdClimate: Cancelled setpoint read task")
        
        if self._max_temp_read_task and not self._max_temp_read_task.done():
            self._max_temp_read_task.cancel()
            tasks_cancelled += 1
            _LOGGER.debug("PlejdClimate: Cancelled limit read task")
        
        if tasks_cancelled > 0:
            _LOGGER.debug(f"PlejdClimate: Cancelled {tasks_cancelled} background task(s)")
        
        # Reset task references
        self._setpoint_read_task = None
        self._max_temp_read_task = None
        self._setpoint_read_in_progress = False

