import logging

LOGGER = logging.getLogger(__name__)

def parse_lightlevel(data: bytearray):

  for i in range(0, len(data), 10):
    ll = data[i:i+10]

    address = int(ll[0])
    state = bool(ll[1])
    dim = int(ll[6]) #int.from_bytes(ll[5:7], "little")
    cover_position = int.from_bytes(ll[5:7], "little")

    # LOGGER.error(f"LIGHTLEVEL {address=} {state=} {dim=}")

    yield {
      "address": address,
      "state": state,
      "dim": dim,
      "cover_position": cover_position,
    }