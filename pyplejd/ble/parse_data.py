from .debug import rec_log


def parse_data(data: bytearray):
    data_bytes = [data[i] for i in range(0, len(data))]
    data_hex = "".join(f"{b:02x}" for b in data_bytes)

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

        case [addr, 0x01, 0x10, 0x00, 0xC8, state, dim1, dim2, *extra] | [
            addr,
            0x01,
            0x10,
            0x00,
            0x98,
            state,
            dim1,
            dim2,
            *extra,
        ]:
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
            rec_log(f"UNKNONW OLD COMMAND {addr=} {cmd=} {extra=}", addr)
            rec_log(f"    {data_hex}", addr)

        case _:
            # Unknown command
            rec_log(f"UNKNOWN {data=}")
            rec_log(f"    {data_hex}")

    return {}
