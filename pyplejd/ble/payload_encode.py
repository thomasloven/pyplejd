from __future__ import annotations
import binascii
from datetime import datetime, timedelta
import time

import typing

if typing.TYPE_CHECKING:
    from . import PlejdMesh

from .crypto import encrypt_decrypt


def encode(mesh: PlejdMesh, payloads: list[str]):
    return [
        encrypt_decrypt(
            mesh._crypto_key,
            mesh._gateway_node,
            binascii.a2b_hex(payload.replace(" ", "")),
        )
        for payload in payloads
    ]


def set_state(mesh: PlejdMesh, address, **state):
    payloads = []

    if (st := state.get("state", None)) is not None:
        if st:
            if (dim := state.get("dim", None)) is not None:
                # Dim command
                # AA 0110 0098 01 DDDD
                # Dim level is passed twice to transform it from 1 byte to 2
                payloads.append(f"{address:02x} 0110 0098 01 {dim:02x}{dim:02x}")
            else:
                # State command on
                # AA 0110 0097 01
                payloads.append(f"{address:02x} 0110 0097 01")
        else:
            # State command off
            # AA 0110 0097 00
            payloads.append(f"{address:02x} 0110 0097 00")

    if (ct := state.get("colortemp", None)) is not None:
        # Color temperature command
        # AA 0110 0420 030111 TTTT
        payloads.append(f"{address:02x} 0110 0420 030111 {ct:04x}")

    if (cover := state.get("cover", None)) is not None:
        if cover < 0:
            # Cover command stop
            # AA 0110 0420 030807 00
            payloads.append(f"{address:02x} 0110 0420 030807 00")
        else:
            # Cover command position
            # AA 0110 0420 030827 01 PPPP
            payloads.append(f"{address:02x} 0110 0420 030827 01 {cover:04x}")

    return encode(mesh, payloads)


def trigger_scene(mesh: PlejdMesh, index):
    # Scene trigger command
    # 02 0110 0021 II
    return encode(mesh, [f"02 0110 0021 {index:02x}"])


def set_time(mesh: PlejdMesh):
    now = datetime.now() + timedelta(seconds=3600 * time.daylight)
    now_bytes = int(now.timestamp()).to_bytes(5, "little")

    # Time broadcast command
    # 00 0110 001B TTTTTTTT

    # TODO: or is it
    # 01 0110 001B TTTTTTTT 01
    # payload = f"01 0110 001B {now_bytes.hex()} 01"

    return encode(mesh, [f"00 0110 001B {now_bytes.hex()}"])


def request_time(mesh: PlejdMesh, address):
    # Request time report command
    # AA 0102 001b
    return encode(mesh, [f"{address:02x} 0102 001b"])


def request_button(mesh: PlejdMesh):
    # Request button identification
    # 00 0110 0015

    return encode(mesh, [f"00 0110 0015"])
