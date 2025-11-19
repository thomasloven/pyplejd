import time
import asyncio
import logging

from .plejd_device import PlejdOutput, PlejdDeviceType

_LOGGER = logging.getLogger(__name__)


# Task scheduling delays (seconds)
SETPOINT_READ_DELAY = 1.0  # Delay before requesting setpoint read
SETPOINT_READ_AFTER_WRITE_DELAY = 0.3  # Delay after 0x98 status before reading setpoint after write
LIMIT_READ_DELAY = 0.5  # Delay before requesting limit read
WRITE_CONFIRMATION_WINDOW = 2.0  # Seconds after write to consider 0x98 as write confirmation

# State keys
STATE_KEY_SETPOINT = "setpoint"
STATE_KEY_TEMPERATURE = "temperature"
STATE_KEY_CURRENT_TEMPERATURE = "current_temperature"
STATE_KEY_MODE = "mode"
STATE_KEY_HEATING = "heating"
STATE_KEY_FLOOR_MIN_TEMPERATURE = "floor_min_temperature"
STATE_KEY_FLOOR_MAX_TEMPERATURE = "floor_max_temperature"
STATE_KEY_ROOM_MAX_TEMPERATURE = "room_max_temperature"
STATE_KEY_AVAILABLE = "available"
STATE_KEY_MSG_TYPE = "msg_type"
STATE_KEY_FLOOR_MIN_TEMP = "floor_min_temp"
STATE_KEY_FLOOR_MAX_TEMP = "floor_max_temp"
STATE_KEY_ROOM_MAX_TEMP = "room_max_temp"

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
TRIGGER_AFTER_WRITE = "after_write"


class PlejdClimate(PlejdOutput):
    """Represents a Plejd thermostat/climate control device.
    
    Handles temperature setpoint, current temperature, HVAC mode, and temperature limits.
    Manages background tasks for reading device state.
    """

    def __init__(self, *args, **kwargs):
        """Initialize the PlejdClimate device.
        
        Sets up device type, internal state tracking, and background task management.
        """
        super().__init__(*args, **kwargs)
        self.outputType = PlejdDeviceType.CLIMATE
        self._setpoint_read_task = None
        self._max_temp_read_task = None
        self._floor_min_temp = None
        self._floor_max_temp = None
        self._room_max_temp = None
        self._was_available = False  # Track previous availability state to detect transitions
        self._last_setpoint_write_time = 0.0  # Track when setpoint was last written to detect 0x98 write confirmations

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

        # Use a list to hold task reference that can be updated after closure creation
        task_container = [None]

        async def do_read():
            try:
                # Use shorter delay for reads after writes (we already got 0x98 confirmation)
                delay = SETPOINT_READ_AFTER_WRITE_DELAY if reason == TRIGGER_AFTER_WRITE else SETPOINT_READ_DELAY
                await asyncio.sleep(delay)
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
                    self._setpoint_read_task = None

        task = asyncio.create_task(do_read())
        task_container[0] = task
        self._setpoint_read_task = task

    def update_state(self, **state):
        """Update device state from incoming BLE messages.
        
        Processes setpoint updates, temperature updates, mode updates, and limit updates.
        Handles availability transitions to trigger initialization reads. Schedules
        setpoint reads after writes when 0x98 status messages are received.
        
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
            
            if msg_type == MSG_TYPE_WRITE_ACK:
                source = MSG_TYPE_WRITE_ACK
            elif msg_type == MSG_TYPE_PUSH_5C:
                source = MSG_TYPE_PUSH_5C
            elif msg_type == MSG_TYPE_READ_01_02:
                source = MSG_TYPE_READ_01_02_PATTERN
                _LOGGER.debug(f"PlejdClimate: Got setpoint via 01 02 pattern: {setpoint_value}°C")
            
            _LOGGER.debug(f"PlejdClimate: Processing setpoint={setpoint_value}°C (source={source})")
            # Setpoint is already in state, will be passed to parent
            # This overrides any cached setpoint with device-confirmed value
        
        # Handle status messages (0x98 pattern)
        # Status messages contain "temperature" (current) field from status2 byte
        if STATE_KEY_TEMPERATURE in state:
            state[STATE_KEY_CURRENT_TEMPERATURE] = state[STATE_KEY_TEMPERATURE]
            _LOGGER.debug(f"PlejdClimate: Processing status message, current={state[STATE_KEY_CURRENT_TEMPERATURE]}")
            
            # If we recently wrote a setpoint, this 0x98 message is likely the write confirmation
            # Schedule a read to get the device-confirmed setpoint value
            now = time.monotonic()
            time_since_write = now - self._last_setpoint_write_time
            if time_since_write < WRITE_CONFIRMATION_WINDOW and self._last_setpoint_write_time > 0:
                _LOGGER.debug(f"PlejdClimate: Received 0x98 status after setpoint write ({time_since_write:.2f}s ago), scheduling setpoint read")
                self._maybe_schedule_setpoint_read(TRIGGER_AFTER_WRITE)

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

        if self._floor_min_temp is not None:
            parsed[STATE_KEY_FLOOR_MIN_TEMP] = self._floor_min_temp
        if self._floor_max_temp is not None:
            parsed[STATE_KEY_FLOOR_MAX_TEMP] = self._floor_max_temp
        if self._room_max_temp is not None:
            parsed[STATE_KEY_ROOM_MAX_TEMP] = self._room_max_temp
        
        return parsed

    async def set_temperature(self, setpoint: float):
        """Set the target temperature (setpoint) for the thermostat.
        
        Sends the setpoint command to the device via BLE. Updates the local state
        immediately to ensure cache coherency when the device sends intermediate
        status updates (0x98) before the final setpoint confirmation (01 03).
        
        Args:
            setpoint: Target temperature in degrees Celsius (will be rounded to nearest degree)
        """
        if not self._mesh:
            return
        
        # Send the command - device will respond with 0x98 status, then we'll read the setpoint
        await self._mesh.set_state(self.address, setpoint=setpoint)
        
        # Optimistically update local state cache.
        # This prevents the subsequent 0x98 status message (which lacks setpoint data)
        # from broadcasting the old setpoint value to listeners, causing a UI glitch.
        # The value will be verified/overwritten when the readback confirmation arrives.
        self.update_state(**{STATE_KEY_SETPOINT: setpoint})
        
        # Track when we wrote the setpoint to detect 0x98 write confirmations
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
            bool: True if all limits (floor_min_temp, floor_max_temp, 
                  room_max_temp) are known, False otherwise
        """
        return (
            self._floor_min_temp is not None
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

