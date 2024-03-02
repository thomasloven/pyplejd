BLE_UUID_SUFFIX = "6085-4726-be45-040c957391b5"
PLEJD_SERVICE = f"31ba0001-{BLE_UUID_SUFFIX}"
PLEJD_LIGHTLEVEL = f"31ba0003-{BLE_UUID_SUFFIX}"
PLEJD_DATA = f"31ba0004-{BLE_UUID_SUFFIX}"
PLEJD_LASTDATA = f"31ba0005-{BLE_UUID_SUFFIX}"
PLEJD_AUTH = f"31ba0009-{BLE_UUID_SUFFIX}"
PLEJD_PING = f"31ba000a-{BLE_UUID_SUFFIX}"

LIGHT = "LIGHT"
SENSOR = "SENSOR"
MOTION = "MOTION"
SWITCH = "RELAY"
UNKNOWN = "UNKNOWN"


class Device:
    def __init__(self, name, type, dimmable=False, colortemp=False):
        self.name = name
        self.type = type
        self.dimmable = dimmable
        self.colortemp = colortemp


HARDWARE = {
    "0": Device("-unknown-", UNKNOWN),
    "1": Device("DIM-01", LIGHT, dimmable=True),
    "2": Device("DIM-02", LIGHT, dimmable=True),
    "3": Device("CTR-01", LIGHT),
    "4": Device("GWY-01", UNKNOWN),
    "5": Device("LED-10", LIGHT, dimmable=True),
    "6": Device("WPH-01", SENSOR),
    "7": Device("REL-01", SWITCH),
    "8": Device("SPR-01", SWITCH),
    "10": Device("WRT-01", SENSOR),
    "11": Device("DIM-01-2P", LIGHT, dimmable=True),
    "12": Device("DAL-01", UNKNOWN),
    "13": Device("Generic", LIGHT),
    "14": Device("DIM-01-LC", LIGHT, dimmable=True),
    "15": Device("DIM-02-LC", LIGHT, dimmable=True),
    "17": Device("REL-01-2P", SWITCH),
    "18": Device("REL-02", SWITCH),
    "19": Device("EXT-01", UNKNOWN),
    "20": Device("SPR-01", SWITCH),
    "36": Device("LED-75", LIGHT, dimmable=True),
    "70": Device("WMS-01", MOTION),
    "103": Device("OUT-01", LIGHT, dimmable=True, colortemp=True),
    "167": Device("DWN-01", LIGHT, dimmable=True, colortemp=True),
    "199": Device("DWN-02", LIGHT, dimmable=True, colortemp=True),
}

HARDWARE_UNKNOWN = HARDWARE["0"]
