# Troubleshooting

Start with the diagnostics download (Settings → Devices → Żabka Triki → ⋮ →
*Download diagnostics*) and, for anything about timing, a debug log: *Enable
debug logging* on the same page, reproduce, *Disable* to get the file. Lines look
like

```
Triki 4190656753: advert via A0:DD:6C:02:B3:16 rssi -68 age 0.2s
Triki 4190656753: connected, streaming at 52 Hz (advert age 0.0s, link 0.1s, setup 0.2s: notify 0.1s, write 0.1s)
Triki 4190656753: event press {'count': 1}
Triki 4190656753: stream now 26 Hz (idle)
Triki 4190656753: not connecting: waiting for the token to sleep after an idle disconnect (source …)
```

## Not discovered

- Press the button right before adding. The token advertises only for a few
  seconds after a press.
- Make sure a scanner is in range. In the Bluetooth integration's diagnostics
  the token should appear under `discovered_devices_and_advertisement_data` of
  some scanner with a small `time_since_last_device_detection`.
- The name must start with `Triki`. Tokens whose name was changed by the app
  are not matched; add them manually with *Add integration*.

## Connects slowly or drops within a minute

Radio. See [Radio and placement](radio-and-placement.md). The debug log shows
the RSSI with every advertisement; below −72 dBm move the receiver, or add a
[Bluetooth proxy](bluetooth-proxy.md) where the token is used.

## Seen but never connects through a proxy

