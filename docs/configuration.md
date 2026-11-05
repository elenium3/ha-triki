# Configuration

All options live in Settings → Devices & services → Żabka Triki → *Configure*.
Changing any option reloads the entry, which drops and re-establishes the link.

## Options

| Option | Default | Meaning |
|---|---|---|
| IMU sample rate | 52 Hz | Rate the token streams motion frames at: 26, 52, 104 or 208 Hz. 52 is what the Żappka app asks for. Higher rates are snappier but lose more frames on a weak link; see [Radio and placement](radio-and-placement.md). |
| Low-power stream after idle | 30 s | After this long without motion or button activity the stream is re-started at 26 Hz over the live link. The button keeps working; any activity restores the configured rate within a frame or two. 0 = never. |
| Disconnect after idle | 300 s | After this long without activity the link is dropped so the token can sleep. 0 = keep the link as long as the token holds it; that empties a CR2032 in about a week, and while the battery is at 30 % or less 0 acts as 300 s. See the caveats below. |
| Knob step | 30° | Degrees of rotation around the vertical axis per `rotate_cw` / `rotate_ccw` event. Smaller steps mean more events per turn. |
| Invert rotation direction | off | Swap cw and ccw if they read backwards on your unit. |
| Treat wake-up as a press | off | The press that wakes a sleeping token ends before the link is up, so it is reported as `wake`. With this on, a `press` with `source: wake` is emitted after every `wake`, including wakes caused by movement. |
| Knob rotation | off | Enable `rotate_cw` / `rotate_ccw`. |
| Shake | off | Enable `shake`. Confirmed through a proxy; see [Events](events-and-automations.md#gesture-status). |
| Motion gestures | off | Enable `tap`, `throw`, `flip`. Tuned on one hardware session; see [Events](events-and-automations.md#gesture-status). |
| Double and triple press | off | Off: `press` is reported the moment the button is released. On: single presses are delayed by the window below so that `double_press` and `triple_press` can be told apart. |
| Double/triple press window | 0.5 s | Longest pause between releasing and pressing again that still counts as a multi-press. 0.3 s is a good compromise between a quick single press and a comfortable double press. |
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
([Troubleshooting](troubleshooting.md#the-token-vanishes-after-a-night-and-only-a-battery-pull-brings-it-back)).
So the integration guards the setting:

- With the sleep timeout at 0 a repair issue is raised (*Settings → System →
  Repairs*); its fix sets the timeout to 300 s.
- **Battery saver:** once a stream pause measures 30 % or less, 0 acts as
  300 s until Home Assistant restarts or the entry reloads, so the token
  sleeps between uses. The log says so once at info level.
- At 20 % or less a second repair issue asks for a new cell. It clears once a
  pause measures 30 % or more.

**Battery figure on a held link.** The token measures its cell under the load of
the open link. After a night asleep it reported 82 %; after 17 hours of a held
link every pause gave 25–27 %, a fresh link included. Part of that is the
loaded voltage, but on a link held for days the figure kept falling until the
token locked up: treat a low figure on a held link as a real warning.

## Entities

| Entity | Category | Notes |
|---|---|---|
| `event.<name>_action` | | Every gesture. Attributes: `event_type`, plus `steps` and `degrees` for rotation, `count` for presses, `source: wake` for synthetic presses. |
| `binary_sensor.<name>_button` | | Live button state. Off while the token sleeps. |
| `binary_sensor.<name>_connected` | diagnostic | Link state. |
| `switch.<name>_led` | Configuration | The green LED. Last known state while asleep; can only be changed while linked. |
| `sensor.<name>_battery` | diagnostic | The token measures its battery only while it is not streaming, so the integration stops the stream for a few seconds while the token is idle (first at the idle-rate switch, then at most every 30 min) and takes the value the token pushes. Values the token reports on its own while streaming are taken under load and ignored. The first value after setup is read at the connect and is low (taken under load) until the first pause. Restored across restarts. |
| `sensor.<name>_rssi` | diagnostic, disabled | Signal of the last advertisement as seen by the scanner that received it. |
| `sensor.<name>_pitch`, `_roll` | disabled | Tilt in degrees from the gravity estimate, published at most once per second. |

Disabled entities can be enabled from the entity settings. They are off by
default because they update often and fill the recorder.
