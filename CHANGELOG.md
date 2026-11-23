# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- The card's check has new steps: **Pick up and put down** (gestures that fire
  while the cap is picked up are reported as false), **Sleep and wake**
  (optional: drops the link as after idling, follows the doze and checks that
  a press wakes the cap). Shake now asks for three shakes and reports the
  misses, the lean for three each way.
- **Readiness** sensor: whether a press reaches Home Assistant now.
  *Connected*; *Dozing off: presses not seen* for about 3 minutes after an
  idle disconnect; *Asleep: a press wakes it*; *Not responding*. The card
  counts the dozing minutes down. A press while dozing starts them over, and
  the token's adverts do not change with it (checked on hardware), so the
  press itself cannot be caught.
- **Link quality** sensor: the share of motion frames that arrived in the last
  session. Three lossy sessions in a row (under 70 %) raise a repair issue
  with what to do; a clean one clears it.
- **Live 3D card**, `custom:triki-card`, served and registered by the
  integration: nothing to install, search for *Triki live 3D* when adding a
  card. See docs/live-card.md.
  - A 3D model of the token follows it: roll, pitch and yaw, gyro and
    accelerometer readings with a 10 s graph, button, battery, signal, stream
    rate and a label for each gesture.
    Orientation is computed in the integration (Madgwick filter) and goes
    over a websocket subscription (`triki/subscribe`), not into entity states.
  - The default model is our own, built from calipered dimensions, with
    photo textures; Flopsstuff's textured model (MIT) is `model: glb`.
  - Calibration: lay the token on the table with the dot above the Z away
    from you, and the model levels itself and points the same way. The logo
    angle on the metal side is matched once by eye; both are stored per token.
  - **Check** suggests settings when its results point to one (both turns the
    other way round, heavy frame loss, a double press that came as two, a
    gesture that fires by itself) and saves them with **Apply**.
  - **Check** (admins only): a guided walk through lying still (stream rate,
    lost frames, noise and the receiver the link goes through), level, tilt,
    knob turns each way, the presses, turning over and the gestures that are
    turned on. Each step has an instruction, a timer and live numbers, and
    ends with the likely cause when it fails ("19 % of frames lost, move it
    closer to the receiver"). The report folds out for an issue.
  - With several tokens, tabs: *Auto* follows the awake one, or pin one.
  - `show_controls: false` hides the buttons and the help, for a wall tablet.
  - English, Russian and Polish, picked from the Home Assistant language.
- `sensor.<name>_face_up`: which side is up (`cap_up`, `pcb_up` or `edge`), set
  once the token has lain still for 0.3 s and kept while it sleeps.
- `speed` (°/s) in `rotate_cw` / `rotate_ccw` events, so a fast turn can do
  more than a slow one.
- *Tilt in the hand* option, off by default: hold the token level and lean it
  right or left past 25° for `tilt_right` / `tilt_left`, one event and then
  one every 0.4 s while it stays leaned (`repeat: true`). Checked on hardware.
  Its own events, not the knob's (0.3.0b1 sent `rotate_cw` / `rotate_ccw`
  with `source: tilt`): picking the token up leans it, and a dimmer on the
  knob moved.
- Russian translation of the integration (setup, options, repairs, entity
  names).
