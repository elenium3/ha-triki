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
