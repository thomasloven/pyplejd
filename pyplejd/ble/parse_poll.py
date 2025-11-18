from .debug import rec_log
from .parse_data import THERMOSTAT_TEMP_MASK


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
        dim = int(ll[6])
        cover_position = int.from_bytes(ll[5:7], "little")

        # Log full raw hex data for analysis
        raw_hex = "".join(f"{b:02x}" for b in ll)
        rec_log(f"POLL RAW addr={address} bytes=[{ll[0]:02x} {ll[1]:02x} {ll[2]:02x} {ll[3]:02x} {ll[4]:02x} {ll[5]:02x} {ll[6]:02x} {ll[7]:02x} {ll[8]:02x} {ll[9]:02x}] hex={raw_hex}", address)

        # Determine device type for proper logging and response structure
        device_type = device_types.get(address, "UNKNOWN")
        
        # Generate device-type-specific log message and yield appropriate data
        if device_type == "CLIMATE":
            # For climate devices, apply modulo-64 temperature decoding:
            # temp = (dim & THERMOSTAT_TEMP_MASK) - 10
            temperature = (dim & THERMOSTAT_TEMP_MASK) - 10
            
            rec_log(f"CLIMATE POLL {state=} temp_byte={dim} temperature={temperature}°C", address)
            yield {
                "address": address,
                "state": state,
                "temperature": temperature,
            }
        elif device_type == "COVER":
            rec_log(f"COVER POLL {state=} {cover_position=}", address)
            yield {
                "address": address,
                "state": state,
                "cover_position": cover_position,
            }
        elif device_type == "LIGHT" or device_type == "SWITCH":
            rec_log(f"{device_type} POLL {state=} {dim=}", address)
            yield {
                "address": address,
                "state": state,
                "dim": dim,
            }
        else:
            # Unknown or untyped device - yield all fields for debugging
            rec_log(f"POLL {state=} {dim=} {cover_position=}", address)
            yield {
                "address": address,
                "state": state,
                "dim": dim,
                "cover_position": cover_position,
            }
