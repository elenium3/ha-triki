# Configuration

All options live in Settings → Devices & services → Żabka Triki → *Configure*.
Changing any option reloads the entry, which drops and re-establishes the link.
The gestures (knob, multi-press, tilt, shake, motion gestures) are at the top
and are also offered when a cap is added; the rest are under *Advanced*,
folded, and start at their defaults.

## Options

| Option | Default | Meaning |
|---|---|---|
| Sensor rate | 52 Hz | Rate the token streams motion frames at: 26, 52, 104 or 208 Hz. 52 is what the Żappka app asks for. Higher rates are snappier but lose more frames on a weak link; see [Radio and placement](radio-and-placement.md). |
| Slow stream after idle | 30 s | After this long without motion or button activity the stream is re-started at 26 Hz over the live link. The button keeps working; any activity restores the configured rate within a frame or two. 0 = never. |
| Disconnect after idle | 300 s | After this long without activity the link is dropped so the token can sleep. 0 = keep the link as long as the token holds it; that empties a CR2032 in about a week, and while the battery is at 30 % or less 0 acts as 300 s. See the caveats below. |
| Knob step | 30° | Degrees of rotation around the vertical axis per `rotate_cw` / `rotate_ccw` event. Smaller steps mean more events per turn. |
| Invert knob direction | off | Swap cw and ccw if they read backwards on your unit. |
| Count the wake-up as a press | on | Only the button wakes the token, so the press that woke it is reported as `single_press` with `source: wake`, right after `wake`. It is left out when the token had not really slept (no advertisement for 15 s before it), for example after a Home Assistant restart or a dropped link, so nothing toggles by itself. If the button is still held when the stream starts, the stream reports that press itself. Turn it off if your automations already use `wake` to catch the first press. |
| Knob | off | Enable `rotate_cw` / `rotate_ccw`. |
| Shake | off | Enable `shake`. Confirmed through a proxy; see [Events](events-and-automations.md#gesture-status). |
| Tilt in the hand | off | Hold the token level, with the yellow stripe of the card's model towards you, and lean it right or left by more than 25°: one `tilt_right` or `tilt_left`, then one every 0.4 s while it stays leaned (`repeat: true`). These are not knob events, so picking the token up does not move a dimmer on the knob. Bring it back within 10° of level before the next lean. |
| Motion gestures | off | Enable `tap`, `throw`, `flip`. Tuned on one hardware session; see [Events](events-and-automations.md#gesture-status). |
| Double and triple press | off | Off: `single_press` is reported the moment the button is released. On: single presses are delayed by the window below so that a double or triple press (`multi_press` with `press_count`) can be told apart. |
| Multi-press window | 0.5 s | Longest pause between releasing and pressing again that still counts as a multi-press. From 0.2 to 1.5 s: shorter makes a single press quicker, longer makes a double press easier. The card's **Check** measures your double press and offers a value. |
| Record raw sessions | off | Write every session to `<config>/triki_captures/*.jsonl`: raw notifications, detected events, rate switches. For debugging and for tuning gestures with `tools/replay.py`. Turn it off when done. A file stops at 50 MB; a new link starts a new file. |

## Idle and sleep: how the link behaves

```
press ──► advertise ──► connect ──► stream at <sample rate>
                                         │
                       no activity for <idle timeout>
                                         ▼
                                  stream at 26 Hz (link up, button works)
                                         │
                       no activity for <sleep timeout>
                                         ▼
                                  link dropped ──► token advertises ~3 min ──► sleeps
```

Keeping the link is cheaper than it looks: a fresh link is slow and lossy for
the first 10–20 s, and after a drop the token advertises at full power for about
three minutes before it finally sleeps. The 26 Hz idle stream is a quarter of the
radio traffic of 104 Hz.

**Caveat on the sleep timeout.** After the integration drops the link it waits
for the token's advertisements to stop for 15 s before it will connect again.
That is what prevents a reconnect loop (reconnecting resets the token's own
sleep timer). But the token keeps advertising for minutes after a drop and every
press restarts that period, so presses made in that window are ignored. If you
want the token to react at any time, set the sleep timeout to 0 and accept the
battery cost of a permanently held link. See
[Troubleshooting](troubleshooting.md#presses-ignored-after-a-sleep-disconnect).

**The cost of 0.** A held link keeps the token awake around the clock: the
7.5 ms connection and the IMU draw roughly 1 mA, so a fresh CR2032 lasts about a
week instead of months. On the development unit, held around the clock, the
level measured in the stream pauses went from 25 % to 16 % over two days, and
twice, at the end of a 7 and a 21 hour link, the token locked up: no
advertising, the button dead, until the cell was pulled out
([Troubleshooting](troubleshooting.md#the-token-stops-responding-and-only-a-battery-pull-brings-it-back)).
So the integration guards the setting:

- With the sleep timeout at 0 a repair issue is raised (*Settings → System →
  Repairs*); its fix sets the timeout to 300 s.
- **Battery saver:** once a stream pause measures 30 % or less, 0 acts as
  300 s until Home Assistant restarts or the entry reloads, so the token
  sleeps between uses. The log says so once at info level.
- At 30 % or less at rest a second repair issue asks for a new cell. It clears
  once a pause measures 40 % or more. The threshold is this high because a
  cell at 18–21 % locked tokens up within seconds of connecting, also with the
  default sleep timeout.
- A token whose link drops on its own and that is not heard for a minute gets
  a third repair issue, *stopped responding*, with what to do. It clears when
  the token advertises again.
- Three sessions in a row that got less than 70 % of their motion frames
  (sessions with 20 s of stream or more count) raise *loses much of its
  stream*: move the receiver closer, add a proxy or lower the rate. It clears
  after a session with 90 % or more. The count starts over when Home
  Assistant restarts.

**Battery figure on a held link.** The token measures its cell under the load of
the open link. After a night asleep it reported 82 %; after 17 hours of a held
link every pause gave 25–27 %, a fresh link included. Part of that is the
loaded voltage, but on a link held for days the figure kept falling until the
token locked up: treat a low figure on a held link as a real warning.

## Entities

| Entity | Category | Notes |
|---|---|---|
| `event.<name>_action` | | Every gesture. Attributes: `event_type`, plus `steps`, `degrees` and `speed` for rotation, `position` for rotation, `press_count` for a double or triple press, `source: wake` for the press that woke the token, `repeat` for *Tilt in the hand*. |
| `binary_sensor.<name>_button` | | Live button state. Off while the token sleeps. |
| `binary_sensor.<name>_connected` | diagnostic | Link state. |
| `number.<name>_knob_position` | | Where the knob stands, 0 to 100 %: one full turn covers the range, it stops at the ends and is kept across restarts. Settable, so an automation can put a lamp's brightness in. Exists while the knob is on. |
| `switch.<name>_led` | Configuration | The green LED, as on and off buttons: the token cannot report it, so the state is what Home Assistant set during the current link and unknown after it. Can only be changed while linked. |
| `sensor.<name>_battery` | diagnostic | The token measures its battery only while it is not streaming, so the integration stops the stream for a few seconds while the token is idle (first at the idle-rate switch, then at most every 30 min) and takes the value the token pushes. Values the token reports on its own while streaming are taken under load and ignored. The first value after setup is read at the connect and is low (taken under load) until the first pause. Restored across restarts. |
| `sensor.<name>_readiness` | | Whether a press reaches Home Assistant now: `connected`; `dozing` for about 3 minutes after an idle disconnect, while presses are not seen and each one starts the 3 minutes over; `asleep`, a press wakes it; `not_responding`, the link dropped by itself and the token has been silent since. |
| `sensor.<name>_link_quality` | diagnostic | Motion frames that arrived in the last session, % of those the token streamed (rate switches included). Sessions with less than 20 s of stream are not counted. Restored across restarts. |
| `sensor.<name>_signal_strength` | diagnostic, disabled | Signal of the last advertisement as seen by the scanner that received it. |
| `sensor.<name>_face_up` | | Which side is up: `cap_up` (metal), `pcb_up` (green board) or `edge`. Set once the token has lain still for 0.3 s; between flat and on edge (z 0.5-0.8 g) the last value stays. Published at most once per second, restored across restarts and kept while the token sleeps. |
| `sensor.<name>_tilt_left_right`, `_tilt_forward_back` | disabled | The lean to the side and the lift of the dot edge, in degrees from the gravity estimate, published at most once per second. *Tilt forward-back* reads about ±180° while the token lies metal side up. On installs made before 0.3.0 the entity ids are `_pitch` (left-right) and `_roll` (forward-back). |

Disabled entities can be enabled from the entity settings. They are off by
default because they update often and fill the recorder.
