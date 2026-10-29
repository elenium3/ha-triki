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
- The token advertises after a button press or motion, for a few seconds when
  woken from sleep and for about three minutes after a link is dropped. Then it
  sleeps and stops advertising completely.

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
soft reset of the token. The integration uses none of them.

Re-sending *Start* with another rate over a live link switches the rate without
a reconnect; the stream continues and the IMU does not re-settle. The
integration uses this for the idle rate.

## Motion frames (notifications on TX)

14 bytes, little-endian:

```
0x22 | status | gx gy gz | ax ay az
       bit0 = button pressed      int16 each
```

| Field | Scale | Full range |
|---|---|---|
| gyro | 14.286 LSB per °/s | ±2000 °/s |
| accel | 2048 LSB per g | ±16 g |

Axes are in the sensor frame: +z points out of the top (Ż logo side), so a token
lying flat reads +1 g on z. Some earlier tools used a gyro scale of 131 LSB per
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
