# Pyplejd

Python package for communicating with and controlling [Plejd](https://plejd.com) devices with [Home Assistant](https://home-assistant.io)

---

Contributors not listed in git history - in no particular order:

- [@astrandb](https://github.com/astrandb)
- [@bnordli](https://github.com/bnordli)
- [@oyvindwe](https://github.com/oyvindwe)
- [@NewsGuyTor](https://github.com/NewsGuyTor)

---

Much information below is taken from here: https://github.com/icanos/hassio-plejd/issues/163

Other things I have discovered myself

# BLE characteristic LASTDATA: `31BA0004-6085-4726-BE45-040C957391B5`

Used for communication both ways

## General format

(two digits or letters correspond to one byte)

`AA 0110 CCCC ...`

Command `CCCC` sent to address `AA`

Command `0420` is a group of command, followed by a three byte specifier: \
`AA 0110 0420 DDDDDD ...`

Some commands can be both received and sent "(R/W)". Others can be received only "(RO)" or sent only "(WO)".

## Scenes

### `00 0110 0021 SS`

Activate scene `SS`

Always sent to address `00`. Probably a broadcast address.

## Light

### On/Off `AA 0110 0097 SS` (R/W)

Turn on `SS=01` or off `SS=00` light at address `AA`.

### Dim level `AA 0110 0098 SS DDDD` (R/W)

### `AA 0110 00C8 SS DDDD` (RO)

Note: `0x98` is also used for cover position and thermostat status - device type determines interpretation.

Turn on `SS=01` or off `SS=00` light at address `AA`.

If turn on, set dim level to `DDDD`.

`DDDD` is encoded **big**-endian.
The easiest way to decode this is to ignore the first byte, and only care about the second.
When sending the command, send the same byte twice. That way you get the dim level in the range 0-255
instead of 0-65535, which is easier to handle.

### Color temperature `AA 0110 0420 030111 TTTT` (R/W)

### `AA 0110 0420 XX0111 TTTT`

Set color temperature of light at address `AA` to `TTTT` Kelvin.

`TTTT` is encoded **little**-endian and seems to typically be the range 2200-4000 (declared in the device data from the cloud).

I have not discovered the significance of `XX`. When sending the command `03` seems to always work, but I have seen different values received.

## Motion sensor

### Motion detected `AA 0110 0420 XX03XX ...` (RO)

Received when WMS-01 detects motion. Motion events are rate limited to about every 25-35 seconds.

The command is followed by eight bytes of data. I think the last two may be related to light level, but my experiments are inconclusive. The others may or may not have something to do with battery voltage, maybe...

## Buttons

### Button pressed `00 0110 0016 AA BB XX` (RO)

Button no. `BB` was pressed on the device with address `AA`.
If `XX` is included, `XX=01` indicates the button was pressed and `XX=00` indicates it was released.

### Request button report `00 0110 0015` (WO)

Sending this command will cause ALL buttons to send the Button Pressed command when pressed.
Otherwise only battery powered buttons (WPH-01) will do so.

This is what the Plejd app uses to identify a button when programming it. As far as I can tell, this does not affect the normal operation of the buttons.

## Coverables

### Cover position `AA 0110 00C8 XX PPPP YY` (RO)

### `AA 0110 0098 SS PPPP YY` (RO)

Note: `0x98` is also used for light dim level and thermostat status - device type determines interpretation.

`PPPP` is the position of the cover. Encoded **little**-endian.

The cover will send the target position and `SS=01` while moving and `SS=00` when the movement is complete.

`YY` is somehow related to the angle of the cover slats (if applicable).
It seems to be two zero bytes followed by a **six** bit signed integer which gives the angle of the cover slats in 5 degree increments +/- 5.

If the cover is of a type going between -90 and +90, it will take those values. If the cover goes between 0 and +90, the value will be in the range [-90, 0].

I've given up on reliably decoding this for the time being...

It also seems that holding the buttons for a longer time sends different commands...

### Set cover position `AA 0110 0420 030807 01 PPPP` (WO)

Set cover at address `AA` to position `PPPP`.

`PPPP` is encoded **little**-endian and sets a percentage between `00` and `0xFFFF`.

I believe the angle of the cover slats (if applicable) is adjusted by small movements after reaching the target position. I've not dived into this at the time being (see above).

### Stop cover movement `AA 0110 0420 030807 00` (WO)

Immediately stops the movement of the cover.

## Thermostats/Climate

### Thermostat status `AA 0110 0098 SS [status1] [status2] [heating]` (RO)

Note: `0x98` is also used for light dim level and cover position - device type determines interpretation.

For climate devices, this message contains:
- `SS`: State (0x00 = off, 0x01 = on/heating)
- `status1`: Status byte 1
- `status2`: Status byte 2 (lower 6 bits contain current temperature: `(status2 & 0x3F) - 10` in °C)
- `heating`: Heating flag (0x80 = heating, otherwise idle)

The current temperature is decoded from `status2` using: `temperature = (status2 & 0x3F) - 10` in degrees Celsius.

### Setpoint register (0x5c)

#### Write setpoint `AA 0110 045C [temp_low] [temp_high]` (WO)

Set the temperature setpoint. Temperature is encoded as 16-bit **little**-endian integer (value * 10), so `0x0A01` = 26.6°C, `0x0E01` = 30.0°C.

#### Read setpoint `AA 0102 045C` → `AA 0103 045C [temp_low] [temp_high]` (R/W)

Read the current setpoint using the 01 02 read pattern:
- Send: `AA 0102 045C` (read request)
- Receive: `AA 0103 045C [temp_low] [temp_high]` (read response)

The setpoint is encoded as 16-bit **little**-endian integer (value * 10).

#### Setpoint read response `AA 0103 045C [temp_low] [temp_high]` (RO)

Device responds to setpoint read requests with the current setpoint value. This is the response to the `AA 0102 045C` read request (01 02 → 01 03 pattern).

Note: Manual knob changes on the device also trigger setpoint updates

### Temperature limits register (0x0460)

#### Read limits `AA 0102 0460 [sub_id]` → `AA 0103 0460 [sub_id] [first_low] [first_high] [second_low] [second_high]` (R/W)

Read thermostat temperature limits using the 01 02 read pattern with different sub-IDs:
- Send: `AA 0102 0460 [sub_id]` (read request)
- Receive: `AA 0103 0460 [sub_id] [first_low] [first_high] [second_low] [second_high]` (read response)

Response format depends on `sub_id`:
- `sub_id = 0x00`: `first` = floor_min_temperature, `second` = floor_max_temperature
- `sub_id = 0x01` or `0x02`: `first` = floor_min_temperature, `second` = room_max_temperature

All temperatures are encoded as 16-bit **little**-endian integers (value * 10).

### Mode registers

#### Read mode (OFF) `AA 0102 045F` → `AA 0103 045F [mode]` (R/W)

Read thermostat OFF mode status:
- Send: `AA 0102 045F` (read request)
- Receive: `AA 0103 045F [mode]` (read response)
- `mode = 0x00`: Device is in OFF mode
- `mode != 0x00`: Device is not in OFF mode

#### Read mode (HEAT) `AA 0102 047E` → `AA 0103 047E [mode]` (R/W)

Read thermostat HEAT mode status:
- Send: `AA 0102 047E` (read request)
- Receive: `AA 0103 047E [mode]` (read response)
- `mode = 0x00`: Device is in HEAT mode
- `mode != 0x00`: Device is not in HEAT mode

#### Set mode `AA 0110 045F [mode]` / `AA 0110 047E [mode]` (WO)

Set thermostat mode:
- Register `0x5F`: Set OFF mode (`mode=0x00` to enable OFF)
- Register `0x7E`: Set HEAT mode (`mode=0x00` to enable HEAT)

Note: The mode is determined by which register is set to `0x00`.