The proxy is in passive mode. Its ESPHome configuration needs
`bluetooth_proxy: active: true`; the ready-made firmware from
<https://esphome.github.io/bluetooth-proxies/> has it. In the Bluetooth
integration's diagnostics the proxy must show `"connectable": true`. See
[Bluetooth proxy for beginners](bluetooth-proxy.md#check-that-it-works).

## Presses ignored after a sleep disconnect

If *Disconnect after idle* is set, the integration drops the link after that
time and then refuses to reconnect until the token has stopped advertising for
15 s. The token keeps advertising for minutes after a drop, and every press
restarts that window, so presses in that period do nothing. The log shows
`not connecting: waiting for the token to sleep after an idle disconnect`.

Wait until the token sleeps (a few minutes without presses); the next press
then wakes it and connects. Setting *Disconnect after idle* to 0 avoids the
window altogether, but the link is then held around the clock and a CR2032
lasts about a week instead of months; the integration raises a repair issue for
0 (see [Configuration](configuration.md#idle-and-sleep-how-the-link-behaves)).
A proper fix needs a way to tell a press from post-drop advertising, which the
token's advertisement does not provide.

## A press produces rotate events

Fixed in 0.1.0: the knob is muted while the button is down and for 0.8 s after
release. If you still see it, the token was turned more than 30° within that
second; raise the knob step.

## Shake is not detected, or shows up as rotations

The detector wants about 0.8 s of hard swinging (peaks above 500 °/s, the
direction reversing at least twice) and judges it on the frames' arrival times,
so a lossy proxy link only delays the event. What still loses it:

- The token was idle (26 Hz) and the link drops most frames: fewer than ~8
  frames per second reach the detector, and a short shake may not show two
  reversals. Shake longer, or raise the idle timeout so the token streams at
  the configured rate when you pick it up.
- Swinging gently: moving the token around in the hand peaks at 160–580 °/s
  and is deliberately below the threshold.

While swinging, rotations are muted, so a shake must not appear as
`rotate_cw` / `rotate_ccw` any more. Captures of shakes that misbehave (see
[Development](development.md)) help.

## Automations lag or presses arrive late

Usually the automation, not the token. A fast turn of the knob produces many
events per second. If each one calls a slow light (Wi‑Fi bulbs can take
0.4–7 s per command), a `queued` automation builds a backlog and presses wait
behind rotations, or hit *Maximum number of runs exceeded*. Split rotation into
its own automation in `restart` mode and keep the knob step at 30° or more. See
[Events and automations](events-and-automations.md).

## The token accepts the connection but sends no frames

Seen once: start acknowledged with `21 01`, no frames. The integration drops the
link and leaves the token alone for 60 s instead of reconnecting in a loop. It
recovered on its own. If it does not, pull the battery for a few seconds; see
[Opening it and the battery](hardware.md#opening-it-and-the-battery).

## The token stops responding and only a battery pull brings it back

The link drops on its own, the token stops advertising, and pressing the button
does nothing until the CR2032 is taken out for a few seconds and put back. Home
Assistant shows the repair notice *… stopped responding* a minute after such a
drop; it clears when the token is heard again.

What was measured:

- **14 Nov 2026, default settings (*Disconnect after idle* 300 s).** One cell
  that read 18–21 % at rest locked up two different tokens four times. Each
  time the link dropped 20–27 s into a session, while the stream still ran at
  52 Hz; in the one session that was recorded the token lost frames for the
  last six seconds before the drop. The same two tokens on a fresh cell went
  through about twenty sessions without a single lock-up. With the weak cell
  it is irregular: three times in the first eight sessions, then not once in
  twenty-three, then again a few sessions later.
- **October 2026, *Disconnect after idle* at 0.** After links of 7–21 hours the
  token dropped the link and was gone; the level in the stream pauses was
  16–19 % and falling.

So the common factor is the cell, not one token, the radio path or how long
the link was held. A worn coin cell's internal resistance rises, every radio
transmission pulls its voltage down, and an nRF52 that browns out this way can
reset in a loop or freeze until its power is removed
([Nordic DevZone](https://devzone.nordicsemi.com/f/nordic-q-a/116224/voltage-drop-triggers-bor-reset-mcu-occasionally-completely-freezes)).
Pulling the cell clears the freeze and lets the cell recover a little, which is
why it helps for a while. Żabka's FAQ says the same in short: an irregular LED
or frequent disconnects mean a weak battery. What exactly trips it on a given
session is not known.

What to do:

- Take the cell out for a few seconds to get the token back, then **replace
  it**; a recovered weak cell locks up again.
- Replace the cell when the *replace the battery* notice appears (30 % or less
  at rest), before it gets this far.
- Keep *Disconnect after idle* at a non-zero value so the token sleeps between
  uses; at 0 a fresh cell is empty in about a week. See
  [Configuration](configuration.md#idle-and-sleep-how-the-link-behaves).

The *stopped responding* notice also appears when a token is carried out of
range while connected. Press it next to the receiver: if it connects, it was
only out of range.

If it happens on a fresh cell, check before pulling it, because the pull
wipes the evidence: does the LED blink on a press; does a phone (nRF Connect)
see `Triki …`; does a restart of the ESPHome proxy bring it back (a proxy that
still holds the link would explain it too). Then measure the cell with a
multimeter.

## The token never advertises

Something else holds the link, usually a phone with the Żappka app that is
still in range: the token accepts one connection at a time and does not
advertise while connected. Turn Bluetooth off on the phone or close the app.
A battery pull also drops that link.

## Duplicate notifications on a local adapter

On BlueZ every notification can arrive several times (up to 12 copies per frame
were seen, growing with each reconnect) and the number of D‑Bus connections
grows with it. The integration de-duplicates identical chunks closer than 3 ms,
so events are correct; the link statistics in diagnostics count the duplicates
(`notifications` much higher than `frames`). Restarting Home Assistant resets
it. Not seen through a proxy.

## Light effects out of sync

Not this integration, but it comes up when the token drives several lamps: a
group call waits for the slowest lamp, and a lamp on bad Wi‑Fi can take seconds.
Give every lamp its own loop (one script instance per lamp) and avoid
`transition` on bulbs that ignore it.

## Reporting

Open a [bug report](https://github.com/elenium3/ha-triki/issues/new/choose) with
the diagnostics JSON and the debug log. Addresses are redacted in diagnostics;
the log contains the token's name and the scanner addresses.
