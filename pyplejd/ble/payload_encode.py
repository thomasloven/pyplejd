from __future__ import annotations
import binascii
from datetime import datetime, timedelta
import math
import time

import typing

if typing.TYPE_CHECKING:
    from . import PlejdMesh

from .crypto import encrypt_decrypt
from .debug import send_log


def encode(mesh: PlejdMesh, payloads: list[str]):
    return [
        encrypt_decrypt(
            mesh._crypto_key,
            mesh._gateway_node,
            binascii.a2b_hex(payload.replace(" ", "")),
        )
        for payload in payloads
    ]


def hex_payload(payload):
    return "".join([f"{b:02x}" for b in binascii.a2b_hex(payload.replace(" ", ""))])


def set_state(mesh: PlejdMesh, address, **state):
    payloads = []

    if (st := state.get("state", None)) is not None:
        if st:
            if (dim := state.get("dim", None)) is not None:
                # Dim command
                # AA 0110 0098 01 DDDD
                # Dim level is passed twice to transform it from 1 byte to 2
                payloads.append(f"{address:02x} 0110 0098 01 {dim:02x}{dim:02x}")
                send_log(f"DIM command {hex_payload(payloads[-1])}", address)
            else:
                # State command on
                # AA 0110 0097 01
                payloads.append(f"{address:02x} 0110 0097 01")
                send_log(f"ON command {hex_payload(payloads[-1])}", address)
        else:
            # State command off
            # AA 0110 0097 00
            payloads.append(f"{address:02x} 0110 0097 00")
            send_log(f"OFF command {hex_payload(payloads[-1])}", address)

    if (ct := state.get("colortemp", None)) is not None:
        # Color temperature command
        # AA 0110 0420 030111 TTTT
        payloads.append(f"{address:02x} 0110 0420 030111 {ct:04x}")
        send_log(f"COLORTEMP command {hex_payload(payloads[-1])}", address)

    if (cover := state.get("cover", None)) is not None:
        if cover < 0:
            # Cover command stop
            # AA 0110 0420 030807 00
            payloads.append(f"{address:02x} 0110 0420 030807 00")
            send_log(f"COVER STOP command {hex_payload(payloads[-1])}", address)
        else:
            # Cover command position
            # AA 0110 0420 030827 01 PPPP
            payloads.append(f"{address:02x} 0110 0420 030827 01 {cover:04x}")
            send_log(f"COVER POSITION command {hex_payload(payloads[-1])}", address)

    if (thermostat_mode := state.get("thermostat_mode", None)) is not None:
        # Thermostat mode command (confirmed from Plejd app behavior)
        # OFF uses register 0x5f: AA 0110 045f 00
        # ON uses register 0x7e: AA 0110 047e 00
        
        if isinstance(thermostat_mode, str):
            mode_lower = thermostat_mode.lower()
            if mode_lower in ("off", "standby", "0"):
                payload = f"{address:02x} 0110 045f 00"
            else:
                # Turn ON (heat mode) - register 0x7e
                payload = f"{address:02x} 0110 047e 00"
        else:
            # Boolean: True = ON, False = OFF
            payload = f"{address:02x} 0110 047e 00" if thermostat_mode else f"{address:02x} 0110 045f 00"

        payloads.append(payload)
        send_log(
            f"THERMOSTAT MODE command {hex_payload(payload)} mode={thermostat_mode}",
            address,
        )

    if (setpoint := state.get("setpoint", None)) is not None:
        # Setpoint temperature command
        # AA 0110 045c TTTT
        # Temperature encoded as 16-bit little-endian integer (value * 10)
        # Round up to nearest degree (devices don't support fractional degrees)
        setpoint_rounded = math.ceil(setpoint)
        temp_value = int(setpoint_rounded * 10)
        temp_bytes = temp_value.to_bytes(2, "little")
        payloads.append(f"{address:02x} 0110 045c {temp_bytes.hex()}")
        send_log(f"SETPOINT command {hex_payload(payloads[-1])} ({setpoint_rounded}°C)", address)

    encoded = encode(mesh, payloads)
    
    # Return encoded payloads (device will confirm via write_ack or push_5c notifications)
    return encoded, {}


def trigger_scene(mesh: PlejdMesh, index):
    # Scene trigger command
    # 02 0110 0021 II
    payload = f"02 0110 0021 {index:02x}"
    send_log(f"SCENE command {hex_payload(payload)}", "SCN")
    return encode(mesh, [payload])


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
    return encode(mesh, [payload])


def request_time(mesh: PlejdMesh, address):
    # Request time report command
    # AA 0102 001b

    payload = f"{address:02x} 0102 001b"
    send_log(f"TIME REQUEST {hex_payload(payload)}", "TME")
    return encode(mesh, [payload])


def request_button(mesh: PlejdMesh):
    # Request button identification
    # 00 0110 0015

    payload = f"00 0110 0015"
    send_log(f"IDENTIFY BUTTON REQUEST {hex_payload(payload)}")
    return encode(mesh, [payload])
