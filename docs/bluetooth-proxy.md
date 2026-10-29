# Bluetooth proxy for beginners

The token has a weak radio, and the computer that runs Home Assistant usually
sits in a cupboard far from where you use the token. A **Bluetooth proxy** is a
cheap little board that listens for Bluetooth where the token actually is and
forwards everything to Home Assistant over Wi‑Fi. Home Assistant then treats it
like a Bluetooth adapter plugged into the server. Nothing in this integration
needs to be configured for it; it just works through whatever adapters and
proxies Home Assistant has.

This page explains what you need, how to flash it, and where the two lines
`active: true` that the rest of the docs keep mentioning go.

## What to buy

Any **ESP32** development board with Wi‑Fi and Bluetooth. Examples that are
known to work as proxies (all a few euros):

| Board | Notes |
|---|---|
| ESP32-WROOM-32 dev board ("ESP32 DevKit", "NodeMCU-32S") | The classic. USB cable, done. |
| ESP32-C3 or ESP32-S3 mini boards | Smaller, same job. |
| M5Stack Atom Lite | Tiny, in a case, USB‑C. A popular ready-made proxy. |
| Olimex ESP32-POE | If you have Ethernet where the token lives. |

Not suitable: **ESP8266** (no Bluetooth at all), Arduino boards, Raspberry Pi
Pico W (no ESPHome Bluetooth proxy support).

You also need a USB cable, a Wi‑Fi network with 2.4 GHz (ESP32 does not do
5 GHz), and a spot for the board within a metre or two of where the token is
used, for example on the desk or the bedside table.

## Flash it: the easy way

ESPHome publishes ready-made proxy firmware you can flash from a browser, no
install required.

1. Open <https://esphome.github.io/bluetooth-proxies/> in **Chrome** or **Edge**
   (Firefox and Safari cannot flash over USB).
2. Plug the ESP32 into the computer, pick your board on the page, click
   *Connect*, choose the serial port that appeared, click *Install*.
3. When it asks, enter your Wi‑Fi name and password.
4. Within a minute Home Assistant shows a notification: *New device discovered:
   ESPHome*. Click *Configure* and add it.

That is it. The firmware from that page already has the proxy enabled in
*active* mode.

## Flash it: with the ESPHome add-on

If you already use ESPHome, or you want to use the board for other things too
(a temperature sensor, a display), make a device in the ESPHome dashboard with
this configuration:

```yaml
esphome:
  name: triki-proxy          # the name Home Assistant will show
  friendly_name: Triki proxy

esp32:
  board: esp32dev            # change to your board, e.g. m5stack-atom, esp32-c3-devkitm-1
  framework:
    type: esp-idf            # recommended for Bluetooth proxies

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password

api:                          # how Home Assistant talks to the board
  encryption:
    key: !secret api_key      # generate one in the dashboard or with `openssl rand -base64 32`

ota:
  - platform: esphome
    password: !secret ota_password

logger:

# ---- the part that matters for Triki ----
esp32_ble_tracker:
  scan_parameters:
    active: true              # ask devices for their name; needed to see "Triki ..."

bluetooth_proxy:
  active: true                # allow Home Assistant to CONNECT through this board, not only listen
```

The two `active: true` lines are what every other page refers to:

- `esp32_ble_tracker.scan_parameters.active: true` makes the board do *active
  scanning*, which is how it learns the token's name.
- `bluetooth_proxy.active: true` lets Home Assistant open connections through
  the board. Without it the proxy only relays advertisements and the
  integration can see the token but never connect to it.

`!secret` values live in the dashboard's `secrets.yaml` (top-right menu →
*Secrets*). Put the real Wi‑Fi password there, not in the device file.

Click *Install*, choose *Plug into this computer* for the first flash, later
updates go over the air. Then add the discovered ESPHome device in Home
Assistant as above.

## Check that it works

1. Settings → Devices & services → **ESPHome** → your proxy. The device should
   be *online*.
2. Settings → Devices & services → **Bluetooth** → ⋮ → *Download diagnostics*.
   In the JSON, under `manager.scanners`, there should be an entry with
   `"name": "triki-proxy (…)"` and `"connectable": true`.
3. Press the token's button next to the proxy. In the Triki device's
   diagnostics, `last_advertisement.source` is the proxy and `rssi` is around
   −60 to −70 dBm. Debug log lines read `advert via <proxy MAC> rssi -65`.

If the token shows up only with the server's own adapter, or with RSSI below
−75, move the proxy closer to where you press the token.

## Good to know

- One proxy can hold **three connections** at a time by default. The token
  takes one while linked.
- Several proxies are fine. Home Assistant picks the one with the best signal
  for each connection.
- The proxy is an ordinary ESPHome device: it updates over the air and can be
  combined with sensors or a display on the same board.
- Power: any USB charger. The board draws under 1 W.
- The official ESPHome documentation for the component is at
  <https://esphome.io/components/bluetooth_proxy.html>, and Home Assistant's
  page on remote adapters at
  <https://www.home-assistant.io/integrations/bluetooth/#remote-adapters-bluetooth-proxies>.
