import binascii
import hashlib
import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


def encrypt_decrypt(key: str, addr: str, data: bytearray) -> bytearray:
    key = binascii.a2b_hex(key.replace("-", ""))
    addr = binascii.a2b_hex(addr.replace("-", "").replace(":", ""))[::-1]

    buf = addr + addr + addr[:4]

    ct = Cipher(algorithms.AES(bytearray(key)), modes.ECB(), backend=default_backend())
    ct = ct.encryptor()
    ct = ct.update(buf)

    output = b""
    for i, d in enumerate(data):
        output += struct.pack("B", d ^ ct[i % 16])
    return output


def auth_response(key: str, challenge: bytearray) -> bytearray:
    key = binascii.a2b_hex(key.replace("-", ""))

    k = int.from_bytes(key, "big")
    c = int.from_bytes(challenge, "big")
    intermediate = hashlib.sha256((k ^ c).to_bytes(16, "big")).digest()
    part1 = intermediate[:16]
    part2 = intermediate[16:]
    return bytearray([(a ^ b) for (a, b) in zip(part1, part2)])
