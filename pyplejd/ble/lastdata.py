from .debug import rec_log

# Motion event: 03 03 1f 07 00 9c 0f 08 46 06 01

# 03 03
# len 1
# type 3 (Source)
# data 03 (motion source)

# 1f 07 00 9c
# len 2
# type 15+7 (LowPowerBatteryInfo)
# data 00 9C

# 0f 08 46
# Len 1
# Type 15+8 (SenderDeviceType)
# Data 46

# 06 01
# Len 1
# Type 6 (Lux)
# Data 01 (below limit) (02 above limit)

# FSSS TTTT
# F - Flag
# S - payload size
# T - Type


class MiniPkg:
    TPE_WHITEBALANCE = 0x01
    TPE_SOURCE = 0x03
    TPE_LUX = 0x06
    TPE_WINDOWCONTROL = 0x07
    TPE_CHANNEL = 0x10
    TPE_BATTERYINFO = 0x16
    TPE_TILT = 0x18

    SRC_MANUAL = 0x01
    SRC_MOTION = 0x03
    SRC_APP = 0x08

    def __init__(
        self,
        data: bytearray = None,
        /,
        type: int = 0,
        flag: bool = False,
        payload: list[int] = None,
    ):
        self.type = type
        self.flag = flag
        self.payload = payload or []
        if data:
            self.data = data

    @property
    def data(self):
        header = 0x80 if self.flag else 0
        header += ((len(self.payload) - 1) & 0x7) << 4
        if self.type > 0xF:
            package = [header + 0xF, self.type - 0xF]
        else:
            package = [header + (self.type & 0x7)]

        package.extend(self.payload)
        return package

    @data.setter
    def data(self, dta):
        self.flag = bool(int(dta[0]) & 0x80)
        length = (int(dta[0]) & 0x70) >> 4
        start = 1
        self.type = int(dta[0]) & 0x0F
        if self.type == 0x0F:
            self.type += int(dta[1])
            start = 2
        self.payload = [int(i) for i in dta[start : start + length + 1]]

    @property
    def length(self):
        return len(self.payload) + (2 if self.type > 0x0F else 1)

    def __repr__(self):
        return f"{1 if self.flag else 0} {self.length} 0x{self.type:x}: {self.payload} - {"".join(f"{d:02x}" for d in self.data)}"


class LastData:

    # Commands
    CMD_EVENT_PREPARE = 0x0015  # ask for buttons
    CMD_EVENT_FIRED = 0x0016  # button pressed
    CMD_SCENE = 0x0021
    CMD_GROUP_OUTPUT_STATE = 0x0097
    CMD_GROUP_OUTPUT_STATE_AND_LEVEL = 0x0098
    CMD_OUTPUT_STATE_AND_LEVEL = 0x00C8
    CMD_OUTPUT_SET = 0x0420
    CMD_TUNABLE_WHITE_TEMPERATURE = 0x0101
    CMD_AMBIENT_LIGHT_LEVEL = 0x0434
    CMD_TRM_TEMPERATURE_REGULATING_SETPOINT = 0x045C
    CMD_TMR_OPERATING_MODE = 0x045F
    CMD_TMR_RESET_OPERATING_MODE = 0x047E

    # Command types
    CMDT_WRITE = 0x0
    CMDT_ACK = 0x1
    CMDT_READ = 0x2
    CMDT_DONT_RESPOND = 0x10

    def __init__(
        self,
        data: bytearray = None,
        /,
        address: int = 0x00,
        command: int = 0,
        payload: list[int | MiniPkg] = None,
    ):
        self.address = address
        self.version = 0x01
        self.command_type = LastData.CMDT_DONT_RESPOND
        self.command = command
        self.payload = payload or []

        if data:
            self.data = data

    @property
    def data(self) -> list[int]:
        payload = [*self.payload]
        if payload and isinstance(payload[0], MiniPkg):
            payload = []
            for p in self.payload:
                payload.extend(p.data)
        return [
            self.address,
            self.version,
            self.command_type,
            *self.command.to_bytes(2),
            *payload,
        ]

    @data.setter
    def data(self, dta: list[int] | bytearray):
        self.address = int(dta[0])
        self.command_type = int(dta[2])
        self.command = int.from_bytes(dta[3:5], byteorder="big")
        self.payload = dta[5:]

    @property
    def hex(self):
        return "".join(f"{b:02x}" for b in self.data)

    def __str__(self):
        return f"{self.hex} - {self.address} {self.command_type} {self.command} {self.payload}"

    @property
    def minipkgs(self):
        offset = 0
        while offset < len(self.payload):
            pkg = MiniPkg(self.payload[offset:])
            offset += pkg.length
            yield pkg


