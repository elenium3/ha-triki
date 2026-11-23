# Protocol

Everything below comes from community reverse engineering and from captures
made during development. There is no official specification. The primary
sources are listed at the end; `custom_components/triki/protocol.py` is the
executable version of this page.

## Advertising

- Local name `Triki NNNNNNNNNN` (ten digits; the Żappka app shows the same
  number). The integration matches `Triki*` and `TRIKI*`.
- Manufacturer data with company id `0xFF00` and a short, constant payload.
  The payload does not change on button presses, so an advertisement carries
  no state; only its presence and timing matter.
- The token advertises when its button wakes it from sleep (picking it up,
  shaking it or knocking the table does not wake it, firmware 3.2.1-A,
  2026-11-23), for a few seconds, and for about three minutes after a link is
  dropped. Then it sleeps and stops advertising completely.

## GATT

| Service | Characteristic | UUID | Properties | Use |
|---|---|---|---|---|
| Nordic UART Service | | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | | |
| | RX | `6e400002-…` | write | host → token commands |
| | TX | `6e400003-…` | notify | token → host frames |
| | CTRL | `6e400004-…` | read, write | bit 0 = green LED |
| Battery (0x180F) | Battery Level | `0x2A19` | read | percent |
| Device Information (0x180A) | Firmware Revision | `0x2A26` | read | e.g. `3.2.1-A` |
| | Hardware Revision | `0x2A27` | read | |
| | Manufacturer, Model | `0x2A29`, `0x2A24` | read | |

The token requests a connection interval of 7.5–15 ms and a supervision timeout
of 4 s through an L2CAP connection parameter update right after connecting.

## Commands (write to RX)

