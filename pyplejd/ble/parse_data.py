import logging

LOGGER = logging.getLogger(__name__)

def log_command(message, addr = None):
    logger = LOGGER.debug
    if addr:
        logger(f"({addr:>3}) - " + message)
    else:
        logger(f"      - " + message)

def parse_data(data: bytearray):
    data_bytes = [data[i] for i in range(0, len(data))]

    match data_bytes:
        case [0x01, 0x01, 0x10, *extra]:
            # Time data
            log_command(f"TIME DATA {extra}", "TME")


        case [0x02, 0x01, 0x10, *extra]:
            # Scene update
            log_command(f"SCENE UPDATGE {extra}", "SCN")

        case [0x00, 0x01, 0x10, 0x00, 0x21, scene, *extra]:
            # Scene triggered
            log_command(f"SCENE TRIGGER {scene=} {extra=}", "SCN")
            return {
                "scene": scene,
                "triggered": True,
            }


        case [0x00, 0x01, 0x10, 0x00, 0x15, *extra]:
            # Identify buttons command
            log_command(f"IDENTIFY BUTTON REQUEST {extra=}", " - ")

        case [0x00, 0x01, 0x10, 0x00, 0x16, addr, button, *extra]:
            # Button pressed
            log_command(f"BUTTON {button=} {extra=}", addr)
            return {
                "address": addr,
                "button": button,
                "action": "release" if len(extra) and not extra[0] else "press",
            }

        case [addr, 0x01, 0x10, 0x00, 0xC8, state, dim1, dim2, *extra] | [addr, 0x01, 0x10, 0x00, 0x98, state, dim1, dim2, *extra]:
            # State dim command
            extra_hex = "".join(f"{e:02x}" for e in extra)
            log_command(f"DIM {state=} {dim1=} {dim2=} {extra=} {extra_hex}", addr)

            dim = dim2
            cover_position = int.from_bytes([dim1, dim2], byteorder="little", signed=True)
            cover_angle = None
            if extra:
                # The cover angle is given as a six bit signed number?
                cover_angle = extra[0]
                cover_angle_sign = 1
                if cover_angle & 0x20:
                    cover_angle = ~cover_angle
                    cover_angle_sign = -1
                cover_angle = (cover_angle & 0x1F) * cover_angle_sign

            log_command(f"    {cover_position=} {cover_angle=}", addr)
            return {
                "address": addr,
                "state": state,
                "dim": dim,
                "cover_position": cover_position,
                "cover_angle": cover_angle,
            }

        case [addr, 0x01, 0x10, 0x00, 0x97, state, *extra]:
            # state command
            log_command(f"STATE {state=} {extra=}", addr)
            return {
                "address": addr,
                "state": state,
            }


        case [addr, 0x01, 0x10, 0x04, 0x20, a, 0x01, 0x11, *color_temp]:
            # Color temperature
            color_temp = int.from_bytes(color_temp, "big")
            log_command(f"COLORTEMP {a}-1-11 {color_temp=}", addr)
            return {
                "address": addr,
                "temperature": color_temp,
            }


        case [addr, 0x01, 0x10, 0x04, 0x20, a, 0x03, b, *extra, ll1, ll2]:
            # Motion
            lightlevel = int.from_bytes([ll1, ll2], "big")
            log_command(f"MOTION {a}-3-{b} {extra=} {lightlevel=}", addr)
            return {
                "address": addr,
                "motion": True,
                "luminance": lightlevel,
            }


        case [addr, 0x01, 0x10, 0x04, 0x20, a, 0x05, *extra]:
            # Off by timeout?
            log_command(f"TIMEOUT {a=}-5 {extra=}", addr)


        case [addr, 0x01, 0x10, 0x04, 0x20, *extra]:
            # Unknown new style command
            extra = [f"{e:02x}" for e in extra]
            log_command(f"UNKNOWN NEW STYLE {addr=} {extra=}", addr)

        case [addr, 0x01, 0x10, cmd1, cmd2, *extra]:
            # Unknown command
            cmd = (f"{cmd1:x}", f"{cmd2:x}")
            extra = [f"{e:02x}" for e in extra]
            log_command(f"UNKNONW OLD COMMAND {addr=} {cmd=} {extra=}", addr)

        case _:
            # Unknown command
            log_command(f"UNKNOWN {data=}")

    return {}