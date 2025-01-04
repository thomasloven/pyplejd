from .debug import rec_log


def parse_lightlevel(data: bytearray):

    for i in range(0, len(data), 10):
        ll = data[i : i + 10]

        address = int(ll[0])
        state = bool(ll[1])
        dim = int(ll[6])  # int.from_bytes(ll[5:7], "little")
        cover_position = int.from_bytes(ll[5:7], "little")

        rec_log(f"LIGHTLEVEL {state=} {dim=}", address)

        yield {
            "address": address,
            "state": state,
            "dim": dim,
            "cover_position": cover_position,
        }