def parse_data(data: bytearray):
    data_bytes = [data[i] for i in range(0, len(data))]
    data_hex = "".join(f"{b:02x}" for b in data_bytes)

    match data_bytes:
        case [0x01, 0x01, 0x10, *extra]:
            # Time data
            rec_log(f"TIME DATA {extra}", "TME")
            rec_log(f"    {data_hex}", "TME")

        # case [0x02, 0x01, 0x10, 0x00, 0x21, scene, *extra]:
        #     # Scene update
        #     rec_log(f"SCENE UPDATE {scene=} {extra=}", "SCN")
        #     rec_log(f"    {data_hex}", "SCN")
        #     return {
        #         "scene": scene,
        #         "triggered": True,
        #     }

        # case [0x00, 0x01, 0x10, 0x00, 0x21, scene, *extra]:
        #     # Scene triggered
        #     rec_log(f"SCENE TRIGGER {scene=} {extra=}", "SCN")
        #     rec_log(f"    {data_hex}", "SCN")
        #     return {
        #         "scene": scene,
        #         "triggered": True,
        #     }

        # case [0x00, 0x01, 0x10, 0x00, 0x15, *extra]:
        #     # Identify buttons command
        #     rec_log(f"IDENTIFY BUTTON REQUEST {extra=}")
        #     rec_log(f"    {data_hex}")

        # case [0x00, 0x01, 0x10, 0x00, 0x16, addr, button, *extra]:
        #     # Button pressed
        #     rec_log(f"BUTTON {button=} {extra=}", addr)
        #     rec_log(f"    {data_hex}", addr)
        #     return {
        #         "address": addr,
        #         "button": button,
        #         "action": "release" if len(extra) and not extra[0] else "press",
        #     }

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

        # case [addr, 0x01, 0x10, 0x00, 0x97, state, *extra]:
        #     # state command
        #     rec_log(f"STATE {state=} {extra=}", addr)
        #     rec_log(f"    {data_hex}", addr)
        #     return {
        #         "address": addr,
        #         "state": state,
        #     }

        # case [addr, 0x01, 0x10, 0x04, 0x20, a, 0x01, 0x11, *color_temp]:
        #     # Color temperature
        #     color_temp = int.from_bytes(color_temp, "big")
        #     rec_log(f"COLORTEMP {a}-1-11 {color_temp=}", addr)
        #     rec_log(f"    {data_hex}", addr)
        #     return {
        #         "address": addr,
        #         "temperature": color_temp,
        #     }

        # case [addr, 0x01, 0x10, 0x04, 0x20, a, 0x03, b, *extra, ll1, ll2]:
        #     # Motion
        #     lightlevel = int.from_bytes([ll1, ll2], "big")
        #     rec_log(f"MOTION {a}-3-{b} {extra=} {lightlevel=}", addr)
        #     rec_log(f"    {data_hex}", addr)
        #     return {
        #         "address": addr,
        #         "motion": True,
        #         "luminance": lightlevel,
        #     }

        # case [addr, 0x01, 0x10, 0x04, 0x20, a, 0x05, *extra]:
        #     # Off by timeout?
        #     rec_log(f"TIMEOUT {a=}-5 {extra=}", addr)
        #     rec_log(f"    {data_hex}", addr)

        # case [addr, 0x01, 0x10, 0x04, 0x20, *extra]:
        #     # Unknown new style command
        #     extra = [f"{e:02x}" for e in extra]
        #     rec_log(f"UNKNOWN NEW STYLE {addr=} {extra=}", addr)
        #     rec_log(f"    {data_hex}", addr)

        # case [addr, 0x01, 0x10, cmd1, cmd2, *extra]:
        #     # Unknown command
        #     cmd = (f"{cmd1:x}", f"{cmd2:x}")
        #     extra = [f"{e:02x}" for e in extra]
        #     rec_log(f"UNKNONW OLD COMMAND {addr=} {cmd=} {extra=}", addr)
        #     rec_log(f"    {data_hex}", addr)

        # case _:
        #     # Unknown command
        #     rec_log(f"UNKNOWN {data=}")
        #     rec_log(f"    {data_hex}")

    return {}
