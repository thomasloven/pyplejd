from .debug import rec_log


def parse_poll(data: bytearray, device_types: dict | None = None):
    """Parse poll responses from Plejd mesh.
    
    This parses responses from the PLEJD_POLL characteristic 
    All device types respond to poll requests with a 10-byte status packet.
    
    Args:
        data: Raw poll response data (multiple 10-byte packets)
        device_types: Optional dict mapping address to device type string
    """
    if device_types is None:
        device_types = {}

    for i in range(0, len(data), 10):
        ll = data[i : i + 10]

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
            # temp = (dim & 0x3F) - 10
            temperature = (dim & 0x3F) - 10
            
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
