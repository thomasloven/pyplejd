from __future__ import annotations
import binascii
from datetime import datetime, timedelta
import time

import typing

if typing.TYPE_CHECKING:
    from . import PlejdMesh

from .crypto import encrypt_decrypt
from .debug import send_log


def hex_payload(payload):
    return "".join([f"{b:02x}" for b in binascii.a2b_hex(payload.replace(" ", ""))])


def set_time(mesh: PlejdMesh):
    now = datetime.now() + timedelta(seconds=3600 * time.daylight)
    now_bytes = int(now.timestamp()).to_bytes(5, "little")

    # Time broadcast command
    # 00 0110 001B TTTTTTTT

    # TODO: or is it
    # 01 0110 001B TTTTTTTT 01
    # payload = f"01 0110 001B {now_bytes.hex()} 01"

    payload = f"00 0110 001B {now_bytes.hex()}"
    send_log(f"SET TIME command {hex_payload(payload)}", "TME")
    return payload
    return encode(mesh, [payload])


def request_time(mesh: PlejdMesh, address):
    # Request time report command
    # AA 0102 001b

    payload = f"{address:02x} 0102 001b"
    send_log(f"TIME REQUEST {hex_payload(payload)}", "TME")
    return payload
    return encode(mesh, [payload])