| Command | Bytes | Notes |
|---|---|---|
| Start IMU stream | `20 10 00 D0 07 <rate u16 LE> 03` | Rate in Hz: 26, 52, 104, 208 (LSM6DSL output data rates; Flopsstuff reports 416 accepted too, this integration offers up to 208). 12.5 is rejected. Bytes `D0 07` and `03` are not decoded. The token acknowledges with a notification `21 00 00 00 00`; `21 01 …` was seen once when it refused to stream. |
| Stop IMU stream | `20 00 00 00 00 00 00` | Seen in an HCI snoop of the Żappka app before it disconnects ([TrikiEmu](https://github.com/Maku-hub/TrikiEmu)). Flopsstuff's guide says there is no stop opcode and the stream ends on disconnect; both are consistent with what this integration sees. |
| LED on / off | write `01` / `00` to CTRL | A one-bit register; reading CTRL returns the state in bit 0. |

Other opcodes documented by Flopsstuff (reply opcode = request `| 0x80`;
TX is silent until a command arrives): `05` static configuration, `07` unique
id, `09` status (~54 bytes), `43` live counter. `0a`, `42`, `44`, `46` cause a
soft reset of the token. `42` is the reboot into the Nordic DFU bootloader,
which then advertises as `TrikiDfu…` ([Piwencjusz/zabka-triki-hardware](https://github.com/Piwencjusz/zabka-triki-hardware),
`dfu_trigger.py`); discovery ignores that name. The integration uses none of
these opcodes.

Re-sending *Start* with another rate over a live link switches the rate without
a reconnect; the stream continues and the IMU does not re-settle. The
integration uses this for the idle rate.

## Motion frames (notifications on TX)

14 bytes, little-endian:

```
0x22 | status | gx gy gz | ax ay az
       bit0 = button pressed      int16 each
```

Only bit 0 of the status byte is known. In the 13 captures taken during
development (785 kB of notifications, 56 075 frames, firmware 3.2.1-A) the byte
is always `0x00` or `0x01`, checked on the raw bytes, not through the parser.
The parser relies on this: `0x22` is common inside the int16 fields, so a header
counts only when the next byte is `0x00` or `0x01`. A frame with any other
status value would be dropped and show up as `parser_dropped_bytes` in
diagnostics. The bytes the parser does drop in those captures are the start
acknowledgement `21 00 00 00 00` (it also arrives after each rate switch over a
live link) and the torn remains of frames whose 20-byte chunk was lost on the
BlueZ path.

| Field | Scale | Full range |
|---|---|---|
| gyro | 14.286 LSB per °/s | ±2000 °/s |
| accel | 2048 LSB per g | ±16 g |

Axes are in the sensor frame, right-handed, viewed from the green PCB side with
the Ż upright:

| Axis | Points toward |
|---|---|
| +z | out of the green PCB face (the Ż side) |
| −z | out of the metal cap face (the "T" logo) |
| −y | the top of the Ż (12 o'clock) |
| +x | the left of the Ż (9 o'clock) |

So a token lying metal side up, as it usually sits, reads −1 g on z, and PCB side
up reads +1 g. The table follows the measurements in
[Flopsstuff/triki](https://github.com/Flopsstuff/triki) (`docs/guide/hardware.md`),
and koksny/TRIKI-Control and TrikiScope agree on the z sign. The integration does
not depend on the sign: it measures turns about whatever direction gravity has.
Some earlier tools used a gyro scale of 131 LSB per
°/s (an MPU‑6050 value); that under-reads rotation about nine times. 14.286 is
the LSM6DSL value at ±2000 °/s and matches real turns. Notifications may carry several frames back to back
(20-byte MTU chunks are common through BlueZ; proxies deliver whole frames), so
the parser re-synchronises on the `0x22` header and skips stray bytes; the
count of skipped bytes is reported in diagnostics.

The first 20 or so frames after *Start* are the IMU settling and are discarded
by the integration.

## What the Żappka app does that this integration does not

An HCI snoop of the app shows a session handshake after *Start*:

```
app  → 0a <16-byte random id> <payload>
token→ 21 … ack, then 8a <id> <data>
app  → 09 <id> 20 <32 bytes>      about once per second
token→ 89 …                        reply
```

It is an attestation handshake: the replies are computed from a key locked
behind the chip's readout protection, so the app can tell a real token from an
emulator before it accepts a score. Nobody has reproduced it. The integration
does not need it: the IMU stream runs without it. Do not send `0a` with
arbitrary data: on the development unit the token stopped notifying until the
link was re-established (Flopsstuff lists `0a` among the opcodes that soft-reset
the token).

## Timing observed on hardware (firmware 3.2.1-A)

| What | Value |
|---|---|
| Connect through an ESPHome proxy at −68 dBm | 0.1–0.3 s |
| Connect on a Raspberry Pi 5 adapter at −75 dBm | 1.5–10 s, often fails |
| Frames at 52 Hz, good link | ~52 per second, 14 bytes each |
| Advertising after a dropped link | ~3 min |
| Sleep after the last activity with no link | a few seconds |

## Sources

- [Flopsstuff/triki](https://github.com/Flopsstuff/triki): BLE protocol and
  IMU streaming guides, the TrikiEmu emulator; the start and stop commands and
  the rate field come from there.
- [Maku-hub/TrikiScope](https://github.com/Maku-hub/TrikiScope): live IMU
  viewer; `trikiscope/protocol.py` documents the button bit in the status byte.
  [Maku-hub/TrikiEmu](https://github.com/Maku-hub/TrikiEmu): the HCI snoop
  analysis of the app (stop command, attestation handshake).
- [woofter-wolf/triki-library-python](https://github.com/woofter-wolf/triki-library-python):
  Python client library.
- [Piwencjusz/zabka-triki-hardware](https://github.com/Piwencjusz/zabka-triki-hardware)
  and [AND-Y0/TrikiReader](https://github.com/AND-Y0/TrikiReader): board,
  Device Information characteristics.
- Captures and btmon traces taken during development of this integration (see
  [Development](development.md) for the tools).

See [Hardware](hardware.md) for the token itself.
