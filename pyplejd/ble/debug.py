import logging


def send_log(message, address=None):
    L_ALL = logging.getLogger("pyplejd.ble.device.all")
    if address is not None:
        L = logging.getLogger(f"pyplejd.ble.device.{address}")
        L.debug(f"SEND {address}: {message}")
        L_ALL.debug(f"SEND {address}: {message}")
    else:
        L_ALL.debug(f"SEND: {message}")


def rec_log(message, address=None):
    L_ALL = logging.getLogger("pyplejd.ble.device.all")
    if address is not None:
        L = logging.getLogger(f"pyplejd.ble.device.{address}")
        L.debug(f"RECEIVE {address}: {message}")
        L_ALL.debug(f"RECEIVE {address}: {message}")
    else:
        L_ALL.debug(f"RECEIVE: {message}")
