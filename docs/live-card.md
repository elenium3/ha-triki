# Live 3D card

The integration ships a Lovelace card, `custom:triki-card`. It shows a 3D model
of the token that moves with the real one, the roll, pitch and yaw, the
gyroscope and accelerometer readings, a 10 s gyro graph, the button, battery,
signal and stream rate, and a short label for each gesture.

Nothing needs installing: the integration serves the card and loads it into the
frontend itself. After an update, reload the browser page once.

## Adding it

Edit a dashboard, add a card and search for **Triki live 3D**, or in YAML:

```yaml
type: custom:triki-card
device_id: 0123456789abcdef0123456789abcdef  # optional with a single token
title: Triki                                  # optional, defaults to the token's name
show_values: true                             # gyro and accelerometer bars
show_history: true                            # 10 s gyro graph
```

The token has to be awake for the model to move: press or shake it. While it
sleeps the card shows the last state greyed out.

**Several tokens.** Without `device_id` the card shows a row of tabs: **Auto**
and one per token, each with a dot that is green while the token streams. Auto
shows whichever token wakes up; a token's tab pins that one. The choice is kept
per browser. With `device_id` set the card shows that token only and no tabs.

**Calibration.** Press **Calibrate** with the token awake and follow three steps:
lay it flat with the metal side (the grey crown with the black sign) up, so it
reads level on that table; lift the edge the arrow points at in the picture of
the sign (the crown is crimped on at any angle, so the sign's angle is
measured); put it back metal side up with that edge pointing away from you
(heading 0).
The result is kept per token in its config entry. `triki/calibrate` with
`step: clear` forgets it.

**Models.** `model: cap` (the default) is a procedural model built from calipered
dimensions, in the sensor frame; its resin glows while the LED is on and sinks
while the button is held. `model: glb` uses Flopsstuff's textured model.

## How it works

- **Orientation** is computed in the integration (`orientation.py`): a Madgwick
  filter over the gyro and accelerometer, using the gyro offset the gesture
  detector learns while the token lies still. Tilt is held to gravity; the
  accelerometer is ignored while it reads far from 1 g (a swing or a tap).
- **Heading drifts.** There is no compass, so yaw is only the integrated gyro.
  **Zero heading** on the card makes the current heading 0. A new link starts
  level with yaw 0.
- **Data path:** the card subscribes over Home Assistant's websocket
  (`triki/subscribe`). The integration sends the pose and the last frame at up
  to 30 messages per second while a card is open, and nothing when none is.
  Motion is never written to entity states, so the recorder and the database
  are not touched.
- **3D:** [three.js](https://threejs.org/) (MIT), bundled as
  `frontend/triki-three.js`, loaded only when a card is on screen. Rendering
  stops while the card is off screen or the model is still.

## Websocket API

| Command | Fields | Reply |
|---|---|---|
| `triki/devices` | | `[{device_id, name}]` |
| `triki/subscribe` | `device_id` (optional with one token) | events: `status`, `motion`, `event` |
| `triki/reset_heading` | `device_id` (optional with one token) | |

`motion` carries `quaternion` (w, x, y, z, sensor frame, +z out of the logo
side), `euler` (roll, pitch, yaw in degrees), `gyro` (°/s, offset removed),
`accel` (g) and `button`.

## Model

The model is `triki_texture.glb` from
[Flopsstuff/triki](https://github.com/Flopsstuff/triki) (MIT), with its
textures resized to 1024 px WebP and the mesh quantized (6.2 MB to 0.4 MB) with
[glTF-Transform](https://gltf-transform.dev/):

```sh
npx @gltf-transform/cli optimize triki_texture.glb triki.glb \
  --compress quantize --texture-compress webp --texture-size 1024 --simplify false
```
