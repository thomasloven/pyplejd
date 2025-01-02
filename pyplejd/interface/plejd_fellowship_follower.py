from .plejd_device import PlejdDevice


class PlejdFellowshipFollower(PlejdDevice):
    # Fellowshipfollowers are lights that are part of a group
    # E.g. several DWN-01 can be grouped with one device being the leader and the rest followers
    # They all should be registered as devices, so that the BLE connection to the mesh can be made
    # through any one of them.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outputType = None
