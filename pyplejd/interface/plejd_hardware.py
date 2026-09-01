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

        # Filled in by PlejdManager.poll_diagnostics(). None until first polled,
        # and left alone if a device stops answering so the last known value
        # stays visible rather than flapping to unknown.
        self.internal_temperature: int | None = None
        self.external_temperature: int | None = None
        self.hardfault: bool | None = None
        self.diagnostics_updated = None

        self._listeners = set()

    def __repr__(self):
        return f"PlejdHardware(BLEaddress={self.BLEaddress}, powered={self._powered}, blacklisted={self.blacklisted})"

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
