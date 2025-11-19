from .debug import rec_log

THERMOSTAT_TEMP_MASK = 0x3F  # Lower six bits carry temperature information in status2


def parse_data(data: bytearray, device_types: dict | None = None):
    """Parse incoming BLE data messages from Plejd mesh.
    
    Args:
        data: Raw BLE data bytearray
        device_types: Optional dict mapping address (int) to device type (PlejdDeviceType enum)
    
    Returns:
        dict | None: Parsed device state dict if message was recognized, None otherwise
    """
    # Validate device_types format if provided
    if device_types is not None:
        if not isinstance(device_types, dict):
            rec_log(f"WARNING: device_types must be a dict, got {type(device_types).__name__}")
            device_types = None
        else:
            for addr, dev_type in device_types.items():
                if not isinstance(addr, int):
                    rec_log(f"WARNING: device_types key {addr} (type {type(addr).__name__}) is not an integer")
                # Note: dev_type should be PlejdDeviceType enum, but we allow any value
                # The comparison logic in the code handles unknown types gracefully
    
    if device_types is None:
        device_types = {}
    
    data_bytes = [data[i] for i in range(0, len(data))]
    data_hex = "".join(f"{b:02x}" for b in data_bytes)

    rec_log(f"FULL DATA {data_hex}")

    match data_bytes:
        case [0x01, 0x01, 0x10, *extra]:
            # Time data
            rec_log(f"TIME DATA {extra}", "TME")
            rec_log(f"    {data_hex}", "TME")

        case [0x02, 0x01, 0x10, 0x00, 0x21, scene, *extra]:
            # Scene update
            rec_log(f"SCENE UPDATE {scene=} {extra=}", "SCN")
            rec_log(f"    {data_hex}", "SCN")
            return {
                "scene": scene,
                "triggered": True,
            }

        case [0x00, 0x01, 0x10, 0x00, 0x21, scene, *extra]:
            # Scene triggered
            rec_log(f"SCENE TRIGGER {scene=} {extra=}", "SCN")
            rec_log(f"    {data_hex}", "SCN")
            return {
                "scene": scene,
                "triggered": True,
            }

        case [0x00, 0x01, 0x10, 0x00, 0x15, *extra]:
            # Identify buttons command
            rec_log(f"IDENTIFY BUTTON REQUEST {extra=}")
            rec_log(f"    {data_hex}")

        case [0x00, 0x01, 0x10, 0x00, 0x16, addr, button, *extra]:
            # Button pressed
            rec_log(f"BUTTON {button=} {extra=}", addr)
            rec_log(f"    {data_hex}", addr)
            return {
                "address": addr,
                "button": button,
                "action": "release" if len(extra) and not extra[0] else "press",
            }

        case [addr, 0x01, 0x10, 0x00, 0x98, state, status1, status2, *extra]:
            # 0x98 is used by multiple device types
            device_type = (device_types or {}).get(addr, "UNKNOWN")
            if device_type == "CLIMATE":
                # Thermostat status response
                # Format: AA 01 10 00 98 [state] [status1] [status2] [heating]
                extra_hex = "".join(f"{e:02x}" for e in extra)
                heating = extra[0] == 0x80 if extra else None

                # Temperature decoding via modulo-64 rule: lower six bits minus 10 degrees offset
                temp_raw = status2 & THERMOSTAT_TEMP_MASK
                current_temperature = temp_raw - 10
                # Mode: off takes precedence when state==0; otherwise derive from heating flag
                hvac_mode = "off" if not state else ("heating" if heating else "idle")

                temp_str = f"{current_temperature}°C" if current_temperature is not None else "None (invalid)"
                rec_log(
                    f"THERMOSTAT STATUS state={state} status1={status1} status2={status2} current={temp_str} mode={hvac_mode} heating={heating}",
                    addr,
                )
                rec_log(f"    {data_hex}", addr)
                result = {
                    "address": addr,
                    "state": state,
                    "status1": status1,
                    "status2": status2,
                    "heating": heating,
                    "mode": hvac_mode,
                }
                if current_temperature is not None:
                    result["temperature"] = current_temperature
                rec_log(f"THERMOSTAT STATUS RETURNING: {result}", addr)
                return result
            else:
                # Non-climate: treat as dim/cover style response
                extra_hex = "".join(f"{e:02x}" for e in extra)
                dim = status2
                cover_position = int.from_bytes([status1, status2], byteorder="little", signed=True)
                rec_log(f"DIM/STATE state={state} dim={dim} cover_position={cover_position} extra={extra_hex}", addr)
                rec_log(f"    {data_hex}", addr)
                return {
                    "address": addr,
                    "state": state,
                    "dim": dim,
                    "cover_position": cover_position,
                }

        # Setpoint readback responses (01 02 pattern - device responds with 01 03!)
        case [addr, 0x01, 0x03, 0x04, 0x5c, temp_low, temp_high, *extra] if (device_types or {}).get(addr, "CLIMATE") == "CLIMATE":
            # Setpoint readback response - device returns setpoint via read request
            # Format: AA 01 03 04 5c [temp_low] [temp_high]
            # Pattern: We send 01 02 (read request), device responds with 01 03 (read response)
            # Setpoint encoded as 16-bit little-endian integer (value * 10)
            setpoint = int.from_bytes([temp_low, temp_high], byteorder="little") / 10.0
            rec_log(
                f"THERMOSTAT SETPOINT READBACK (01 02->01 03 pattern) setpoint={setpoint}°C (source=read_01_02)",
                addr,
            )
            rec_log(f"    {data_hex}", addr)
            return {
                "address": addr,
                "setpoint": setpoint,
                "msg_type": "read_01_02",
            }
        
        # Also handle 01 02 pattern in case device uses it directly (though we saw 01 03)
        case [addr, 0x01, 0x02, 0x04, 0x5c, temp_low, temp_high, *extra] if (device_types or {}).get(addr, "CLIMATE") == "CLIMATE":
            # Setpoint readback response (alternative format)
            # Format: AA 01 02 04 5c [temp_low] [temp_high]
            setpoint = int.from_bytes([temp_low, temp_high], byteorder="little") / 10.0
            rec_log(
                f"THERMOSTAT SETPOINT READBACK (01 02 pattern) setpoint={setpoint}°C (source=read_01_02)",
                addr,
            )
            rec_log(f"    {data_hex}", addr)
            return {
                "address": addr,
                "setpoint": setpoint,
                "msg_type": "read_01_02",
            }

        # Legacy / unsolicited setpoint messages (0x01 0x10 0x04 0x5c)
        case [addr, 0x01, 0x10, 0x04, 0x5c, temp_low, temp_high, *extra] if (device_types or {}).get(addr, "CLIMATE") == "CLIMATE":
            # Device pushed a setpoint update (can be write ack or manual knob change)
            setpoint = int.from_bytes([temp_low, temp_high], byteorder="little") / 10.0
            msg_type = "write_ack" if extra else "push_5c"
            rec_log(
                f"THERMOSTAT SETPOINT PUSH setpoint={setpoint}°C (source={msg_type})",
                addr,
            )
            rec_log(f"    {data_hex}", addr)
            return {
                "address": addr,
                "setpoint": setpoint,
                "msg_type": msg_type,
            }

        # Maximum temperature limit messages (register 0x0460)
        case [addr, op1, op2, 0x04, 0x60, sub_id, first_low, first_high, second_low, second_high, *extra] if (device_types or {}).get(addr, "CLIMATE") == "CLIMATE":
            # Limit configuration responses (register 0x0460) carry multiple values depending on sub_id
            first_value = int.from_bytes([first_low, first_high], byteorder="little") / 10.0
            second_value = int.from_bytes([second_low, second_high], byteorder="little") / 10.0
            msg_type = "max_temp_push" if (op1, op2) == (0x01, 0x01) else ("max_temp_read" if (op1, op2) == (0x01, 0x03) else "max_temp_unknown")

            result = {
                "address": addr,
                "msg_type": msg_type,
                "limit_sub_id": sub_id,
            }

            if sub_id == 0x00:
                result["floor_min_temperature"] = first_value
                result["floor_max_temperature"] = second_value
                rec_log(
                    f"THERMOSTAT LIMITS (sub=0x00 floor) floor_min={first_value}°C floor_max={second_value}°C",
                    addr,
                )
            elif sub_id in (0x01, 0x02):
                result["floor_min_temperature"] = first_value
                result["room_max_temperature"] = second_value
                rec_log(
                    f"THERMOSTAT LIMITS (sub=0x{sub_id:02x} room) floor_min={first_value}°C room_max={second_value}°C",
                    addr,
                )
            else:
                result["floor_min_temperature"] = first_value
                result["limit_extra_value"] = second_value
                rec_log(
                    f"THERMOSTAT LIMITS (sub=0x{sub_id:02x}) first={first_value} second={second_value}",
                    addr,
                )

            rec_log(f"    {data_hex}", addr)
            return result

        case [addr, 0x01, 0x10, 0x00, 0xC8, state, dim1, dim2, *extra]:
            # State dim command
            extra_hex = "".join(f"{e:02x}" for e in extra)
            rec_log(f"DIM {state=} {dim1=} {dim2=} {extra=} {extra_hex}", addr)

            dim = dim2
            cover_position = int.from_bytes(
                [dim1, dim2], byteorder="little", signed=True
            )
            cover_angle = None
            if extra:
                # The cover angle is given as a six bit signed number?
                cover_angle = extra[0]
                cover_angle_sign = 1
                if cover_angle & 0x20:
                    cover_angle = ~cover_angle
                    cover_angle_sign = -1
                cover_angle = (cover_angle & 0x1F) * cover_angle_sign

            rec_log(f"    {cover_position=} {cover_angle=}", addr)
            rec_log(f"    {data_hex}", addr)
            return {
                "address": addr,
                "state": state,
                "dim": dim,
                "cover_position": cover_position,
                "cover_angle": cover_angle,
            }

        case [addr, 0x01, 0x10, 0x00, 0x97, state, *extra]:
            # state command
            rec_log(f"STATE {state=} {extra=}", addr)
            rec_log(f"    {data_hex}", addr)
            return {
                "address": addr,
                "state": state,
            }

        case [addr, 0x01, 0x10, 0x04, 0x20, a, 0x01, 0x11, *color_temp]:
            # Color temperature
            color_temp = int.from_bytes(color_temp, "big")
            rec_log(f"COLORTEMP {a}-1-11 {color_temp=}", addr)
            rec_log(f"    {data_hex}", addr)
            return {
                "address": addr,
                "temperature": color_temp,
            }

        case [addr, 0x01, 0x10, 0x04, 0x20, a, 0x03, b, *extra, ll1, ll2]:
            # Motion 
            lightlevel = int.from_bytes([ll1, ll2], "big")
            rec_log(f"MOTION {a}-3-{b} {extra=} {lightlevel=}", addr)
            rec_log(f"    {data_hex}", addr)
            return {
                "address": addr,
                "motion": True,
                "luminance": lightlevel,
            }

        case [addr, 0x01, 0x10, 0x04, 0x20, a, 0x05, *extra]:
            # Off by timeout?
            rec_log(f"TIMEOUT {a=}-5 {extra=}", addr)
            rec_log(f"    {data_hex}", addr)

        case [addr, 0x01, 0x10, 0x04, 0x20, *extra]:
            # Unknown new style command
            extra = [f"{e:02x}" for e in extra]
            rec_log(f"UNKNOWN NEW STYLE {addr=} {extra=}", addr)
            rec_log(f"    {data_hex}", addr)

        case [addr, 0x01, 0x10, cmd1, cmd2, *extra]:
            # Unknown command
            cmd = (f"{cmd1:x}", f"{cmd2:x}")
            extra = [f"{e:02x}" for e in extra]
            extra_hex = "".join(extra) if extra else ""
            rec_log(f"UNKNONW OLD COMMAND addr={addr} cmd={cmd} extra={extra_hex}", addr)
            return None

        case _:
            # Unknown command
            rec_log(f"UNKNOWN {data=}")
            rec_log(f"    {data_hex}")

    return None
