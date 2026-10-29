<p align="center">
  <img src="docs/images/icon.png" width="128" alt="Żabka Triki">
</p>

<h1 align="center">Żabka Triki for Home Assistant</h1>

<p align="center">
  Turn the Żabka <b>Triki</b> game token into a Bluetooth remote: button, knob, gestures.<br>
  Local push, no cloud, works with a local adapter or an ESPHome Bluetooth proxy.
</p>

<p align="center">
  <a href="https://github.com/elenium3/ha-triki/actions/workflows/ci.yml"><img src="https://github.com/elenium3/ha-triki/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/elenium3/ha-triki/releases"><img src="https://img.shields.io/github/v/release/elenium3/ha-triki?include_prereleases" alt="Release"></a>
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-custom-41BDF5.svg" alt="HACS custom"></a>
  <img src="https://img.shields.io/badge/Home%20Assistant-2025.8%2B-blue" alt="Home Assistant 2025.8+">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/elenium3/ha-triki" alt="MIT"></a>
</p>

---

<p align="center">
  <img src="https://raw.githubusercontent.com/Flopsstuff/triki/main/assets/1.jpg" width="300" alt="The Triki token">
  <br><sub>The token. Photo: <a href="https://github.com/Flopsstuff/triki">Flopsstuff/triki</a>, MIT.</sub>
</p>

**Triki** is a bottle-cap sized motion controller that Żabka, the Polish
convenience chain, sells for games inside its Żappka app. Inside: an nRF52810
Bluetooth chip, an LSM6DSL accelerometer/gyroscope, one button, one green LED
and a coin cell. The app only needs a stream of motion frames and the button
state, so the token works just as well as a tiny, cheap remote for Home
Assistant. [More about the device →](docs/hardware.md)

## Features

- **Discovery** by name, pairing is just a button press.
- **Button**: press, double and triple press, long press, live button state.
- **Knob**: turn it on the table for `rotate_cw` / `rotate_ccw` with step and
  degrees. Dim a light, scroll a playlist.
- **Gestures** (opt-in, experimental): shake, tap, throw, flip.
- **Event entity** plus a bus event `triki_event` for every gesture.
- **LED** as a light entity, **battery**, **RSSI**, **tilt** sensors.
- **Battery-aware link**: the stream drops to 26 Hz when the token is idle and
  comes back on the first touch; the link is dropped after a longer idle.
- **Diagnostics** with link statistics, **raw capture** option for debugging,
  config entry migration, 95 %+ test coverage, strict typing.

## Quick start

1. Install through HACS (custom repository `elenium3/ha-triki`, type
   *Integration*) or copy `custom_components/triki` to your config. Restart.
2. Press the token's button. Home Assistant discovers *Żabka Triki*; confirm.
3. Put the Bluetooth receiver where the token is used. An ESPHome proxy
   (`bluetooth_proxy: active: true`) next to the desk or bed connects in under
   a second; a Raspberry Pi across the room does not. This matters more than
   any setting. [Why →](docs/radio-and-placement.md)
4. Automate on `event.<name>_action`:

```yaml
automation:
  - alias: "Triki: press toggles the desk lamp"
    triggers:
      - trigger: state
        entity_id: event.triki_action
    conditions:
      - "{{ trigger.to_state.attributes.event_type == 'press' }}"
    actions:
      - action: light.toggle
        target:
          entity_id: light.desk
```

Knob dimming, long press, double-press presets and a light-effect toggle are in
[Events and automations](docs/events-and-automations.md).

## Entities

| Entity | Notes |
|---|---|
| `event.<name>_action` | `wake`, `press`, `double_press`, `triple_press`, `long_press`, `rotate_cw` / `rotate_ccw` (`steps`, `degrees`), `shake`, `tap`, `throw`, `flip` |
| `binary_sensor.<name>_button` | live button state, off while asleep |
| `binary_sensor.<name>_connected` | diagnostic |
| `light.<name>_led` | the green LED; changeable only while connected |
| `sensor.<name>_battery` | read on connect and every 10 min |
| `sensor.<name>_rssi`, `_pitch`, `_roll` | disabled by default |

## Documentation

| Page | |
|---|---|
| [The token](docs/hardware.md) | what it is, what is inside, how it behaves, related projects |
| [Installation](docs/installation.md) | HACS, manual, adding the token |
| [Configuration](docs/configuration.md) | every option, idle and sleep behaviour, entities |
| [Events and automations](docs/events-and-automations.md) | event reference, gesture status, worked examples |
| [Radio and placement](docs/radio-and-placement.md) | measured link behaviour versus signal, proxy versus local adapter |
| [Troubleshooting](docs/troubleshooting.md) | symptoms, causes, what to attach to a bug report |
| [Diagnostics](docs/diagnostics.md) | the diagnostics download, debug log, capture format |
| [Protocol](docs/protocol.md) | GATT, commands, frame format, what the app does that we do not |
| [Architecture](docs/architecture.md) | how the integration is built and why |
| [Development](docs/development.md) | setup, tests, tools, releasing |
| [Changelog](CHANGELOG.md) | |

## Known limitations

- Presses within the first few minutes after an idle disconnect are ignored
  while the token still advertises; set the sleep timeout to 0 to avoid this at
  the cost of battery. See [Configuration](docs/configuration.md#idle-and-sleep-how-the-link-behaves).
- Shake is not reliably detected through a proxy yet; use triple press.
- Tap, throw and flip are tuned on synthetic data only.
- The integration icon appears only once the brand is accepted into
  [home-assistant/brands](https://github.com/home-assistant/brands); the files
  are prepared in `brands/triki`.

## Credits

The protocol is community work; this integration stands on:

- [Flopsstuff/triki](https://github.com/Flopsstuff/triki) by Flopsstuff (MIT):
  protocol, IMU and hardware guides, photos.
- [Maku-hub/TrikiScope](https://github.com/Maku-hub/TrikiScope) and
  [TrikiEmu](https://github.com/Maku-hub/TrikiEmu) by Mateusz "Maku" Mączewski
  (MIT): the button flag, the HCI snoop analysis of the app.
- [woofter-wolf/triki-library-python](https://github.com/woofter-wolf/triki-library-python)
  by Woofter_Wolf (MIT).
- [Piwencjusz/zabka-triki-hardware](https://github.com/Piwencjusz/zabka-triki-hardware),
  [koksny/TRIKI-Control](https://github.com/koksny/TRIKI-Control) by Wojciech
  Górny (MIT), [orionas97/triki_unofficial](https://github.com/orionas97/triki_unofficial)
  (MIT, another Home Assistant integration with a sensor-oriented design).

Built on Home Assistant's [Bluetooth stack](https://www.home-assistant.io/integrations/bluetooth/),
[bleak](https://github.com/hbldh/bleak) and
[bleak-retry-connector](https://github.com/Bluetooth-Devices/bleak-retry-connector).

## License

[MIT](LICENSE). Triki, Żappka and Żabka are trademarks of their owners. This
project is not affiliated with Żabka Polska or Caps Apps, and using the token
outside the app is at your own risk.
