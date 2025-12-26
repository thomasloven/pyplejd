class LightLevel:

    def __init__(self, data: bytearray):
        self.address = int(data[0])
        self.state = bool(data[1])
        self.dim = int.from_bytes(data[5:7], byteorder="little")
        self.payload = [int(d) for d in data[5:]]


def parse_lightlevels(data: bytearray):
    # NodeIndexDataVector always contains exactly 10 or 20 bytes
    return [LightLevel(data[i : i + 10]) for i in range(0, len(data), 10)]
