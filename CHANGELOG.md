# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Project documentation under `docs/`: hardware, protocol, installation,
  configuration, events and automations, radio placement, troubleshooting,
  diagnostics, development.
- Repository hygiene: MIT license, contributing guide, code of conduct, security
  policy, issue and pull request templates, Dependabot, release workflow that
  publishes a HACS zip.
- Security workflow: Bandit, ruff security rules, zizmor for the workflows,
  Gitleaks, pip-audit, CodeQL (once the repository is public). All actions
  pinned to commit SHAs, checkouts do not persist credentials, CI runs with
  read-only permissions.
- A beginner's guide to building an ESPHome Bluetooth proxy
  (`docs/bluetooth-proxy.md`).
- README: a plain-language "What is Triki" section with photos and use cases.
  The photos (Flopsstuff/triki, MIT) are now stored in `docs/images/` because
  upstream keeps them in Git LFS and raw links returned pointer text.
- `docs/hardware.md`: board photo, chip photo and the community reference
  schematic (linked from Piwencjusz/zabka-triki-hardware, which has no license
  file), with the pin assignments explained in words.
- `docs/hardware.md`: "Opening it and the battery": CR2032, how the cap is
  built, when a power cycle helps and what it does not fix. The opening
  technique itself is marked as not yet documented.
- README reordered: what it is, quick install, full installation with links,
  entities, docs index. Ruleset for `main` in `.github/rulesets/main.json`.

### Fixed
- Security workflow: Gitleaks needs `pull-requests: read` on pull requests;
  pip-audit is informational (`continue-on-error`) because the audited versions
  are pinned by the Home Assistant test package.

## [0.1.0] - 2026-10-29

First usable version, tested on a real token through an ESPHome Bluetooth proxy
and a Raspberry Pi 5 built-in adapter.

### Added
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

[Unreleased]: https://github.com/elenium3/ha-triki/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/elenium3/ha-triki/releases/tag/v0.1.0
