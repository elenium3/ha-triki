# Contributing

Thanks for taking the time. This is a small project, so the rules are short.

## Before you start

- Check the [open issues](https://github.com/elenium3/ha-triki/issues) and the
  [troubleshooting guide](docs/troubleshooting.md) first.
- For anything beyond a bug fix, open an issue to discuss it before writing code.
  Gesture thresholds in particular are tuned on real captures; a change that looks
  harmless in a unit test can break on hardware.

## Development setup

```bash
git clone https://github.com/elenium3/ha-triki
cd ha-triki
python3.13 -m venv .venv && . .venv/bin/activate
pip install pytest-homeassistant-custom-component pytest-cov mypy ruff bleak
```

Run the full check before opening a pull request. CI runs the same commands:

```bash
ruff check custom_components tests tools
ruff format custom_components tests
mypy
pytest --cov --cov-fail-under=95
```

Details, including how to record and replay captures from a real token, are in
[docs/development.md](docs/development.md).

## Pull requests

- One topic per pull request. Keep refactors separate from behaviour changes.
- Add or adjust tests for every behaviour change. Coverage must stay at 95 % or
  above.
- Update the docs (`README.md`, `docs/`) and `CHANGELOG.md` under *Unreleased*.
- Follow the Home Assistant
  [development guidelines](https://developers.home-assistant.io/docs/development_guidelines):
  type hints everywhere, no blocking I/O in the event loop, user-facing strings in
  `translations/en.json`.
- Protocol changes must cite where the behaviour was observed (capture file, HCI
  snoop, or one of the upstream projects listed in `protocol.py`).

## Reporting hardware findings

Observations about the token itself (timings, advertising behaviour, battery)
are as valuable as code. Open an issue with the *Hardware finding* template and
attach a capture if you have one (`tools/triki_probe.py record`). Captures do not
contain anything personal: raw IMU frames and the token's Bluetooth address.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).
