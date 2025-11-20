from .debug import rec_log
from .parse_data import THERMOSTAT_TEMP_MASK
from ..interface.device_type import PlejdDeviceType



def _parse_poll_climate(address, state, ll, raw_hex):
    """Parse poll response for climate/thermostat devices.
    
    Returns dict with temperature data.
    """
    temp_byte = int(ll[6])
    temperature = (temp_byte & THERMOSTAT_TEMP_MASK) - 10
    
    rec_log(f"CLIMATE POLL {state=} temp_byte={temp_byte} temperature={temperature}°C", address)
    return {
        "address": address,
        "state": state,
        "temperature": temperature,
    }


def _parse_poll_cover(address, state, ll, raw_hex):
    """Parse poll response for cover devices.
    
    Returns dict with cover position.
    """
    cover_position = int.from_bytes(ll[5:7], "little")
    rec_log(f"COVER POLL {state=} {cover_position=}", address)
    return {
        "address": address,
        "state": state,
        "cover_position": cover_position,
    }


def _parse_poll_light(address, state, ll, raw_hex, device_type):
    """Parse poll response for light/switch devices.
    
    Returns dict with dim level.
    """
    dim = int(ll[6])
    rec_log(f"{device_type} POLL {state=} {dim=}", address)
    return {
        "address": address,
        "state": state,
        "dim": dim,
    }


def _parse_poll_unknown(address, state, ll, raw_hex):
    """Parse poll response for unknown device types.
    
    Returns dict with raw byte data for debugging.
    """
    dim = int(ll[6])
    cover_position = int.from_bytes(ll[5:7], "little")
    rec_log(f"POLL {state=} byte_6={dim} bytes_5_7={cover_position}", address)
    return {
        "address": address,
        "state": state,
        "dim": dim,
        "cover_position": cover_position,  # Include for unknown devices to aid debugging
    }


# Dispatch table for poll response handlers
# Maps device type to appropriate parsing function
_POLL_HANDLERS = {
    PlejdDeviceType.CLIMATE: _parse_poll_climate,
    PlejdDeviceType.COVER: _parse_poll_cover,
    PlejdDeviceType.LIGHT: _parse_poll_light,
    PlejdDeviceType.SWITCH: _parse_poll_light,  # Switch shares handler with Light
}

# ============================================================================


def parse_poll(data: bytearray, device_types: dict | None = None):
    """Parse poll responses from Plejd mesh.
    
    This parses responses from the PLEJD_POLL characteristic 
    All device types respond to poll requests with a 10-byte status packet.
    
    Args:
        data: Raw poll response data (multiple 10-byte packets)
        device_types: Optional dict mapping address (int) to device type (PlejdDeviceType enum)
    
    Yields:
        dict: Parsed device state with address, state, and device-specific fields
    """
    if device_types is None:
        device_types = {}
    
    # Validate data length is a multiple of 10
    if len(data) % 10 != 0:
        rec_log(f"WARNING: Poll data length ({len(data)}) is not a multiple of 10, truncating incomplete packet")
        # Truncate to nearest multiple of 10
        data = data[:len(data) - (len(data) % 10)]
    
    # Validate device_types format if provided
    if device_types:
        for addr, dev_type in device_types.items():
            if not isinstance(addr, int):
                rec_log(f"WARNING: device_types key {addr} is not an integer, skipping validation")
                continue
            # Note: dev_type should be PlejdDeviceType enum, but we allow any value
            # The comparison logic in the code handles unknown types gracefully

    for i in range(0, len(data), 10):
        ll = data[i : i + 10]
        
        # Safety check: ensure we have exactly 10 bytes
        if len(ll) < 10:
            rec_log(f"WARNING: Incomplete poll packet at offset {i}, expected 10 bytes, got {len(ll)}")
            break

        address = int(ll[0])
        state = bool(ll[1])

        # Log full raw hex data for analysis
        raw_hex = "".join(f"{b:02x}" for b in ll)
        rec_log(f"POLL RAW addr={address} bytes=[{ll[0]:02x} {ll[1]:02x} {ll[2]:02x} {ll[3]:02x} {ll[4]:02x} {ll[5]:02x} {ll[6]:02x} {ll[7]:02x} {ll[8]:02x} {ll[9]:02x}] hex={raw_hex}", address)

        # Determine device type and dispatch to appropriate handler
        device_type = device_types.get(address, PlejdDeviceType.UNKNOWN)
        handler = _POLL_HANDLERS.get(device_type, _parse_poll_unknown)
        
        # Call handler with device_type if it's light/switch (needs it for logging)
        if device_type in (PlejdDeviceType.LIGHT, PlejdDeviceType.SWITCH):
            yield handler(address, state, ll, raw_hex, device_type)
        else:
            yield handler(address, state, ll, raw_hex)
