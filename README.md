# Żabka Triki for Home Assistant

Custom integration for the Żabka **Triki** BLE motion token (nRF52810 + LSM6DSL).
Uses Home Assistant's own Bluetooth stack, so it works with a local adapter **or an
ESPHome Bluetooth proxy** (`bluetooth_proxy: active: true`). No ESPHome firmware of
its own, no cloud.

Unofficial, not affiliated with Żabka Polska. The protocol comes from community
reverse engineering:
[Flopsstuff/triki](https://github.com/Flopsstuff/triki),
[Maku-hub/TrikiScope](https://github.com/Maku-hub/TrikiScope),
[woofter-wolf/triki-library-python](https://github.com/woofter-wolf/triki-library-python).

## How it works

The token sleeps a few seconds after it goes still and only advertises while awake.
The integration listens for its advertisements. When the token shows up (button
press or movement), it connects, reads battery/firmware, sends the IMU start command
(`20 10 00 D0 07 <rate LE16> 03`) and turns the 14-byte frames into events. After
`idle_timeout` seconds without motion or button activity the link stays up but the
stream is restarted at 26 Hz (a quarter of the radio traffic); the next press or
movement brings the configured rate back within a frame or two. Only after
`sleep_timeout` seconds of inactivity is the link dropped so the token can sleep.
A fresh link is slow and lossy for the first 10-20 s and the token then advertises
at full tilt for minutes, so keeping the link is the cheaper path.

## Entities

| Entity | Notes |
|---|---|
| `event.<name>_action` | `wake`, `press`, `double_press`, `triple_press`, `long_press`, `rotate_cw` / `rotate_ccw` (attrs `steps`, `degrees`), `shake`, `tap`, `throw`, `flip` |
| `binary_sensor.<name>_button` | live button state (off while the token sleeps) |
| `binary_sensor.<name>_connected` | diagnostic |
| `light.<name>_led` | green LED, last known state while asleep; can only be changed while connected |
| `sensor.<name>_battery` | read on connect and every 10 min; restored while asleep |
| `sensor.<name>_rssi`, `_pitch`, `_roll` | disabled by default; tilt is published at 1 Hz max |

Every event is also fired on the bus as `triki_event` with
`device_id`, `address`, `type` plus the event data.

## Install

HACS → Custom repositories → this repo (type *Integration*), or copy
`custom_components/triki` into `config/custom_components/`. Restart, then press the
green button. The token should be discovered. Otherwise use *Add integration →
Żabka Triki* while it is awake.

## Options

- **Sample rate**: 26 / 52 / 104 / 208 Hz (default 52). 104 is what the Żappka app
  uses; 52 is enough for the button and the knob and loses fewer frames on a weak link.
- **Idle timeout**: seconds without activity before the stream drops to 26 Hz over the
  live link (default 30, 0 = never).
- **Sleep timeout**: seconds without activity before the link is dropped and the token
  is let sleep (default 300, 0 = keep the link as long as the token holds it).
- **Knob step**: degrees of rotation around the vertical axis per `rotate_*` event.
- **Invert rotation**: flip cw/ccw if it is backwards on your unit.
- **Knob rotation** (default off): `rotate_cw` / `rotate_ccw` only.
- **Shake** (default off): several quick back-and-forth swings.
- **Motion gestures** (default off): shake, tap, throw, flip (plus rotate). Thresholds are not calibrated on hardware yet; enable to test.
- **Double and triple press** (default off): when off, `press` is reported as soon as the button is released; when on, it is delayed by the window below to tell single, double and triple apart.
- **Double/triple press window**: longest pause (0.2-1.5 s, default 0.5) between releasing and pressing again. A single press is reported this long after release. Multi-presses only work while the link is up; the press that wakes a sleeping token is lost to the wake-up.
- **Treat wake-up as a press**: also emit `press` right after `wake` (see Caveats). A wake caused by movement then looks like a press too.

## Example: knob dimmer + button toggle

```yaml
automation:
  - alias: Triki dimmer
    mode: queued
    triggers:
      - trigger: state
        entity_id: event.triki_xxxx_action
    actions:
      - choose:
          - conditions: "{{ trigger.to_state.attributes.event_type == 'press' }}"
            sequence:
              - action: light.toggle
                target: { entity_id: light.desk }
          - conditions: "{{ trigger.to_state.attributes.event_type in ['rotate_cw','rotate_ccw'] }}"
            sequence:
              - action: light.turn_on
                target: { entity_id: light.desk }
                data:
                  brightness_step_pct: >-
                    {{ (10 if trigger.to_state.attributes.event_type == 'rotate_cw' else -10)
                       * trigger.to_state.attributes.steps }}
```

## Caveats

- If the token accepts the connection but sends no frames within 3 s of the start command (seen once, start ack `21 01`; it recovered on its own), the integration drops the link and leaves the token alone for 60 s instead of reconnecting in a loop.
- Gesture thresholds and the rotation direction are tested against synthetic data,
  not tuned on hardware yet. Constants are at the top of `gestures.py`.
- The press that wakes the token happens before the link is up, so it shows up as
  `wake`, not `press`.
- The stream keeps the token awake and costs battery; the idle rate switch and the
  sleep timeout limit that. A held link also keeps the token from advertising, so the
  Żappka app cannot see it meanwhile.
- **Radio budget decides everything.** The token's antenna sits inside a bottle cap and
  is weak. Links were stable (hours) at an RSSI of about -65 dBm or better and lasted
  only seconds to a minute at -75 dBm, whatever the sample rate, connection interval or
  software did. Place the receiver where the token is used:
  - An ESPHome Bluetooth proxy (ESP32, `bluetooth_proxy: active: true`) at the usage
    spot connected in under a second and held the link for hours. This is the
    recommended setup.
  - A Raspberry Pi's built-in Bluetooth (Pi 5 tested) only works with the token right
    next to the Pi; across a room it connected in 1.5-10 s, often failed and lost the
    link within a minute.
- On a weak link the stream arrives with gaps of 0.3-3 s and 104 Hz delivered only
  7-18% of the frames; 26 Hz delivered about 78%, 52 Hz 20-74%. Lost frames make
  rotation read a little short; presses made during a gap show up late.
- An ESPHome proxy has a limited number of active connection slots (3 by default).

## Development

```bash
pip install pytest-homeassistant-custom-component
pytest
```
