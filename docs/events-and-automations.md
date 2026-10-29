# Events and automations

Every gesture is published twice: as a state change of the `event` entity and as
a bus event `triki_event`. Use whichever fits. The entity is easier in the UI;
the bus event carries `device_id` and `address` and is convenient for
device-independent automations.

## Event types

| `event_type` | Data | When |
|---|---|---|
| `wake` | | The token woke up and the link is established. Not emitted on a quick resume after a weak-signal drop. |
| `press` | `count: 1`; `source: wake` for synthetic presses | Button released (immediately, or after the multi-press window if that option is on). |
| `double_press`, `triple_press` | `count` | Multi-press option on. |
| `long_press` | | Button held for 0.8 s. Reported while still held; the release does not produce a `press`. |
| `rotate_cw`, `rotate_ccw` | `steps`, `degrees` | Turned around the vertical axis by at least one knob step. Several steps can arrive in one event after a fast turn. Muted while the button is down and for 0.8 s after release. |
| `shake` | | Several quick back-and-forth swings. One event per episode. |
| `tap`, `throw`, `flip` | | Motion gestures option. Uncalibrated. |

### Gesture status

What has been confirmed on hardware (firmware 3.2.1-A, through an ESPHome proxy
and a Raspberry Pi 5 adapter):

| Gesture | Status |
|---|---|
| wake, press, long press, double and triple press | Reliable. |
| rotate | Reliable with the token flat on a surface or held level. A press twists the token in the hand; those false rotations are filtered. |
| shake | Timed on the frames' arrival clock, so lost frames and the 26 Hz idle rate do not break it; one event per episode, the knob is muted while swinging. Synthetic data only so far: not yet confirmed on hardware through a proxy. |
| tap, throw, flip | Synthetic data only. |

## Bus event

```yaml
event_type: triki_event
data:
  device_id: 1a2b3c…
  address: C4:43:28:XX:XX:XX
  type: rotate_cw
  steps: 1
  degrees: 30.0
```

## Example: button toggles a light, knob dims it, long press for full warm white

This is the setup the integration was developed with. It is split into three
automations on purpose. A fast turn produces many `rotate` events per second; if
they queue up behind a slow light, presses get stuck in the queue. Giving the
rotation its own automation in `restart` mode means only the latest step is
acted on and presses are handled immediately.

```yaml
automation:
  - alias: "Triki: press toggles the ceiling light"
    mode: queued
    max: 3
    triggers:
      - trigger: state
        entity_id: event.triki_action
    conditions:
      - condition: template
        value_template: >-
          {{ trigger.to_state.state not in ['unavailable', 'unknown']
             and trigger.to_state.attributes.event_type == 'press' }}
    actions:
      - action: light.toggle
        target:
          entity_id: light.ceiling

  - alias: "Triki: knob dims the ceiling light"
    mode: restart
    triggers:
      - trigger: state
        entity_id: event.triki_action
    conditions:
      - condition: template
        value_template: >-
          {{ trigger.to_state.state not in ['unavailable', 'unknown']
             and trigger.to_state.attributes.event_type in ['rotate_cw', 'rotate_ccw'] }}
      - condition: state
        entity_id: light.ceiling
        state: "on"
    actions:
      - action: light.turn_on
        target:
          entity_id: light.ceiling
        data:
          brightness_step_pct: >-
            {{ 8 * (trigger.to_state.attributes.steps | default(1) | int)
               * (1 if trigger.to_state.attributes.event_type == 'rotate_cw' else -1) }}

  - alias: "Triki: long press = full warm white"
    mode: single
    triggers:
      - trigger: state
        entity_id: event.triki_action
    conditions:
      - condition: template
        value_template: >-
          {{ trigger.to_state.state not in ['unavailable', 'unknown']
             and trigger.to_state.attributes.event_type == 'long_press' }}
    actions:
      - action: light.turn_on
        target:
          entity_id: light.ceiling
        data:
          brightness_pct: 100
          color_temp_kelvin: 2700
```

## Example: double press cycles colour presets

```yaml
  - alias: "Triki: double press = next preset"
    mode: single
    triggers:
      - trigger: state
        entity_id: event.triki_action
    conditions:
      - condition: template
        value_template: >-
          {{ trigger.to_state.state not in ['unavailable', 'unknown']
             and trigger.to_state.attributes.event_type == 'double_press' }}
    actions:
      - variables:
          presets: [2700, 4000, 6500]
          current: "{{ state_attr('light.ceiling', 'color_temp_kelvin') | int(4000) }}"
          next: >-
            {% set ns = namespace(i=0) %}
            {% for k in presets %}{% if k == current %}{% set ns.i = loop.index %}{% endif %}{% endfor %}
            {{ presets[ns.i % presets | count] }}
      - action: light.turn_on
        target:
          entity_id: light.ceiling
        data:
          color_temp_kelvin: "{{ next }}"
```

## Example: triple press or shake starts a light effect

Looping effects should run as scripts in `restart` mode and stop themselves when
the light goes off. If several lamps are involved and one of them is slow (Wi‑Fi
bulbs often are), give every lamp its own loop instead of one group call per
step; otherwise the whole effect waits for the slowest lamp.

```yaml
  - alias: "Triki: triple press or shake toggles the police lights"
    mode: single
    triggers:
      - trigger: state
        entity_id: event.triki_action
    conditions:
      - condition: template
        value_template: >-
          {{ trigger.to_state.state not in ['unavailable', 'unknown']
             and trigger.to_state.attributes.event_type in ['triple_press', 'shake'] }}
    actions:
      - if:
          - condition: state
            entity_id: script.police_lights
            state: "on"
        then:
          - action: script.turn_off
            target:
              entity_id: script.police_lights
          - action: light.turn_on
            target:
              entity_id: light.ceiling
            data:
              color_temp_kelvin: 2700
              brightness_pct: 100
        else:
          - action: script.turn_on
            target:
              entity_id: script.police_lights
```

## Using the device trigger UI

The event entity works with the standard *State* trigger in the automation
editor. Pick the `event.<name>_action` entity, leave *to* empty, and add a
template condition on `trigger.to_state.attributes.event_type` as in the
examples above. The state of an event entity is the timestamp of the last event,
which is why the trigger fires on every gesture even when two identical gestures
follow each other.

## Tips

- Multi-press delays single presses by the window (0.3–0.5 s). If you do not use
  double or triple press, leave the option off and presses are instant.
- The press that wakes a sleeping token is reported as `wake`, not `press`. If
  you want the first press to count, enable *Treat wake-up as a press*.
- Holding the link (sleep timeout 0) makes the token react at any time but costs
  battery; see [Configuration](configuration.md#idle-and-sleep-how-the-link-behaves).
