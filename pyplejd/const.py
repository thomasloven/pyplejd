BLE_UUID_SUFFIX = "6085-4726-be45-040c957391b5"
PLEJD_SERVICE = f"31ba0001-{BLE_UUID_SUFFIX}"
PLEJD_LIGHTLEVEL = f"31ba0003-{BLE_UUID_SUFFIX}"
PLEJD_DATA = f"31ba0004-{BLE_UUID_SUFFIX}"
PLEJD_LASTDATA = f"31ba0005-{BLE_UUID_SUFFIX}"
PLEJD_AUTH = f"31ba0009-{BLE_UUID_SUFFIX}"
PLEJD_PING = f"31ba000a-{BLE_UUID_SUFFIX}"

LIGHT = "LIGHT"
SENSOR = "SENSOR"
SWITCH = "RELAY"
UNKNOWN = "UNKNOWN"


class DEVICES:
    UNKNOWN_TYPE = "-unknown-"
    DIM_01 = "DIM-01"
    DIM_02 = "DIM-02"
    CTR_01 = "CTR-01"
    GWY_01 = "GWY-01"
    LED_10 = "LED-10"
    WPH_01 = "WPH-01"
    REL_01 = "REL-01"
    SPR_01 = "SPR-01"
    WRT_01 = "WRT-01"
    DIM_01_2P = "DIM-01-2P"
    GENERIC = "Generic"
    DIM_01_LC = "DIM-01-LC"
    DIM_02_LC = "DIM-02-LC"
    REL_01_2P = "REL-01-2P"
    REL_02 = "REL-02"
    SPR_01 = "SPR-01"
    LED_75 = "LED_75"

    HARDWARE_ID = {
        "0": UNKNOWN_TYPE,
        "1": DIM_01,
        "2": DIM_02,
        "3": CTR_01,
        "4": GWY_01,
        "5": LED_10,
        "6": WPH_01,
        "7": REL_01,
        "8": SPR_01,
        "10": WRT_01,
        "11": DIM_01_2P,
        "13": GENERIC,
        "14": DIM_01_LC,
        "15": DIM_02_LC,
        "17": REL_01_2P,
        "18": REL_02,
        "20": SPR_01,
        "36": LED_75,
    }

    HARDWARE_TYPE = {
        UNKNOWN_TYPE: UNKNOWN,
        DIM_01: LIGHT,
        DIM_02: LIGHT,
        CTR_01: LIGHT,
        GWY_01: UNKNOWN,
        LED_10: LIGHT,
        WPH_01: SENSOR,  # button
        REL_01: SWITCH,
        SPR_01: SWITCH,
        WRT_01: SENSOR,
        DIM_01_2P: LIGHT,
        GENERIC: LIGHT,
        DIM_01_LC: LIGHT,
        DIM_02_LC: LIGHT,
        REL_01_2P: SWITCH,
        REL_02: SWITCH,
        SPR_01: SWITCH,
        LED_75: LIGHT,
    }

    DIMMABLE = [DIM_01, DIM_02, LED_10, DIM_01_2P, DIM_01_LC, DIM_02_LC, LED_75]
