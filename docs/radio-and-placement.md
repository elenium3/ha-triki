# Radio and placement

Where the receiver sits decides whether the token is a reliable remote or a
frustrating toy. Everything in this page was measured on one token (firmware
3.2.1-A) during development; your numbers will differ, the pattern will not.

## The token's radio is weak

The antenna is a small trace inside a plastic cap next to a coin cell and a
metal button spring. Compared with a phone the signal is roughly 10–15 dB
weaker. Link stability tracked signal strength and nothing else: not the sample
rate, not the connection interval, not the firmware of the adapter, not Wi‑Fi
load, not the temperature of the host.

| RSSI at the receiver | Link behaviour |
|---|---|
| −60 … −65 dBm | Stable for hours. |
| −68 … −72 dBm | Stable for an hour or more, occasional retransmits. |
| −75 dBm and below | Drops after seconds to a minute, regardless of settings. |

RSSI is shown on the device page once the `sensor.<name>_rssi` entity is enabled.
The *Diagnostics* download also contains the RSSI of the last advertisement.

## Recommended: an ESPHome Bluetooth proxy at the usage spot

An ESP32 running ESPHome with

```yaml
esp32_ble_tracker:
  scan_parameters:
    active: true
bluetooth_proxy:
  active: true
```

placed where the token is normally used (a desk, a bedside table) connected in
under a second and held the link for hours at −65 to −70 dBm. Home Assistant
uses the proxy transparently; nothing in this integration is proxy specific.

Notes:

- A proxy has a limited number of active connections (3 by default on an
  ESP32). The token takes one for as long as the link is held.
- If both a proxy and a local adapter see the token, Home Assistant picks the
  path with the best signal for each connection. Mixed paths work, but
  diagnostics are easier to read with one.
- An ESP8266 has no Bluetooth and cannot be a proxy.

## Built-in Raspberry Pi Bluetooth

A Raspberry Pi 5 (Cypress CYW43455) only gave a usable link with the token right
next to the board: across a room it connected in 1.5–10 s, often failed, and lost
the link within a minute at −75 dBm. With the token on the Pi's case (−62 dBm)
the link held for 47 minutes and more. The Pi's own radio is fine; the token's
is not, and the Pi usually lives far from where the token is used.

Two things that looked like causes and were not: host temperature (a Pi 5 at
79 °C without a fan throttled, a fan fixed that, and the drops stayed) and the
BlueZ notification duplicates described in [Troubleshooting](troubleshooting.md).

## Other single-board computers

Boards with a u.FL connector and no antenna attached (an Orange Pi Zero 3 was
tried) do not hear the token at all. Attach an antenna first.

## Sample rate versus link quality

On a weak link the stream arrives with gaps of 0.3–3 s:

| Rate | Frames delivered on a weak link |
|---|---|
| 26 Hz | about 78 % |
| 52 Hz | 20–74 % |
| 104 Hz | 7–18 % |

For the button and the knob 26–52 Hz is enough. Lost frames make a rotation read
a little short; presses made during a gap are reported late, not lost.
