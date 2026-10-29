# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/elenium3/ha-triki/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/elenium3/ha-triki/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/elenium3/ha-triki/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/elenium3/ha-triki/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/elenium3/ha-triki/releases/tag/v0.1.0
