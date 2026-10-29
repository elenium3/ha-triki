# The token

<p align="center">
  <img src="images/triki-front.jpg" width="360" alt="Żabka Triki: the silver cap with the black T">
  <img src="images/triki-back.jpg" width="360" alt="Żabka Triki: the green board seen from below">
  <br>
  <sub>Photos: <a href="https://github.com/Flopsstuff/triki">Flopsstuff/triki</a>, MIT.</sub>
</p>

## What it is

**Triki** is a bottle-cap sized Bluetooth motion controller sold by the Polish
convenience chain Żabka. It was announced on 29 April 2026 as "the smallest game
controller in the world" for the *Strefa Gier* (game zone) inside the Żappka
loyalty app, where it drives small games (Snake, Ninja Frog, a boxing game, a
toss game, football) and earns loyalty points and discounts. After a pilot with
influencer codes it went on general sale on 8 June 2026 in all Żabka stores at
69.99 zł, with coupon prices down to a few złoty for active app users.
([Żabka press release](https://www.zabka.pl/triki-nowy-wymiar-rozrywki-w-zappce/),
[Wiadomości Handlowe](https://www.wiadomoscihandlowe.pl/retailtech-i-nowe-technologie/triki-w-zabce-najmniejszy-kontroler-gier-mobilnych-na-swiecie-juz-w-sprzedazy-2535657),
[Spider's Web](https://spidersweb.pl/2026/04/ten-maly-gadzet-to-hit-zabka-wymyslila-kontroler-na-nowo.html).)

The device is made by **Caps Apps** (brand HOPX), model **CAP001**; the firmware
reports itself as `3.2.1-A` on the unit this integration was developed with. It
has one button (the whole cap), a green LED and a 6-axis IMU. Nothing else:
no haptics, no speaker, no magnetometer.

Because the app only needs a stream of motion data and a button, the token is a
cheap, tiny, battery-powered BLE remote for anything else, which is what this
integration is for.

## Inside

| Part | What | Source |
|---|---|---|
| MCU | Nordic **nRF52810** (Cortex-M4, BLE 5), marking `N52810 QDAAE0` | [Flopsstuff hardware guide](https://github.com/Flopsstuff/triki/blob/main/docs/guide/hardware.md), [Piwencjusz/zabka-triki-hardware](https://github.com/Piwencjusz/zabka-triki-hardware) |
| IMU | ST **LSM6DSL**, 3-axis accelerometer + 3-axis gyroscope, I²C to the MCU, marking `SF 422` | same |
| Flash | Macronix MX25R8035F, 8 Mbit SPI NOR, used to stage OTA updates | same |
| Clock | 32 MHz crystal | Flopsstuff |
| Battery | CR2032 coin cell according to a press review; not confirmed by a teardown | [gsmonline.pl](https://gsmonline.pl/artykuly/sprawdzilismy-nowy-kontroler-triki-z-zabki) |
| Debug | SWD pads on the board; readout protection (APPROTECT) is enabled | Piwencjusz |
| Firmware updates | Nordic Secure DFU packages, signed and encrypted, delivered by the app | Piwencjusz |

The radio is the weak spot: a PCB antenna inside a plastic cap next to a coin
cell and the button's metal spring. See
[Radio and placement](radio-and-placement.md) for what that means in practice.

## Board, pinout and schematic

The images in this section are shown from
[Piwencjusz/zabka-triki-hardware](https://github.com/Piwencjusz/zabka-triki-hardware)
(Piwencjusz, with tsuki and AND-Y0). That repository has no license file, so
the pictures are linked, not copied into this one; all rights stay with the
authors. If they disappear, the originals are in that repository's `photos/`.

<p align="center">
  <img src="https://raw.githubusercontent.com/Piwencjusz/zabka-triki-hardware/main/photos/TIKIpinout.jpg" width="420" alt="The board with the 3V3, GND, nRESET, SWCLK and SWDIO pads marked">
  <br><sub>The board with the cap removed. The yellow part in the middle is the button, the small can next to it is the 32 MHz crystal, the big square chip is the nRF52810, the pads marked SWCLK / SWDIO / nRESET are the debug port. Photo: Piwencjusz.</sub>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/Piwencjusz/zabka-triki-hardware/main/photos/nrf.jpeg" width="300" alt="Microscope photo of the nRF52810 marking N52810 QCAAE0 2232AB">
  <br><sub>The nRF52810 under a microscope: marking <code>N52810 QCAAE0 2232AB</code>, date code 2022 week 32. Photo: Piwencjusz.</sub>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/Piwencjusz/zabka-triki-hardware/main/photos/schematic.png" width="760" alt="Reference schematic: LSM6DSL on I2C, nRF52810 with crystal, antenna, SWD, LED, button and SPI NOR">
  <br><sub>Reference schematic reconstructed from PCB tracing by Piwencjusz. Their own caveat is printed on it: it is a reference, not electrically verified, and some GPIO assignments may be wrong.</sub>
</p>

What the schematic says, in words: the LSM6DSL talks to the nRF52810 over I²C
(SDA on P0.05, SCL on P0.06, two interrupt lines on P0.09 and P0.10), the
SPI NOR flash hangs on P0.12 to P0.20, the LED and the button are on P0.28 and
P0.30, the 32 MHz crystal is on XC1/XC2, and the PCB antenna is on the ANT pin.
SWD is on the two pads next to the chip; it is useless without erasing the chip
because readout protection is on.

A KiCad version of the schematic is being drawn in
[DISKIMG/Triki-PCB](https://github.com/DISKIMG/Triki-PCB) (no license file
either; link only). Flopsstuff's
[hardware guide](https://github.com/Flopsstuff/triki/blob/main/docs/guide/hardware.md)
(MIT) covers the same parts from the firmware's point of view.

## Behaviour

- **Sleep.** The token sleeps whenever it is still and not connected. It wakes
  on a button press or on motion, advertises for a few seconds, and goes back to
  sleep if nobody connects.
- **One connection at a time.** While the Żappka app (or anything else) is
  connected, Home Assistant cannot see it, and vice versa.
- **After a link is dropped** it advertises for about three minutes before
  sleeping.
- **Battery.** On the development unit the level went from 84 % to 82 % over a
  night of continuous testing with the link held most of the time. No long-term
  figures yet.
- **Axes.** The sensor's +Z points out of the top (the Ż logo side), so a token
  lying flat reads +1 g on Z. Rotation around Z is what the knob gesture uses.

<p align="center">
  <img src="images/triki-axes.jpg" width="420" alt="The token with its X, Y and Z axes drawn in">
  <br><sub>Axes as the firmware reports them. Photo: <a href="https://github.com/Flopsstuff/triki">Flopsstuff/triki</a>, MIT.</sub>
</p>

## Opening it and the battery

The token is meant to be opened by the user: Żabka's own
[FAQ](https://triki.zabka.pl/#faq) says that an irregularly blinking LED or
frequent disconnects mean a weak battery and tells you to replace it "according
to the controller's manual" (that manual is not published online). The cell is
a **CR2032**
([gsmonline review](https://gsmonline.pl/artykuly/sprawdzilismy-nowy-kontroler-triki-z-zabki)),
the most common 3 V coin cell, sold everywhere.

How it is built, from the same review and the photos above: a classic steel
bottle cap with the electronics on a round board, and a translucent green
polypropylene part that closes the underside. Polypropylene was chosen because
it flexes without cracking, which is also what lets the cap act as a button.
In the photos the green part sits inside the crimped rim of the steel cap and
no screws are visible.

**What we have not verified:** the exact way to get the green part out without
marking it. Several short videos on TikTok show a battery swap, but none that
we could cite describes the technique in text, and the author of this project
has not opened their own token for a photo series yet. Until there is a
documented procedure with pictures (contributions welcome, see
[images/README.md](images/README.md)), the general rules for crimped coin-cell
enclosures apply: work on a soft surface, use a plastic spudger or a guitar
pick rather than a screwdriver, go around the rim in small steps instead of
prying at one point, and note which way the cell faces before lifting it out.

### When a power cycle helps

Pulling the cell for a few seconds and putting it back restarts the firmware
from scratch. It is the only reset the token has: there is no reset button,
and the app's "turn off" (a second press after wake-up, the LED blinks twice,
per the FAQ) is a software sleep, not a reset. Cases where a power cycle is the
right tool:

- The token advertises, Home Assistant connects, the start command is
  acknowledged, and no frames arrive (seen once during development; it
  recovered on its own after a minute, a power cycle would have been faster).
- The token stays connected to a phone that is no longer around, so Home
  Assistant never sees it advertise. Turning Bluetooth off on the phone is the
  cleaner fix; the cell works when the phone is not at hand.

A power cycle does not forget anything: the token has no pairing or bonding
with Home Assistant, and the integration keeps its options. What the firmware
itself keeps across a power cycle (name, calibration, if any) has not been
checked.

The things a power cycle does **not** fix: presses ignored right after a sleep
disconnect (that is the integration's post-drop gate, see
[Troubleshooting](troubleshooting.md#presses-ignored-after-a-sleep-disconnect)),
and a weak link (that is radio placement).

## Identification

Advertised name `Triki NNNNNNNNNN` (the ten-digit number is printed in the app
when pairing), Bluetooth address of the random static type, manufacturer data
with company id `0xFF00`. Device Information reports firmware and hardware
revisions; the integration shows them on the device page.

## Related projects

The protocol was reverse engineered by the community. This integration builds
on:

- [Flopsstuff/triki](https://github.com/Flopsstuff/triki) by Flopsstuff (MIT):
  the most complete documentation (BLE protocol, IMU streaming, hardware), a
  TypeScript controller library and sensor-fusion tools.
- [Maku-hub/TrikiScope](https://github.com/Maku-hub/TrikiScope) by Mateusz
  "Maku" Mączewski (MIT): terminal IMU viewer and the first description of the
  button flag; its sibling [TrikiEmu](https://github.com/Maku-hub/TrikiEmu)
  analysed an HCI snoop of the app.
- [woofter-wolf/triki-library-python](https://github.com/woofter-wolf/triki-library-python)
  by Woofter_Wolf (MIT): Python client library.
- [Piwencjusz/zabka-triki-hardware](https://github.com/Piwencjusz/zabka-triki-hardware)
  (Piwencjusz, tsuki, AND-Y0): board photos, pinout, flash and DFU analysis.
- [koksny/TRIKI-Control](https://github.com/koksny/TRIKI-Control) by Wojciech
  Górny (MIT): desktop control and a clear "how it works" write-up.
- [orionas97/triki_unofficial](https://github.com/orionas97/triki_unofficial)
  (MIT): another Home Assistant integration exposing raw sensors, button and LED.
  This project differs in being gesture-oriented (event entity, knob, presses)
  and in how it manages the link (idle rate, sleep handling, proxy-first).
- Also: [AND-Y0/TrikiReader](https://github.com/AND-Y0/TrikiReader) (C#),
  [CreoleVR/TrikiVR](https://github.com/CreoleVR/TrikiVR) (SlimeVR tracker),
  [Wojtekb30/unofficial-triki-api-py](https://github.com/Wojtekb30/unofficial-triki-api-py),
  [alex-so-3/find-my-triki](https://github.com/alex-so-3/find-my-triki),
  [DISKIMG/Triki-PCB](https://github.com/DISKIMG/Triki-PCB) (KiCad).

Triki, Żappka and Żabka are trademarks of their owners. This project is not
affiliated with Żabka Polska or Caps Apps.
