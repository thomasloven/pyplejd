import asyncio

from .plejd_device import PlejdInput, PlejdDeviceType
from ..ble import LastData
from ..ble.debug import rec_log

# Threshold between a single and a long press, and also how long we
# wait for a release before declaring a press "long" on our own: the
# mesh's release packet for a press frequently never arrives at all
# (confirmed live against a real mains-powered puck - lost roughly 1 in
# 3-4 presses during testing), so classifying long press only once a
# release shows up would mean long presses regularly go unreported.
# Firing long_press from a timeout the instant this threshold passes -
# independent of whether a release ever follows - makes it reliable
# either way. A genuine short tap's release reliably does arrive well
# under this (observed ~135-400ms), so the timeout never fires for
# those.
LONG_PRESS_THRESHOLD = 0.5

# Some units' CMD_EVENT_FIRED payload for a press is longer than the
# usual 3 bytes (addr, button, flag) and never gets a release at all,
# regardless of how long the button is actually held (confirmed live
# 2026-10-07 against two distinct physical devices behind two different
# mesh addresses, both sending a 5-byte payload and neither ever
# following up with anything - tested holds up to ~11s, exactly one
# packet each time). Originally tried detecting this by hardware model
# string (WPH-01-LC), but a second, differently-addressed unit showing
# the identical one-packet-then-silence behavior makes the payload
# shape itself the more reliable signal - whatever the exact model,
# nothing this short-lived can ever turn into a real release, so there
# is genuinely no information on the wire to tell a quick tap from a
# long hold. For these, report single_press once the timeout passes
# instead of long_press, and still fire our own synthetic release right
# after so the entity settles back to its normal resting state.
RELEASE_CAPABLE_PAYLOAD_LENGTH = 3


class PlejdButton(PlejdInput):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outputType = PlejdDeviceType.BUTTON
        self._press_time = None
        self._long_press_fired = False
        self._no_release_press = False
        self._cancel_long_press_timer = lambda: None

    @property
    def button_id(self):
        return self.settings.input

    def _notify(self, button, action, click_type):
        rec_log(f"BUTTON button={button} {action=} {click_type=}", self.address)
        for listener in self._listeners:
            listener(
                {
                    **self._state,
                    "button": button,
                    "action": action,
                    "click_type": click_type,
                }
            )

    def _long_press_timeout(self, button):
        self._cancel_long_press_timer = lambda: None
        self._press_time = None
        if self._no_release_press:
            # This press's own payload shape told us no release will
            # ever follow - see RELEASE_CAPABLE_PAYLOAD_LENGTH above.
            # Report the only thing we can actually know (a press
            # happened) as single_press, and immediately settle to
            # release since the real one never comes.
            self._notify(button, "release", "single_press")
            return
        self._long_press_fired = True
        self._notify(button, "long_press", "long_press")

    async def parse_lastdata(self, data: LastData):
        match data.command:
            case LastData.CMD_EVENT_FIRED:
                addr = int(data.payload[0])
                button = int(data.payload[1])
                if not (addr == self.deviceAddress and button == self.settings.input):
                    return
                action = "press"
                if (
                    len(data.payload) == RELEASE_CAPABLE_PAYLOAD_LENGTH
                    and data.payload[2] == 0
                ):
                    action = "release"

                # Any fresh event for this button (press or release)
                # supersedes a still-pending long-press timeout from
                # whatever came before it.
                self._cancel_long_press_timer()

                if action == "press":
                    self._press_time = asyncio.get_running_loop().time()
                    self._long_press_fired = False
                    self._no_release_press = (
                        len(data.payload) != RELEASE_CAPABLE_PAYLOAD_LENGTH
                    )
                    loop = asyncio.get_running_loop()
                    self._cancel_long_press_timer = loop.call_at(
                        loop.time() + LONG_PRESS_THRESHOLD,
                        self._long_press_timeout,
                        button,
                    ).cancel
                    # No HA-facing event for a bare press - see event.py
                    # for why only release/single_press/long_press are
                    # surfaced there.
                    return

                # action == "release" (hardware that does send one)
                click_type = None
                if self._long_press_fired:
                    # Already reported as long_press via the timeout -
                    # this release just confirms it finally let go,
                    # nothing new to classify.
                    pass
                elif self._press_time is not None:
                    duration = asyncio.get_running_loop().time() - self._press_time
                    click_type = (
                        "long_press"
                        if duration > LONG_PRESS_THRESHOLD
                        else "single_press"
                    )
                self._press_time = None
                self._long_press_fired = False
                self._notify(button, "release", click_type)
            case _:
                return