- Diagnostics: `measured_rate`, `gyro_bias`, `link_via` (the receiver the
  link actually went through; the advert's source was reported before) and
  `shakes`, the 1.5 s of stream before each of the last three shakes.

### Changed
- The knob no longer turns when the token is picked up. Picking it up turns it
  mostly about other axes than the vertical; while that is so the knob does
  not count. In a labelled run, ten pick-ups made 2 knob steps instead of 24,
  and turns on the table kept 35 of 37 steps.
- The press that wakes the token arrives as `press` (with `source: wake`) right
  after `wake`: *Treat wake-up as a press* is on by default and existing installs
  are switched on once. Only the button wakes the token, so a wake from sleep is
  a press; it is left out when the token had not really slept (after a Home
  Assistant restart or a dropped link). An automation that used `wake` to catch
  the first press now gets a `press` as well: turn the option off or drop the
  `wake` trigger.
- The pitch and roll sensors are called *Tilt forward-back* and *Tilt
  left-right*, the names the card uses. Entity ids stay `_pitch` and `_roll`.
- One motion, one gesture: knob steps are held 0.3 s and dropped if the motion
  turns out to be a shake, a jolt or a fall. A shake used to fire two knob
  steps before it was recognised.
- The knob ignores turns with the token tilted more than 40° from level (was
  60°): knocking it edge-on against the table no longer turns it.
- Slow knob turns are counted: the knob follows rotation from 10 °/s (was
  15 °/s) and keeps a partial turn through 1 s pauses (was 0.6 s). A slow hand
  turn of one revolution used to report 8-10 of its 12 steps, now 11.
- Knob turns are integrated over the frames' arrival times instead of one
  sample period per frame: with half the frames lost the knob used to report
  half the steps.
- The gyro's zero offset is learned while the token lies still and subtracted
  from knob turns and the card's 3D model; it is kept across reconnects.
  "Still" means the readings spread by under 0.5 °/s over half a second, so a
  steady hand does not count, and an offset learned wrongly is replaced the
  next time the token lies on the table.
- For 30 s after Home Assistant starts, a token heard only through a local
  adapter waits for the Bluetooth proxies instead of connecting at once: the
  link used to go through the Pi's adapter at −85 dBm before the proxies had
  reported the token.
- Firmware that streams faster than requested no longer speeds up gesture
  timing (multi-press window, long press).

### Fixed
- A wake is a press only after real sleep. A silence sooner than ~3 minutes
  after a dropped link is adverts Home Assistant missed (a weak link, or the
  cap carried out of range and back): it no longer makes a press nobody
  pressed, and an idle-dropped cap is no longer reconnected while it dozes.
- Tilt in the hand counts leans up to 80° (was 60°): asked for more than 25°,
  people lean to 70-85°, and half the leans of a check went unseen.
- The check: closing the tab ends the check at once (the sleep step held it
  for 7 minutes); the multi-press window suggestion also comes when the double
  press made it on a retry.
- The card said *Dozing off* until the next wake-up, long after the token had
  fallen asleep.
- Saving the options right after an idle disconnect no longer links up to the
  dozing token for another session.
- Battery: a stream pause now reports its highest level, once. The token can
  send a low series (21-27 %) alongside the real one (82-94 %) during the
  pause; each value went to the sensor and the last one counted as the level
  at rest, so a pause ending on a low value could have turned on the battery
  saver and raised the low-battery notice on a healthy cell.
- Knob: a link that holds the stream back for a second or two and then
  delivers it at once no longer drops a partial turn.
- A token in its firmware-update bootloader (advertising as `TrikiDfu…`) is
  no longer offered as a new device.
- The LED switch keeps its last known state across Home Assistant restarts. It
  read unknown until the token next woke, which could take hours.
- Docs: the token wakes only on a button press, not on motion.
- Docs: the IMU axes in `docs/protocol.md`. +z points out of the green PCB (Ż)
  side, not the metal side. The status byte section says what is known.

## [0.2.5] - 2026-11-14

### Added
- Battery saver: with *Disconnect after idle* at 0, once a stream pause measures
  30 % or less the link is dropped after 300 s idle anyway, so the token can
  sleep. A link held around the clock empties a CR2032 in about a week, and the
  weak cell then locked the token up until it was pulled out.
- Repair issues: one while *Disconnect after idle* is 0, with a fix that sets it
  to 300 s; one asking for a new cell at 30 % or less at rest.
- Repair issue *stopped responding*: the link dropped on its own and the token
  has not advertised for a minute. A weak cell locks the token up this way
  (no advertising, the button dead until the cell is pulled); the notice says
  what to do and clears when the token is heard again. Diagnostics carry
  `unresponsive`.

### Changed
- Docs: install by searching the default HACS catalog for *Żabka Triki*; the
  custom repository route is the fallback.
- Docs: the README and Troubleshooting no longer recommend a sleep timeout of 0;
  they describe the trade-off between reacting at any time and battery life.
- Docs: a *Battery* section at the top of the README, with a note for those who
  installed 0.2.4 or earlier. Troubleshooting has the measurements behind it:
  on 14 Nov 2026 one cell at 18–21 % at rest locked up two different tokens
  four times with the default settings, 20–27 s into a session; neither token
  did it on a fresh cell.

- Docs: the README and the install guide say that the knob, double and triple
  press and shake are off until turned on in the options.

### Upgrade notice
- 0.2.4 and earlier told you to keep *Disconnect after idle* at 0. That holds
  the link around the clock and empties a CR2032 in about a week, and a weak
  cell can lock the token up. After updating, accept the repair notice that
  sets it to 300 s, and replace the cell if the *replace the battery* notice
  shows up.

## [0.2.4] - 2026-10-30

### Fixed
- Knob: a brisk turn lost half its steps. The IMU sits off the axis, so a fast
  spin reads up to 2 g and the lift filter reset the partial turn on every such
  frame; those frames are now skipped and the turn kept. The mute on every
  reversal within the shake window is gone. On the 29 Oct 2026 session the
  reported angle went from 65 % to 85 % on the table and from 45 % to 65–70 %
  between the fingers.
- Knob: a knock or a toss no longer makes rotation steps. A hard jolt, free
  fall or a shake drops the partial turn and mutes the knob for 0.5 s, a turn
  needs two frames (a garbage frame is not a step), and frames with the cap
  tilted past 60° are skipped.
- Tap: the 2.5 g threshold never saw a finger tap at 52 Hz and fired on every
  shake swing and catch instead. A tap is now a 0.7 g jump between frames on a
  token at rest, reported once it is still again.
- Shake fired while turning the token briskly between the fingers (three times
  in twenty seconds on hardware) and muted the knob each time. A frame whose
  rotation is mostly about gravity is a turn, not a swing, unless it comes with
  the linear shock of a real shake (over 2 g).

### Added
- A trimmed capture of the hardware session as a test fixture; the replay test
  scores every rule against it.

### Changed
- The config flow builds its forms with probatio, the schema library of the
  2026 cores, and falls back to voluptuous on the 2025 ones. No change in
  behaviour: the 2026 cores alias one to the other at runtime.
- The idle, battery and stream watchdog callbacks cancel their own timer
  first, so a callback invoked by hand cannot leave a timer behind.

### Development
- The pinned test toolchain is Home Assistant 2026.10 on Python 3.14; the
  compatibility matrix still runs 2025.8 on Python 3.13.

## [0.2.3] - 2026-10-29

### Fixed
- The battery pause took the first notification after STOP, which can still be
  the loaded figure (27 % at 3 s, the rested 82 % follows at 4–6 s). The pause
  now stays open for 3 s of quiet after a value and keeps the last one.

### Changed
- A restart or reload no longer shows the under-load battery figure (17–27 %)
  for the first minute: the sensor's last value seeds the device and the
  connect-time read is skipped.
- Picking the token up or putting it down no longer registers a rotation step
  (the knob ignores frames with the accelerometer more than 0.25 g off 1 g).
- Unload waits for a connect in flight and undoes it, so no link outlives the
  entry.
- CI: `compat` jobs run the suite against Home Assistant 2025.8 (the declared
  minimum) and the newest release, next to the pinned toolchain.
- Repository: full Contributor Covenant text; Discussions enabled and linked
  from the issue chooser; release notes come from the changelog only;
  `scripts/setup` falls back to `uv` when `python3.13` is not on PATH.

## [0.2.2] - 2026-10-29

### Changed
- **Breaking:** the LED is a `switch` with the *Configuration* category instead
  of a `light`, so it stays out of area light groups and "turn off all the
  lights" no longer wakes a sleeping token into an error. The entity id changes
  from `light.<name>_led` to `switch.<name>_led`; update automations and remove
  the orphaned `light` entity from the registry.
- `hacs.json` declares `country: PL` (the token is sold in Poland).

## [0.2.1] - 2026-10-29

### Fixed
- On Home Assistant 2026.10+ the token never reconnected after a sleep-timeout
  disconnect: the "wait until the token slept" gate judged the silence after
  refreshing its own mark, and without the 1 s poll nothing ever cleared it.
  The first advertisement after 15 s of silence is now taken as the wake-up.
  Affects 0.2.0 only, with a sleep timeout other than 0.

### Changed
- The *Motion gestures* option enables only `tap`, `throw` and `flip`; rotate
  and shake have their own switches and are no longer implied by it.
- A capture file stops at 50 MB with one warning, so a forgotten debug option
  cannot fill the disk; a new link starts a new file.
- Options read from a hand-edited store are sanitised (unknown rate, zero knob
  step or window, negative timeouts) instead of crashing the stream.
- RSSI state writes only when the value changed; platforms unload before the
  link is closed.
- Docs: shake status, entity availability and battery interval corrected;
  photo placeholders removed; obsolete `render_readme` dropped from `hacs.json`.

## [0.2.0] - 2026-10-29

### Added
- Integration icon and logo ship in `custom_components/triki/brand/`
  (Home Assistant 2026.3+ reads them from there; older versions show the
  icon once the domain is in `home-assistant/brands`).
- Polish translation.
- `quality_scale.yaml` recording the Integration Quality Scale status.
- Config flow: `data_description` for the device picker, knob step and
  inverted rotation; `already_in_progress` abort text.
- One info log line after three failed connect attempts in a row for an awake
  token, and one when it links again.
- `led_write_retries` link statistic in diagnostics.
- On Home Assistant 2026.10+ every advertisement of the token is delivered to
  the integration (`async_register_advertisement_callback`); the 1 s poll of
  the last advertisement remains for older cores. Diagnostics gain an `adverts`
  counter and an `advertisements` block with the cadence of the last 32 packets.
- Repository: `requirements_test.txt` (pinned, Dependabot), `pre-commit`
  config, `scripts/setup` and `scripts/check`, weekly scheduled CI, release
  notes grouped by label. Bandit and pip-audit jobs dropped (ruff's `S` rules
  and Dependabot alerts cover them); `hacs` is a required check.

### Changed
- A stale BlueZ link left by a previous Home Assistant process is closed when
  the entry loads.
- The LED write has a 5 s timeout and is retried up to three times on a GATT
  error. Turning the LED on while the token sleeps now raises
  `HomeAssistantError` (a device state, not invalid input).
- Gestures are timed on the frames' arrival clock instead of counting frames,
  so a lossy proxy link or the 26 Hz idle rate no longer stretches the
  multi-press, long-press and motion windows.
- Shake detector rewritten: share of hard-motion frames and gyro reversals
  within 0.8 s of wall time, one event per episode, knob muted while swinging.
  Tested at 104/52/26 Hz with 50–70 % synthetic frame loss and confirmed
  through an ESPHome proxy: one event per shake, no rotations while swinging.

### Fixed
- Battery level stuck at a low value (17–27 %) for whole sessions while the
  resting level was 82–100 %. The token measures its battery only while it is
  not streaming; the integration read it right after the connect, under load,
  and the 10-minute re-reads returned the same stale number. Now the value
  comes from the token's own notification after a short stream pause while it
  is idle (at the idle-rate switch, then at most every 30 min); the connect
  read is only used while no value is known.
- A slow reconnect right after a weak-signal drop was reported as a new `wake`
  (the gap was measured at the end of the connect, not at its start).
- A failed firmware or hardware revision read was never retried and could wipe
  the value stored in the device registry.
- Capture files could get batches out of order when two flushes overlapped.

## [0.1.0] - 2026-10-29

First usable version, tested on a real token through an ESPHome Bluetooth proxy
and a Raspberry Pi 5 built-in adapter.

### Added
- Documentation under `docs/`: the token (hardware, board and schematic,
  battery), protocol, installation, configuration, events and automations with
  worked examples, a beginner's guide to an ESPHome Bluetooth proxy, radio and
  placement, troubleshooting, diagnostics, architecture, development. README
  with photos (Flopsstuff/triki, MIT, stored in `docs/images/`).
- Repository: MIT license, contributing guide, code of conduct, security
  policy, issue and pull request templates, Dependabot, CODEOWNERS, a ruleset
  for `main`, release workflow that publishes `triki.zip` for HACS.
- Security workflow: Bandit, ruff security rules, zizmor, Gitleaks, pip-audit
  (informational), CodeQL. Actions pinned to commit SHAs, checkouts without
  persisted credentials, read-only CI permissions.
- Config flow with Bluetooth discovery (`Triki*` local name) and manual pick.
- Entities: `event` (wake, press, double/triple/long press, rotate, shake, tap,
  throw, flip), `binary_sensor` button and connected, `light` for the green LED,
  `sensor` battery, RSSI, pitch and roll.
- Bus event `triki_event` with `device_id`, `address` and `type`.
- Options: sample rate, idle timeout (low-rate stream), sleep timeout (link
  drop), knob step, inverted rotation, wake-as-press, multi-press and its
  window, opt-in gesture groups, raw capture.
- Diagnostics with link statistics and the last advertisement; adapter and proxy
  addresses are redacted.
- Config entry migration v1 → v2: a v1 `idle_timeout` (which dropped the link)
  becomes `sleep_timeout`.
- Tools: `tools/triki_probe.py` (scan, info, LED, record, guided capture) and
  `tools/replay.py` (re-run captures through the parser and gesture detector).
- CI: hassfest, HACS validation, ruff, mypy, pytest with 95 % coverage gate.

### Changed
- Idle no longer drops the link: the stream is re-started at 26 Hz over the live
  link and the first press or motion brings the configured rate back. A fresh
  link is slow and lossy for 10–20 s, so holding it is the cheaper path.
- Default sample rate 52 Hz (the Żappka app's rate); 104 Hz lost most frames on
  weak links.
- The knob is muted while the button is held and for 0.8 s after release: a
  press twists the token in the hand and produced 3–5 spurious rotate events.
- A rate switch over the live link no longer re-arms the start-up frame discard,
  so a press right after the switch is reported.

### Fixed
- Reconnect loop after an idle disconnect (the token keeps advertising for
  minutes after a link drop).
- Duplicate BlueZ notifications counted as separate frames.
- Wake reported again on a quick resume after a weak-signal drop.

[Unreleased]: https://github.com/elenium3/ha-triki/compare/v0.2.5...HEAD
[0.2.5]: https://github.com/elenium3/ha-triki/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/elenium3/ha-triki/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/elenium3/ha-triki/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/elenium3/ha-triki/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/elenium3/ha-triki/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/elenium3/ha-triki/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/elenium3/ha-triki/releases/tag/v0.1.0
