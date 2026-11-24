# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

Compared with 0.2.5. Upgrading from 0.3.0b1: tilt now sends `tilt_right` /
`tilt_left` (b1 sent `rotate_cw` / `rotate_ccw` with `source: tilt`), and some
option names changed (see Changed).

### Added

- **Live 3D card**, `custom:triki-card`, served and registered by the
  integration: nothing to install, search for *Triki live 3D* when adding a
  card. See docs/live-card.md.
  - A 3D model that follows the cap, gyro and accelerometer readings with a
    10 s graph, the button, battery, signal, link and stream rate. Orientation
    is computed in the integration (Madgwick filter) and sent over a websocket
    subscription (`triki/subscribe`), not through entity states.
  - A list of the gestures: each lights up when it fires, tap one to read how
    to make it, the ones turned off in the options are struck through.
  - **Calibrate** levels the model and matches the logo once per cap;
    **Align direction** points the model the way the cap lies.
  - **Check** (admins only) walks through lying still (frame loss, noise, the
    receiver in use), tilt, knob turns, presses, flipping, picking up, the
    enabled gestures and, optionally, sleep and wake. The model shows each
    move to make. A failed step names the likely cause ("19 % of frames lost,
    move it closer to the receiver"), and settings the results point to can be
    saved with one tap.
  - Every part can be hidden on its own (`show_model`, `chips`, `buttons`,
    `show_gestures`, `show_help`, `show_values`, `show_history`), from a
    translated visual editor. Several caps get tabs.
  - English, Russian and Polish, picked from the Home Assistant language.
- **Two blueprints** with one-click import: a light remote (press toggles, the
  knob dims, long press sets a brightness) and an action for each gesture.
- Adding a cap asks which gestures to turn on.
- *Tilt in the hand* option, off by default: hold the cap level and lean it
  right or left past 25° (up to 80°) for `tilt_right` / `tilt_left`, repeated
  every 0.4 s while it stays leaned (`repeat: true`).
- **Readiness** sensor: whether a press reaches Home Assistant now
  (*Connected*, *Dozing off* for about 3 minutes after an idle disconnect,
  when presses are missed, *Asleep*, *Not responding*).
- **Link quality** sensor: the share of motion frames that arrived in the last
  session. Three lossy sessions in a row (under 70 %) raise a repair issue
  with what to do.
- `sensor.<name>_face_up`: `cap_up`, `pcb_up` or `edge`, once the cap lies
  still.
- `speed` (°/s) in knob events, so a fast turn can do more than a slow one.
- Russian translation of the integration.
- Diagnostics: `measured_rate`, `gyro_bias`, `link_via` (the receiver the
  link went through) and the stream before each of the last three shakes.

### Changed

- The knob:
  - It no longer turns while the cap is picked up or handled. Ten pick-ups
    made 2 knob steps instead of 24, and turns on the table kept 35 of 37.
    After the cap goes edge-on it stays off until it lies still again.
  - Slow turns are counted: one slow revolution reports 11 of its 12 steps
    (was 8-10), and frames lost on a weak link no longer cost steps.
  - It ignores turns with the cap more than 40° from level (was 60°), and a
    shake, a jolt or a fall no longer adds steps before it is recognised.
  - The gyro's zero offset is learned while the cap lies still, so the knob
    and the card's model do not drift.
- The press that wakes the cap arrives as `press` (`source: wake`) right after
  `wake`: *Count the wake-up as a press* is on by default and existing installs
  are switched on once. It counts only after real sleep, not after a restart or
  a dropped link. An automation that used `wake` to catch the first press now
  gets a `press` as well: turn the option off or drop the `wake` trigger.
- Texts of the setup and options reworded in English, Russian and Polish. New
  option names (the keys stay): *Sensor rate*, *Slow stream after idle*,
  *Invert knob direction*, *Count the wake-up as a press*, *Knob*,
  *Multi-press window*. The pitch and roll sensors are *Tilt forward-back* and
  *Tilt left-right*; entity ids stay `_pitch` and `_roll`.
- For 30 s after Home Assistant starts, a cap heard only through a local
  adapter waits for the Bluetooth proxies instead of linking up through a
  distant adapter at once.
- Firmware that streams faster than asked no longer speeds up gesture timing.
- The README leads with install, what the cap can do and the card.

### Fixed

- Shake fired on fast wrist swings while the cap was picked up. It now needs a
  jolt of 3 g or more: real shakes reach 6-17 g, the swings 1-2 g.
- The automation examples could fire on their own after a restart, when the
  event entity comes back from unavailable with the last event. Their
  triggers now say `not_from: unavailable`.
- Battery: a stream pause could end on a false low reading (21-27 % next to a
  real 82-94 %), turning on the battery saver and the replace-the-cell notice
  on a healthy cell. A pause now reports its highest level, once.
- Knob: a link that holds the stream back for a second or two and then
  delivers it at once no longer drops a partial turn.
- Saving the options right after an idle disconnect no longer links up to the
  dozing cap for another session.
- A cap in its firmware-update bootloader (`TrikiDfu…`) is no longer offered
  as a new device.
- The LED switch keeps its last known state across restarts instead of
  reading unknown until the cap wakes.
- Docs: the cap wakes only on a button press, not on motion; the IMU axes in
  `docs/protocol.md` (+z points out of the green side).

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
