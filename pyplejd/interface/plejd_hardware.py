from ..ble import MeshDevice


class PlejdHardware(MeshDevice):
    def __init__(
        self,
        BLEaddress: str,
        powered: bool,
        blacklisted: bool = False,
    ):
        self.BLEaddress = BLEaddress
        self._powered = powered
        self.blacklisted = blacklisted
        self.devices = set()
        self.last_seen = None
        self.rssi = None

        self._listeners = set()

    @property
    def connectable(self):
        return self._powered and not self.blacklisted

    def see(self, *args, **kwargs):
        retval = super().see(*args, **kwargs)
        self.update()
        return retval

    def update(self):
        for listener in self._listeners:
            listener()

    def subscribe(self, listener):
        self._listeners.add(listener)

        def remover():
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remover
