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
`idle_timeout` seconds without motion or button activity it drops the link so the
token can sleep again.

## Entities

| Entity | Notes |
|---|---|
| `event.<name>_action` | `wake`, `press`, `double_press`, `triple_press`, `long_press`, `rotate_cw` / `rotate_ccw` (attrs `steps`, `degrees`), `shake`, `tap`, `throw`, `flip` |
| `binary_sensor.<name>_button` | live button state (only while connected) |
| `binary_sensor.<name>_connected` | diagnostic |
| `light.<name>_led` | green LED, only while connected |
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

- **Sample rate**: 26 / 52 / 104 / 208 Hz. 104 is what the Żappka app uses.
- **Idle timeout**: seconds without activity before disconnecting (0 = never).
- **Knob step**: degrees of rotation around the vertical axis per `rotate_*` event.
- **Invert rotation**: flip cw/ccw if it is backwards on your unit.

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

- Gesture thresholds and the rotation direction are tested against synthetic data,
  not tuned on hardware yet. Constants are at the top of `gestures.py`.
- The press that wakes the token happens before the link is up, so it shows up as
  `wake`, not `press`.
- A 104 Hz stream keeps the token awake and costs battery. Keep the idle timeout short.
- An ESPHome proxy has a limited number of active connection slots (3 by default).

## Development

```bash
pip install pytest-homeassistant-custom-component
pytest
```
